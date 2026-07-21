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
from app.schemas import ExtractedApplication
from app.services.audit import AuditTrailIsAppendOnly, jsonable, record_event
from app.services.rating import rate
from tests.factories import make_submission
from tests.rating_baseline import CLEAN_ENRICHMENT, application
from tests.test_models import count_queries


@dataclass
class Coordinates:
    latitude: float
    longitude: float


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
