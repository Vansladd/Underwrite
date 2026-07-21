from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, MissingGreenlet
from sqlalchemy.orm import selectinload

from app.domain.enums import (
    AuditActor,
    AuditEventType,
    CompanyStatus,
    DataVolume,
    Decision,
    InputMode,
    QuoteStatus,
    RequestedLimit,
    Sector,
    SubmissionStatus,
)
from app.models import AuditEvent, Enrichment, Extraction, Quote, Rating, Submission
from tests.factories import make_full_submission, make_submission


@contextmanager
def count_queries():
    statements = []

    def record(connection, cursor, statement, *args):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(Engine, "before_cursor_execute", record)


async def test_every_model_round_trips(db):
    submission_id = (await make_full_submission(db)).id
    db.expire_all()

    loaded = await db.scalar(select(Submission).where(Submission.id == submission_id))

    assert loaded.status is SubmissionStatus.REFERRED
    assert loaded.input_mode is InputMode.PASTE
    assert isinstance(loaded.created_at, datetime)
    assert loaded.created_at.tzinfo is not None


async def test_nested_relations_load_with_selectinload(db):
    submission_id = (await make_full_submission(db)).id
    db.expire_all()

    loaded = await db.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(
            selectinload(Submission.extraction),
            selectinload(Submission.enrichment),
            selectinload(Submission.rating),
            selectinload(Submission.quote),
            selectinload(Submission.audit_events),
        )
    )

    assert loaded.extraction.sector is Sector.SAAS
    assert loaded.extraction.requested_limit is RequestedLimit.GBP_1M
    assert loaded.enrichment.ch_company_status is CompanyStatus.ACTIVE
    assert loaded.enrichment.sic_codes == ["62012", "01110"]
    assert loaded.rating.decision is Decision.REFER
    assert loaded.quote.status is QuoteStatus.ISSUED
    assert [event.event_type for event in loaded.audit_events] == [AuditEventType.RATING_COMPLETED]


async def test_an_unloaded_relation_cannot_be_lazy_loaded_under_asyncio(db):
    submission_id = (await make_full_submission(db)).id
    db.expire_all()

    loaded = await db.scalar(select(Submission).where(Submission.id == submission_id))

    with pytest.raises(MissingGreenlet):
        _ = loaded.audit_events


@pytest.mark.parametrize(
    ("table", "column", "value", "expected"),
    [
        ("extractions", "sector", Sector.SAAS, "saas"),
        ("extractions", "data_records_held", DataVolume.HUNDRED_K_TO_1M, "100k_1m"),
        ("enrichments", "ch_company_status", CompanyStatus.ACTIVE, "active"),
        ("submissions", "status", SubmissionStatus.REFERRED, "referred"),
        ("quotes", "status", QuoteStatus.ISSUED, "issued"),
        ("audit_events", "event_type", AuditEventType.RATING_COMPLETED, "rating_completed"),
    ],
)
async def test_string_enums_store_their_value_not_their_name(db, table, column, value, expected):
    submission = await make_full_submission(db)
    key = "id" if table == "submissions" else "submission_id"

    stored = await db.scalar(
        text(f"select {column}::text from {table} where {key} = :id"),  # noqa: S608
        {"id": submission.id},
    )

    assert stored == expected
    assert expected != value.name


async def test_decision_stores_its_name_so_reordering_cannot_rewrite_history(db):
    submission = await make_full_submission(db)

    stored = await db.scalar(
        text("select decision::text from ratings where submission_id = :id"),
        {"id": submission.id},
    )

    assert stored == "REFER"


async def test_requested_limit_stores_its_name_because_a_pg_enum_cannot_hold_an_int(db):
    submission = await make_full_submission(db)

    stored = await db.scalar(
        text("select requested_limit::text from extractions where submission_id = :id"),
        {"id": submission.id},
    )

    assert stored == "GBP_1M"
    assert RequestedLimit.GBP_1M.pence == 100_000_000


async def test_factor_multipliers_survive_jsonb_as_exact_decimals(db):
    submission = await make_submission(db)
    db.add(
        Rating(
            submission_id=submission.id,
            rating_version="v1.0",
            decision=Decision.AUTO_APPROVE,
            base_premium_pence=90_000,
            indicative_premium_pence=278_000,
            annual_premium_pence=278_000,
            factors=[
                {"code": "LIMIT", "multiplier": "1.9", "premium_after_pence": "171000"},
                {"code": "REVENUE_BAND", "multiplier": "1.3", "premium_after_pence": "222300"},
                {"code": "DATA_VOLUME", "multiplier": "1.25", "premium_after_pence": "277875"},
            ],
            refer_reasons=[],
            decline_reasons=[],
        )
    )
    await db.flush()
    submission_id = submission.id
    db.expire_all()

    rating = await db.scalar(select(Rating).where(Rating.submission_id == submission_id))
    running = Decimal(rating.base_premium_pence)
    for factor in rating.factors:
        running *= Decimal(factor["multiplier"])

    assert running == Decimal("277875")
    assert running == Decimal(rating.factors[-1]["premium_after_pence"])


async def test_a_declined_rating_cannot_carry_an_annual_premium(db):
    submission = await make_submission(db)
    db.add(
        Rating(
            submission_id=submission.id,
            rating_version="v1.0",
            decision=Decision.DECLINE,
            base_premium_pence=90_000,
            indicative_premium_pence=417_000,
            annual_premium_pence=417_000,
            factors=[],
            refer_reasons=[],
            decline_reasons=[{"code": "SECTOR_OUT_OF_APPETITE", "message": "Crypto."}],
        )
    )

    with pytest.raises(IntegrityError, match="declined_iff_no_annual_premium"):
        await db.flush()


async def test_an_approved_rating_must_carry_an_annual_premium(db):
    submission = await make_submission(db)
    db.add(
        Rating(
            submission_id=submission.id,
            rating_version="v1.0",
            decision=Decision.AUTO_APPROVE,
            base_premium_pence=90_000,
            indicative_premium_pence=278_000,
            annual_premium_pence=None,
            factors=[],
            refer_reasons=[],
            decline_reasons=[],
        )
    )

    with pytest.raises(IntegrityError, match="declined_iff_no_annual_premium"):
        await db.flush()


async def test_a_submission_with_history_cannot_be_deleted(db):
    submission = await make_submission(db)
    db.add(
        AuditEvent(
            submission_id=submission.id,
            event_type=AuditEventType.SUBMISSION_RECEIVED,
            actor=AuditActor.APPLICANT,
            payload={},
        )
    )
    await db.flush()

    with pytest.raises(IntegrityError, match="fk_audit_events_submission_id"):
        await db.execute(text("delete from submissions where id = :id"), {"id": submission.id})


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (Extraction, {"extraction_confidence": 1.0, "missing_fields": [], "model": "form"}),
        (Enrichment, {"ch_found": False, "sic_codes": [], "discrepancies": []}),
        (
            Rating,
            {
                "rating_version": "v1.0",
                "decision": Decision.AUTO_APPROVE,
                "base_premium_pence": 90_000,
                "indicative_premium_pence": 278_000,
                "annual_premium_pence": 278_000,
                "factors": [],
                "refer_reasons": [],
                "decline_reasons": [],
            },
        ),
        (
            Quote,
            {
                "quote_ref": "UW-2026-0002",
                "limit_pence": 100_000_000,
                "excess_pence": 250_000,
                "gross_premium_pence": 278_000,
                "inception_date": date(2026, 8, 1),
                "valid_until": date(2026, 8, 31),
            },
        ),
    ],
)
async def test_a_submission_gets_at_most_one_of_each_component(db, model, kwargs):
    submission = await make_submission(db)
    db.add(model(submission_id=submission.id, **kwargs))
    await db.flush()

    duplicate = dict(kwargs)
    if "quote_ref" in duplicate:
        duplicate["quote_ref"] = "UW-2026-0003"
    db.add(model(submission_id=submission.id, **duplicate))

    with pytest.raises(IntegrityError, match="uq_"):
        await db.flush()


async def test_quote_references_are_unique_across_submissions(db):
    first = await make_submission(db)
    second = await make_submission(db)
    shared = {
        "quote_ref": "UW-2026-0009",
        "limit_pence": 100_000_000,
        "excess_pence": 250_000,
        "gross_premium_pence": 278_000,
        "inception_date": date(2026, 8, 1),
        "valid_until": date(2026, 8, 31),
    }
    db.add(Quote(submission_id=first.id, **shared))
    await db.flush()
    db.add(Quote(submission_id=second.id, **shared))

    with pytest.raises(IntegrityError, match="uq_quotes_quote_ref"):
        await db.flush()


async def test_timestamps_are_timezone_aware(db):
    submission = await make_submission(db)
    db.add(
        AuditEvent(
            submission_id=submission.id,
            event_type=AuditEventType.SUBMISSION_RECEIVED,
            actor=AuditActor.APPLICANT,
            payload={},
        )
    )
    await db.flush()
    submission_id = submission.id
    db.expire_all()

    event = await db.scalar(select(AuditEvent).where(AuditEvent.submission_id == submission_id))

    assert event.occurred_at.tzinfo is not None
    assert event.occurred_at.astimezone(UTC) <= datetime.now(UTC)


async def test_selectinload_costs_one_query_per_relation(db):
    submission_id = (await make_full_submission(db)).id
    db.expire_all()

    with count_queries() as statements:
        loaded = await db.scalar(
            select(Submission)
            .where(Submission.id == submission_id)
            .options(
                selectinload(Submission.extraction),
                selectinload(Submission.enrichment),
                selectinload(Submission.rating),
                selectinload(Submission.quote),
                selectinload(Submission.audit_events),
            )
        )
        assert loaded.extraction.company_name == "Example Ltd"
        assert loaded.quote.quote_ref == "UW-2026-0001"

    # One for the submission, one per relation.
    assert len(statements) == 6


async def test_events_written_in_one_transaction_keep_their_order(db):
    submission = await make_submission(db)
    written = [
        AuditEventType.SUBMISSION_RECEIVED,
        AuditEventType.EXTRACTION_COMPLETED,
        AuditEventType.ENRICHMENT_COMPLETED,
        AuditEventType.RATING_COMPLETED,
    ]
    for event_type in written:
        db.add(
            AuditEvent(
                submission_id=submission.id,
                event_type=event_type,
                actor=AuditActor.SYSTEM,
                payload={},
            )
        )
        await db.flush()
    submission_id = submission.id
    db.expire_all()

    loaded = await db.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(selectinload(Submission.audit_events))
    )

    assert [event.event_type for event in loaded.audit_events] == written
    stamps = [event.occurred_at for event in loaded.audit_events]
    assert len(set(stamps)) == len(stamps)


async def test_form_submissions_have_no_raw_input(db):
    submission = await make_submission(db, input_mode=InputMode.FORM, raw_input=None)
    submission_id = submission.id
    db.expire_all()

    loaded = await db.scalar(select(Submission).where(Submission.id == submission_id))

    assert loaded.raw_input is None
    assert loaded.input_mode is InputMode.FORM


async def test_rows_inserted_outside_the_orm_get_their_defaults(db):
    submission_id = await db.scalar(
        text(
            "insert into submissions (input_mode, raw_input) "
            "values ('paste', 'quote us please') returning id"
        )
    )
    await db.execute(
        text("insert into enrichments (submission_id, ch_found) values (:id, false)"),
        {"id": submission_id},
    )

    status, rate_limited, sic_codes = (
        await db.execute(
            text(
                "select s.status::text, e.rate_limited, e.sic_codes "
                "from submissions s join enrichments e on e.submission_id = s.id "
                "where s.id = :id"
            ),
            {"id": submission_id},
        )
    ).one()

    assert status == "received"
    assert rate_limited is False
    assert sic_codes == []


async def test_a_committing_test_does_not_leak_rows(db, engine):
    submission = await make_submission(db, raw_input="committed inside a test")
    await db.commit()

    async with engine.connect() as outside:
        visible = await outside.scalar(
            text("select count(*) from submissions where id = :id"), {"id": submission.id}
        )

    assert visible == 0
