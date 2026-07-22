from sqlalchemy import select

from app.domain.enums import (
    AuditEventType,
    CompanyStatus,
    DataVolume,
    RequestedLimit,
    Sector,
    SubmissionStatus,
)
from app.models import AuditEvent, Enrichment, Extraction, Rating
from app.schemas import CompanyProfile, ExtractedApplication
from app.services import pipeline as pipeline_module
from app.services.companies_house import CompaniesHouseLookup
from app.services.extraction import ExtractionRefused
from app.services.pipeline import run_pipeline
from tests.factories import make_submission
from tests.fakes import FakeChClient, FakeExtractor

COMPLETE = dict(
    company_name="Example Ltd",
    company_number="00000006",
    sector=Sector.SAAS,
    annual_revenue_gbp=750_000.0,
    years_trading=3.0,
    prior_claims_count=0,
    data_records_held=DataVolume.HUNDRED_K_TO_1M,
    requested_limit_gbp=RequestedLimit.GBP_1M,
    extraction_confidence=0.94,
)


def application(**overrides) -> ExtractedApplication:
    return ExtractedApplication(**{**COMPLETE, **overrides})


def active_profile() -> CompaniesHouseLookup:
    return CompaniesHouseLookup(
        CompanyProfile(
            company_number="00000006",
            company_name="EXAMPLE LIMITED",
            company_status=CompanyStatus.ACTIVE,
            date_of_creation=None,
            sic_codes=["62012"],
        )
    )


async def row(db, model, submission_id):
    return await db.scalar(select(model).where(model.submission_id == submission_id))


async def event_types(db, submission_id) -> list[AuditEventType]:
    events = (
        await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.submission_id == submission_id)
            .order_by(AuditEvent.occurred_at)
        )
    ).all()
    return [each.event_type for each in events]


async def test_a_paste_runs_extract_enrich_rate_and_auto_approves(db):
    submission = await make_submission(db)
    extractor = FakeExtractor(result=application())
    ch = FakeChClient(active_profile())

    await run_pipeline(db, submission, None, extractor, ch)

    assert extractor.calls == [submission.raw_input]
    assert await event_types(db, submission.id) == [
        AuditEventType.EXTRACTION_COMPLETED,
        AuditEventType.ENRICHMENT_COMPLETED,
        AuditEventType.RATING_COMPLETED,
    ]
    rating = await row(db, Rating, submission.id)
    assert rating.decision.name == "AUTO_APPROVE"
    assert submission.status is SubmissionStatus.AUTO_APPROVED


async def test_a_form_application_skips_the_extractor(db):
    submission = await make_submission(db, input_mode="form")
    extractor = FakeExtractor(error=AssertionError("form must not call the LLM"))
    ch = FakeChClient()

    await run_pipeline(db, submission, application(), extractor, ch)

    assert extractor.calls == []
    extraction = await row(db, Extraction, submission.id)
    assert extraction.model == "form"
    # CH not found -> referred.
    assert submission.status is SubmissionStatus.REFERRED


async def test_an_extraction_failure_stops_the_pipeline_recoverably(db):
    submission = await make_submission(db)
    extractor = FakeExtractor(error=ExtractionRefused({"reason": "policy"}))
    ch = FakeChClient(active_profile())

    await run_pipeline(db, submission, None, extractor, ch)

    assert await event_types(db, submission.id) == [AuditEventType.EXTRACTION_FAILED]
    assert submission.status is SubmissionStatus.FAILED
    assert await row(db, Extraction, submission.id) is None
    assert await row(db, Enrichment, submission.id) is None


async def test_a_companies_house_outage_still_produces_a_rating(db):
    submission = await make_submission(db)
    extractor = FakeExtractor(result=application())
    ch = FakeChClient(error=RuntimeError("companies house is down"))

    await run_pipeline(db, submission, None, extractor, ch)

    # Enrichment failure is best-effort: it degrades to CH_NOT_FOUND -> REFER, never a hard stop.
    assert await event_types(db, submission.id) == [
        AuditEventType.EXTRACTION_COMPLETED,
        AuditEventType.ENRICHMENT_FAILED,
        AuditEventType.RATING_COMPLETED,
    ]
    enrichment = await row(db, Enrichment, submission.id)
    assert enrichment.ch_found is False
    assert submission.status is SubmissionStatus.REFERRED


async def test_incomplete_extraction_is_referred_not_rated(db):
    submission = await make_submission(db)
    extractor = FakeExtractor(
        result=application(annual_revenue_gbp=None, missing_fields=["annual_revenue_gbp"])
    )
    ch = FakeChClient()

    await run_pipeline(db, submission, None, extractor, ch)

    assert await event_types(db, submission.id) == [
        AuditEventType.EXTRACTION_COMPLETED,
        AuditEventType.ENRICHMENT_COMPLETED,
        AuditEventType.RATING_FAILED,
    ]
    assert submission.status is SubmissionStatus.REFERRED
    # Extraction + enrichment persisted; no rating, because the engine can't run without the input.
    assert await row(db, Extraction, submission.id)
    assert await row(db, Enrichment, submission.id)
    assert await row(db, Rating, submission.id) is None


async def test_a_rating_engine_crash_leaves_the_earlier_stages_durable(db, monkeypatch):
    submission = await make_submission(db)
    extractor = FakeExtractor(result=application())
    ch = FakeChClient(active_profile())

    def boom(*args, **kwargs):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(pipeline_module, "rate", boom)

    await run_pipeline(db, submission, None, extractor, ch)

    assert await event_types(db, submission.id) == [
        AuditEventType.EXTRACTION_COMPLETED,
        AuditEventType.ENRICHMENT_COMPLETED,
        AuditEventType.RATING_FAILED,
    ]
    assert submission.status is SubmissionStatus.FAILED
    # The whole point: A and B committed before C blew up.
    assert await row(db, Extraction, submission.id)
    assert await row(db, Enrichment, submission.id)
    assert await row(db, Rating, submission.id) is None
