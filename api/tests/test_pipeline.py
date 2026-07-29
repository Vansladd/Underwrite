from sqlalchemy import select

from app.domain.enums import (
    AuditActor,
    AuditEventType,
    CompanyStatus,
    DataVolume,
    QuoteStatus,
    ReasonCode,
    RequestedLimit,
    Sector,
    SubmissionStatus,
)
from app.models import AuditEvent, Enrichment, Extraction, Quote, Rating
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
        AuditEventType.SUBMISSION_APPROVED,
    ]
    rating = await row(db, Rating, submission.id)
    assert rating.decision.name == "AUTO_APPROVE"
    assert submission.status is SubmissionStatus.AUTO_APPROVED


async def test_auto_approval_issues_its_own_quote(db):
    submission = await make_submission(db)

    extractor = FakeExtractor(result=application())
    await run_pipeline(db, submission, None, extractor, FakeChClient(active_profile()))

    # No underwriter is coming, so nothing else would ever issue one (D-030).
    quote = await row(db, Quote, submission.id)
    assert quote is not None
    assert quote.quote_ref.startswith("Q-")
    assert quote.status is QuoteStatus.ISSUED
    # The status records who decided; both auto_approved and quoted now carry a Quote.
    assert submission.status is SubmissionStatus.AUTO_APPROVED

    event = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.submission_id == submission.id,
            AuditEvent.event_type == AuditEventType.SUBMISSION_APPROVED,
        )
    )
    assert event.actor is AuditActor.SYSTEM
    assert event.actor_id is None
    assert event.payload["auto"] is True


async def test_a_failed_quote_does_not_take_the_rating_with_it(db, monkeypatch):
    # quote_ref is unique-constrained and built from 6 hex chars, so a collision is rare but real.
    # It must not roll back a rating that was already earned.
    def boom(*args, **kwargs):
        raise RuntimeError("duplicate key value violates unique constraint")

    monkeypatch.setattr(pipeline_module, "build_quote", boom)
    submission = await make_submission(db)

    await run_pipeline(
        db, submission, None, FakeExtractor(result=application()), FakeChClient(active_profile())
    )

    assert await row(db, Quote, submission.id) is None
    # The rating survives, and the trail says the decision was made without an approval after it.
    rating = await row(db, Rating, submission.id)
    assert rating.decision.name == "AUTO_APPROVE"
    assert submission.status is SubmissionStatus.AUTO_APPROVED
    events = await event_types(db, submission.id)
    assert AuditEventType.RATING_COMPLETED in events
    assert AuditEventType.SUBMISSION_APPROVED not in events


async def test_a_referral_issues_no_quote(db):
    submission = await make_submission(db)
    ch = FakeChClient()  # no CH match -> CH_NOT_FOUND -> REFER

    await run_pipeline(db, submission, None, FakeExtractor(result=application()), ch)

    assert submission.status is SubmissionStatus.REFERRED
    # A referral is an underwriter's to decide; issuing a quote here would pre-empt them.
    assert await row(db, Quote, submission.id) is None


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

    # Enrichment failure is best-effort: it degrades to CH_UNAVAILABLE -> REFER, never a hard stop.
    assert await event_types(db, submission.id) == [
        AuditEventType.EXTRACTION_COMPLETED,
        AuditEventType.ENRICHMENT_FAILED,
        AuditEventType.RATING_COMPLETED,
    ]
    enrichment = await row(db, Enrichment, submission.id)
    assert enrichment.ch_found is False
    assert submission.status is SubmissionStatus.REFERRED


async def test_a_rate_limited_lookup_is_not_recorded_as_a_completed_check(db):
    submission = await make_submission(db)
    extractor = FakeExtractor(result=application())
    ch = FakeChClient(CompaniesHouseLookup(None, rate_limited=True))

    await run_pipeline(db, submission, None, extractor, ch)

    # The trail must not say "Companies House checked" while the decision says it could not be.
    assert AuditEventType.ENRICHMENT_FAILED in await event_types(db, submission.id)
    rating = await row(db, Rating, submission.id)
    assert [r["code"] for r in rating.refer_reasons] == [ReasonCode.CH_UNAVAILABLE.value]


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
