from contextlib import contextmanager
from dataclasses import replace
from datetime import date

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.domain.enums import (
    AuditActor,
    AuditEventType,
    CompanyStatus,
    DataVolume,
    InputMode,
    RequestedLimit,
    Sector,
    SubmissionStatus,
)
from app.models import AuditEvent, Enrichment, Extraction, Quote, Rating, Submission
from app.schemas import rating_to_orm_kwargs
from app.services.rating import rate
from tests.rating_baseline import CLEAN_ENRICHMENT, application


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


async def make_submission(db, **overrides) -> Submission:
    submission = Submission(
        **{
            "input_mode": InputMode.PASTE,
            "raw_input": "Please quote Example Ltd for £1m cyber cover.",
            **overrides,
        }
    )
    db.add(submission)
    await db.flush()
    return submission


STRIKE_OFF = replace(
    CLEAN_ENRICHMENT,
    discrepancies=("Companies House shows a proposal to strike off.",),
)


async def make_full_submission(db) -> Submission:
    submission = await make_submission(db, status=SubmissionStatus.REFERRED)
    db.add_all(
        [
            Extraction(
                submission_id=submission.id,
                company_name="Example Ltd",
                sector=Sector.SAAS,
                annual_revenue_pence=75_000_000,
                months_trading=36,
                prior_claims_count=0,
                data_records_held=DataVolume.HUNDRED_K_TO_1M,
                requested_limit=RequestedLimit.GBP_1M,
                extraction_confidence=0.94,
                missing_fields=[],
                model="claude-sonnet-5",
            ),
            Enrichment(
                submission_id=submission.id,
                ch_found=True,
                ch_company_number="00000006",
                ch_company_name="EXAMPLE LIMITED",
                ch_company_status=CompanyStatus.ACTIVE,
                ch_company_status_detail="active-proposal-to-strike-off",
                ch_date_of_creation=date(2021, 4, 1),
                ch_name_match_score=0.97,
                sic_codes=["62012", "01110"],
                discrepancies=["Companies House shows a proposal to strike off."],
            ),
            Rating(
                submission_id=submission.id,
                **rating_to_orm_kwargs(rate(application(), STRIKE_OFF)),
            ),
            Quote(
                submission_id=submission.id,
                quote_ref="UW-2026-0001",
                limit_pence=100_000_000,
                excess_pence=250_000,
                gross_premium_pence=278_000,
                inception_date=date(2026, 8, 1),
                valid_until=date(2026, 8, 31),
            ),
            AuditEvent(
                submission_id=submission.id,
                event_type=AuditEventType.RATING_COMPLETED,
                actor=AuditActor.SYSTEM,
                payload={"decision": "REFER"},
            ),
        ]
    )
    await db.flush()
    return submission
