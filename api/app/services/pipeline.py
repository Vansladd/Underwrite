from __future__ import annotations

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    AuditActor,
    AuditEventType,
    Decision,
    SubmissionStatus,
)
from app.models import Enrichment, Extraction, Rating, Submission
from app.schemas import ExtractedApplication, IncompleteExtraction, rating_to_orm_kwargs
from app.services.audit import record_event
from app.services.companies_house import CompaniesHouseClient
from app.services.enrichment import enrich
from app.services.extraction import AnthropicExtractor, ExtractionRefused
from app.services.rating import rate

FORM_MODEL = "form"

STATUS_FOR_DECISION = {
    Decision.AUTO_APPROVE: SubmissionStatus.AUTO_APPROVED,
    Decision.REFER: SubmissionStatus.REFERRED,
    Decision.DECLINE: SubmissionStatus.DECLINED,
}


async def run_pipeline(
    session: AsyncSession,
    submission: Submission,
    application: ExtractedApplication | None,
    extractor: AnthropicExtractor,
    ch_client: CompaniesHouseClient,
) -> None:
    """Extract -> enrich -> rate, one AuditEvent per transition, committing after each stage.

    A stage failure leaves a recoverable status with the error in the audit payload (UW-025).
    """
    application = await _extract(session, submission, application, extractor)
    if application is None:
        return

    enrichment = await _enrich(session, submission, application, ch_client)
    await _rate(session, submission, application, enrichment)


async def _extract(
    session: AsyncSession,
    submission: Submission,
    application: ExtractedApplication | None,
    extractor: AnthropicExtractor,
) -> ExtractedApplication | None:
    if application is not None:
        model, source = FORM_MODEL, "applicant_form"
    elif submission.raw_input is not None:
        model, source = extractor.model, "broker_email"
        try:
            application = await extractor.extract(submission.raw_input)
        except (anthropic.APIStatusError, ExtractionRefused) as error:
            await record_event(
                session,
                submission.id,
                AuditEventType.EXTRACTION_FAILED,
                AuditActor.SYSTEM,
                {"model": model, "source": source, "error": repr(error)},
            )
            submission.status = SubmissionStatus.FAILED
            await session.commit()
            return None
    else:
        # pdf_upload: the text does not exist until pypdf runs (UW-026). Leaves 'received'.
        return None

    session.add(Extraction(submission_id=submission.id, **application.to_orm_kwargs(model)))
    await record_event(
        session,
        submission.id,
        AuditEventType.EXTRACTION_COMPLETED,
        AuditActor.SYSTEM,
        {"model": model, "source": source, "fields": sorted(application.model_fields_set)},
    )
    await session.commit()
    return application


async def _enrich(
    session: AsyncSession,
    submission: Submission,
    application: ExtractedApplication,
    ch_client: CompaniesHouseClient,
):
    outcome = await enrich(ch_client, application)
    session.add(Enrichment(submission_id=submission.id, **outcome.orm_kwargs))

    event_type = (
        AuditEventType.ENRICHMENT_FAILED
        if outcome.error is not None
        else AuditEventType.ENRICHMENT_COMPLETED
    )
    payload = {
        "ch_found": outcome.orm_kwargs["ch_found"],
        "rate_limited": outcome.orm_kwargs["rate_limited"],
        "discrepancies": len(outcome.orm_kwargs["discrepancies"]),
    }
    if outcome.error is not None:
        payload["error"] = outcome.error
    await record_event(session, submission.id, event_type, AuditActor.SYSTEM, payload)
    await session.commit()
    return outcome.domain


async def _rate(
    session: AsyncSession,
    submission: Submission,
    application: ExtractedApplication,
    enrichment,
) -> None:
    try:
        domain_application = application.to_domain()
    except IncompleteExtraction as error:
        # A valid extraction that lacks required inputs is a referral, not a system failure.
        submission.status = SubmissionStatus.REFERRED
        await record_event(
            session,
            submission.id,
            AuditEventType.RATING_FAILED,
            AuditActor.SYSTEM,
            {"reason": "incomplete_extraction", "missing_fields": list(error.missing)},
        )
        await session.commit()
        return

    try:
        result = rate(domain_application, enrichment)
    except Exception as error:
        # rate() is pure and validated; a raise is a bug. A+B stay durable, status recoverable.
        submission.status = SubmissionStatus.FAILED
        await record_event(
            session,
            submission.id,
            AuditEventType.RATING_FAILED,
            AuditActor.SYSTEM,
            {"reason": "rating_error", "error": repr(error)},
        )
        await session.commit()
        return

    session.add(Rating(submission_id=submission.id, **rating_to_orm_kwargs(result)))
    submission.status = STATUS_FOR_DECISION[result.decision]
    await record_event(
        session,
        submission.id,
        AuditEventType.RATING_COMPLETED,
        AuditActor.SYSTEM,
        {
            "decision": result.decision.name,
            "indicative_premium_pence": result.indicative_premium_pence,
            "refer_reasons": len(result.refer_reasons),
            "decline_reasons": len(result.decline_reasons),
        },
    )
    await session.commit()
