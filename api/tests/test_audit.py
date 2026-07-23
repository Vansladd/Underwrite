import socket
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.domain.enums import AuditActor, AuditEventType, Decision, RequestedLimit, Sector
from app.models import AuditEvent
from app.models.audit_event import AuditTrailIsAppendOnly
from app.schemas import ExtractedApplication
from app.services.audit import jsonable, record_event
from app.services.rating import rate
from tests.factories import count_queries, make_submission
from tests.rating_baseline import CLEAN_ENRICHMENT, application

RESTRICT_VIOLATION = "23001"


@dataclass
class Coordinates:
    latitude: float
    longitude: float


@dataclass
class Wrapper:
    inner: object


# Every one of these raises TypeError at flush if it reaches JSONB uncoerced.
UNSERIALISABLE = [
    pytest.param(Decimal("1.35"), "1.35", id="decimal"),
    pytest.param(datetime(2026, 7, 21, 12, 0, tzinfo=UTC), "2026-07-21T12:00:00+00:00", id="dt"),
    pytest.param(date(2026, 7, 21), "2026-07-21", id="date"),
    pytest.param(
        uuid.UUID("0f9d1e6a-8d3f-4a1c-9d2b-2f9a6c1e4b77"),
        "0f9d1e6a-8d3f-4a1c-9d2b-2f9a6c1e4b77",
        id="uuid",
    ),
    pytest.param({1, 2}, [1, 2], id="set"),
    pytest.param(Coordinates(51.5, -0.12), {"latitude": 51.5, "longitude": -0.12}, id="dataclass"),
]


@pytest.mark.parametrize(("value", "expected"), UNSERIALISABLE)
def test_types_that_jsonb_rejects_are_coerced(value, expected):
    assert jsonable(value) == expected


def test_enums_keep_the_representation_the_database_uses():
    assert jsonable(Sector.SAAS) == "saas"
    assert jsonable(RequestedLimit.GBP_1M) == 1_000_000
    # IntEnum is an int, so the primitive branch would have written 0 (RATING_SPEC D7).
    assert jsonable(Decision.AUTO_APPROVE) == "AUTO_APPROVE"


def test_dictionary_keys_become_strings():
    assert jsonable({(1, 2): "corner", 3: "three"}) == {"(1, 2)": "corner", "3": "three"}


def test_bytes_are_summarised_not_expanded_into_integers():
    # The Sequence branch would render a 2MB PDF as two million integers.
    assert jsonable(b"%PDF-1.7 header") == "%PDF-1.7 header"
    assert jsonable(bytes(4096)) == "<4096 bytes>"


def test_undecodable_bytes_are_described_by_length():
    assert jsonable(b"\xff\xfe\x00binary") == "<9 bytes>"


def test_nul_never_reaches_jsonb():
    # Postgres rejects \u0000 in a jsonb string, so a decodable NUL is still a flush failure.
    assert "\x00" not in jsonable({"text": "before\x00after"})["text"]
    assert jsonable(bytes(16)) == "<16 bytes>"


def test_a_cycle_is_marked_rather_than_recursed_forever():
    cyclic = {"name": "loop"}
    cyclic["self"] = cyclic

    coerced = jsonable(cyclic)

    assert coerced["name"] == "loop"
    assert coerced["self"] == "<cycle: dict>"


def test_a_dataclass_holding_an_unpicklable_field_does_not_raise():
    # asdict() deep-copies, and deepcopy raises on a socket.
    with socket.socket() as connection:
        coerced = jsonable(Wrapper(connection))

    assert coerced["inner"].startswith("<socket.socket")


def test_an_object_with_no_json_form_is_recorded_not_raised():
    with socket.socket() as unserialisable:
        coerced = jsonable({"connection": unserialisable})

    assert coerced["connection"].startswith("<socket.socket")


def test_a_pydantic_model_keeps_its_field_names():
    coerced = jsonable(ExtractedApplication(extraction_confidence=0.9, years_trading=3.0))

    assert coerced["years_trading"] == 3.0
    assert coerced["annual_revenue_gbp"] is None


# --- the payload the pipeline will actually write -----------------------------------------


async def test_a_rating_result_survives_the_round_trip_exactly(db):
    submission = await make_submission(db)
    result = rate(application(), CLEAN_ENRICHMENT)

    await record_event(
        db,
        submission.id,
        AuditEventType.RATING_COMPLETED,
        AuditActor.SYSTEM,
        {"output": result},
    )
    submission_id = submission.id
    db.expire_all()

    stored = await db.scalar(select(AuditEvent).where(AuditEvent.submission_id == submission_id))
    factors = stored.payload["output"]["factors"]

    running = Decimal(stored.payload["output"]["base_premium_pence"])
    for factor in factors:
        running *= Decimal(factor["multiplier"])

    assert running == Decimal(factors[-1]["premium_after_pence"])
    assert stored.payload["output"]["decision"] == "AUTO_APPROVE"
    assert stored.payload["output"]["indicative_premium_pence"] == result.indicative_premium_pence


async def test_recording_an_event_returns_it_with_its_timestamp_assigned(db):
    submission = await make_submission(db)

    recorded = await record_event(
        db, submission.id, AuditEventType.SUBMISSION_RECEIVED, AuditActor.APPLICANT, {}
    )

    assert recorded.id is not None
    assert recorded.occurred_at is not None


async def test_an_unknown_submission_fails_at_the_call_site(db):
    with pytest.raises(IntegrityError, match="fk_audit_events_submission_id"):
        await record_event(
            db, uuid.uuid4(), AuditEventType.SUBMISSION_RECEIVED, AuditActor.SYSTEM, {}
        )


# --- append-only --------------------------------------------------------------------------


async def test_a_pipeline_run_keeps_its_events_in_order(db):
    submission = await make_submission(db)
    written = [
        AuditEventType.SUBMISSION_RECEIVED,
        AuditEventType.EXTRACTION_COMPLETED,
        AuditEventType.ENRICHMENT_COMPLETED,
        AuditEventType.RATING_COMPLETED,
    ]

    for event_type in written:
        await record_event(db, submission.id, event_type, AuditActor.SYSTEM, {})

    stored = (
        await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.submission_id == submission.id)
            .order_by(AuditEvent.occurred_at)
        )
    ).all()
    stamps = [each.occurred_at for each in stored]

    assert [each.event_type for each in stored] == written
    assert len(set(stamps)) == len(stamps)
    assert stamps == sorted(stamps)


async def test_recording_an_event_only_inserts(db):
    submission = await make_submission(db)
    await record_event(
        db, submission.id, AuditEventType.EXTRACTION_COMPLETED, AuditActor.SYSTEM, {}
    )

    with count_queries() as statements:
        await record_event(
            db, submission.id, AuditEventType.RATING_COMPLETED, AuditActor.SYSTEM, {}
        )

    touched = [s for s in statements if "audit_events" in s.lower()]
    assert touched
    assert all(s.strip().upper().startswith("INSERT") for s in touched)


async def test_an_earlier_event_is_untouched_by_a_later_one(db):
    submission = await make_submission(db)
    first = await record_event(
        db, submission.id, AuditEventType.SUBMISSION_RECEIVED, AuditActor.APPLICANT, {"seq": 1}
    )
    before = (
        await db.execute(
            text("select event_type::text, actor::text, payload, occurred_at from audit_events"),
        )
    ).one()

    await record_event(
        db, submission.id, AuditEventType.RATING_COMPLETED, AuditActor.SYSTEM, {"seq": 2}
    )

    after = (
        await db.execute(
            text(
                "select event_type::text, actor::text, payload, occurred_at "
                "from audit_events where id = :id"
            ),
            {"id": first.id},
        )
    ).one()

    assert after == before


async def test_an_event_cannot_be_edited(db):
    submission = await make_submission(db)
    recorded = await record_event(
        db, submission.id, AuditEventType.RATING_COMPLETED, AuditActor.SYSTEM, {"seq": 1}
    )

    recorded.payload = {"seq": 2}

    with pytest.raises(AuditTrailIsAppendOnly, match="cannot be modified"):
        await db.flush()


async def test_an_event_cannot_be_deleted(db):
    submission = await make_submission(db)
    recorded = await record_event(
        db, submission.id, AuditEventType.RATING_COMPLETED, AuditActor.SYSTEM, {}
    )

    await db.delete(recorded)

    with pytest.raises(AuditTrailIsAppendOnly, match="cannot be deleted"):
        await db.flush()


async def test_a_non_mapping_payload_is_refused_at_the_call_site(db):
    submission = await make_submission(db)

    # JSONB would accept an array, but the model and read schema both type payload as an object.
    with pytest.raises(TypeError, match="payload must be a mapping"):
        await record_event(
            db, submission.id, AuditEventType.RATING_COMPLETED, AuditActor.SYSTEM, [1, 2]
        )


def test_the_append_only_guard_does_not_depend_on_importing_the_service():
    # A zip Lambda (#40, #41) imports models and never touches app.services.
    assert len(AuditEvent.__mapper__.dispatch.before_delete) == 1
    assert len(AuditEvent.__mapper__.dispatch.before_update) == 1


# --- immutable at the database, not only in the ORM ---------------------------------------


# TRUNCATE is the one a reset routine reaches for, and row triggers do not see it.
TAMPERING = [
    pytest.param("update audit_events set payload = '{\"tampered\": true}'", id="update"),
    pytest.param("delete from audit_events", id="delete"),
    pytest.param("truncate audit_events", id="truncate"),
    pytest.param("truncate submissions cascade", id="truncate_cascade"),
]


@pytest.mark.parametrize("statement", TAMPERING)
async def test_raw_sql_cannot_change_the_trail(db, statement):
    submission = await make_submission(db)
    await record_event(
        db, submission.id, AuditEventType.RATING_COMPLETED, AuditActor.SYSTEM, {"seq": 1}
    )

    # Core and raw SQL never reach the mapper listeners, so only the triggers stop these.
    with pytest.raises(IntegrityError) as raised:
        await db.execute(text(statement))

    # The SQLSTATE the migration declares, not the message text it happens to carry.
    assert raised.value.orig.sqlstate == RESTRICT_VIOLATION


async def test_the_trigger_does_not_block_appending(db):
    submission = await make_submission(db)

    for _ in range(3):
        await record_event(
            db, submission.id, AuditEventType.RATING_COMPLETED, AuditActor.SYSTEM, {}
        )

    stored = await db.scalar(
        text("select count(*) from audit_events where submission_id = :id"),
        {"id": submission.id},
    )
    assert stored == 3


async def test_the_orm_error_wins_over_the_database_one(db):
    submission = await make_submission(db)
    recorded = await record_event(
        db, submission.id, AuditEventType.RATING_COMPLETED, AuditActor.SYSTEM, {}
    )

    await db.delete(recorded)

    # The listener fires before the flush reaches Postgres, so the reader gets the clearer error.
    with pytest.raises(AuditTrailIsAppendOnly):
        await db.flush()


async def test_an_event_can_name_the_operator_who_wrote_it(db):
    # The attribution wiring UW-034 will use; here we just prove the column round-trips.
    from app.models import User
    from app.services.auth import hash_password

    operator = User(username="jane", password_hash=hash_password("pw"), display_name="Jane")
    db.add(operator)
    submission = await make_submission(db)
    await db.flush()

    recorded = await record_event(
        db,
        submission.id,
        AuditEventType.SUBMISSION_APPROVED,
        AuditActor.OPS,
        {},
        actor_id=operator.id,
    )

    fetched = await db.scalar(select(AuditEvent).where(AuditEvent.id == recorded.id))
    assert fetched.actor_id == operator.id
