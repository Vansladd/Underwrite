from __future__ import annotations

import logging
from datetime import date

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    AuditActor,
    AuditEventType,
    Decision,
    InputMode,
    SubmissionStatus,
)
from app.models import Enrichment, Extraction, Rating, Submission
from app.schemas import ExtractedApplication, IncompleteExtraction, rating_to_orm_kwargs
from app.services.audit import record_event
from app.services.companies_house import CompaniesHouseClient
from app.services.enrichment import enrich
from app.services.extraction import AnthropicExtractor, ExtractionRefused
from app.services.quote import build_quote
from app.services.rating import rate

log = logging.getLogger("uvicorn.error")

FORM_MODEL = "form"

SOURCE_FOR_MODE = {
    InputMode.PASTE: "broker_email",
    InputMode.PDF_UPLOAD: "uploaded_pdf",
}

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
    elif submission.raw_input:
        model, source = extractor.model, SOURCE_FOR_MODE[submission.input_mode]
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
        # Unreachable: every creation route carries a form application or extractable text.
        raise ValueError(f"submission {submission.id} has no extractable payload")

    submission.extraction = Extraction(
        submission_id=submission.id, **application.to_orm_kwargs(model)
    )
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

    # Keyed on lookup_failed, not error: a rate limit has no error slug but is still a lookup that
    # never happened, and the trail must not say "checked" while the decision says "could not be".
    event_type = (
        AuditEventType.ENRICHMENT_FAILED
        if outcome.domain.lookup_failed
        else AuditEventType.ENRICHMENT_COMPLETED
    )
    payload = {
        "ch_found": outcome.orm_kwargs["ch_found"],
        "rate_limited": outcome.orm_kwargs["rate_limited"],
        "discrepancies": len(outcome.orm_kwargs["discrepancies"]),
    }
    if outcome.error is not None:
        # A classified slug, not a repr: this trail is append-only and cannot be redacted (D-010).
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

    # Assigned, not just added: build_quote reads submission.rating/.extraction below.
    submission.rating = Rating(submission_id=submission.id, **rating_to_orm_kwargs(result))
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

    # Committed before the quote: issuing one is a separate transaction so that a failure there
    # cannot roll back the rating that has already been earned.
    await session.commit()

    if result.decision is Decision.AUTO_APPROVE:
        await issue_quote(session, submission)


async def issue_quote(session: AsyncSession, submission: Submission) -> None:
    """The machine's own quote. AUTO_APPROVE means no underwriter is coming, so nothing else would
    ever issue one and 'auto-approved' would mean priced-then-abandoned. See D-030.

    The status stays `auto_approved` rather than becoming `quoted`: both now carry a Quote, and the
    distinction records *who* decided, which is the question an auditor asks.
    """
    try:
        quote = build_quote(submission, today=date.today())
        session.add(quote)
        # SUBMISSION_APPROVED, not QUOTE_GENERATED: that one already means "the PDF was rendered",
        # and the render happens later in the route. This is the approval itself, exactly parallel
        # to the operator's — with no actor_id, because there is no human and borrowing one would
        # falsify the trail.
        await record_event(
            session,
            submission.id,
            AuditEventType.SUBMISSION_APPROVED,
            AuditActor.SYSTEM,
            {"quote_ref": quote.quote_ref, "auto": True},
        )
        await session.commit()
    except Exception as error:  # noqa: BLE001 — the rating is already durable; keep it that way.
        # A quote_ref collision or any other insert failure degrades to the pre-D-030 state:
        # auto_approved with no quote. The committed rating_completed event, with no
        # submission_approved after it, is what says so.
        await session.rollback()
        log.warning("auto-approval quote failed for %s: %s", submission.id, error)
