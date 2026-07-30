"""Ask Companies House again for a submission that referred because it could not be asked."""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AuditActor, AuditEventType, Decision, ReasonCode, SubmissionStatus
from app.domain.rating import Application
from app.models import Submission
from app.schemas import ExtractedApplication, rating_to_orm_kwargs
from app.services.audit import record_event
from app.services.companies_house import CompaniesHouseClient
from app.services.enrichment import enrich
from app.services.pipeline import STATUS_FOR_DECISION, issue_quote
from app.services.rating import rate


class NotRecheckable(Exception):
    """Why this submission must not be re-rated. The message is shown to the operator."""


@dataclass(frozen=True)
class RecheckOutcome:
    decision_before: Decision
    decision_after: Decision
    premium_before_pence: int
    premium_after_pence: int
    resolved: bool


def _reason_codes(rating) -> set[str]:
    # Stored as JSON dicts by reason_to_json, so the code is a key rather than an attribute.
    return {reason.get("code") for reason in rating.refer_reasons}


def _for_enrichment(extraction) -> ExtractedApplication:
    """Only what `enrich` reads: name, number, and the years it checks incorporation against.

    `annual_revenue_gbp` is deliberately absent. Rebuilding it would mean pence -> float pounds ->
    pence, which is the round trip the money rule exists to prevent, and enrichment never looks at
    it. Rating gets its numbers from `_for_rating` below, in storage units, untouched.
    """
    return ExtractedApplication(
        company_name=extraction.company_name,
        company_number=extraction.company_number,
        years_trading=(
            None if extraction.months_trading is None else extraction.months_trading / 12
        ),
        extraction_confidence=extraction.extraction_confidence,
    )


def _for_rating(extraction) -> Application:
    """Straight from the stored columns — no unit conversion, so no rounding to disagree about."""
    return Application(
        company_name=extraction.company_name,
        sector=extraction.sector,
        annual_revenue_pence=extraction.annual_revenue_pence,
        months_trading=extraction.months_trading,
        prior_claims_count=extraction.prior_claims_count,
        data_records_held=extraction.data_records_held,
        requested_limit=extraction.requested_limit,
        extraction_confidence=extraction.extraction_confidence,
        missing_fields=tuple(extraction.missing_fields),
    )


def require_recheckable(submission: Submission) -> None:
    """Deliberately narrow. This is not a re-run-the-pipeline button.

    Re-rating moves the premium, so anything a human or a customer has already been given an
    answer on is out of scope — an issued quote is a number somebody is holding.
    """
    # Quote first: it is the actual harm, and it names the reason an operator needs to hear. The
    # status check below is the broader invariant, not a restatement of this one.
    if submission.quote is not None:
        raise NotRecheckable("this submission already has a quote, and re-rating would move it")
    if submission.status is not SubmissionStatus.REFERRED:
        raise NotRecheckable(
            f"only a referred submission can be rechecked, and this one is {submission.status}"
        )
    if submission.rating is None:
        raise NotRecheckable("this submission was never rated, so there is nothing to recheck")
    if ReasonCode.CH_UNAVAILABLE not in _reason_codes(submission.rating):
        raise NotRecheckable(
            "this submission did not refer because Companies House was unreachable"
        )


async def recheck(
    session: AsyncSession,
    submission: Submission,
    ch_client: CompaniesHouseClient,
    *,
    actor_id: uuid.UUID,
) -> RecheckOutcome:
    require_recheckable(submission)

    rating = submission.rating
    decision_before = rating.decision
    premium_before = rating.indicative_premium_pence
    error_before = submission.enrichment.lookup_error if submission.enrichment else None

    extraction = submission.extraction
    outcome = await enrich(ch_client, _for_enrichment(extraction))

    # Updated in place, not inserted: both tables are unique on submission_id, so the previous
    # values live in the audit trail rather than in a second row.
    for column, value in outcome.orm_kwargs.items():
        setattr(submission.enrichment, column, value)

    try:
        result = rate(_for_rating(extraction), outcome.domain)
    except (TypeError, ValueError) as error:
        # Guarded by require_recheckable: a rated submission had every field rate() needs. If that
        # ever stops holding, a half-applied enrichment must not be what commits.
        await session.rollback()
        raise NotRecheckable(f"this submission can no longer be rated: {error}") from error

    for column, value in rating_to_orm_kwargs(result).items():
        setattr(rating, column, value)
    submission.status = STATUS_FOR_DECISION[result.decision]

    resolved = ReasonCode.CH_UNAVAILABLE not in {
        reason.get("code") for reason in rating.refer_reasons
    }
    await record_event(
        session,
        submission.id,
        AuditEventType.SUBMISSION_RECHECKED,
        AuditActor.OPS,
        {
            # Both sides, because the row now holds only the second one.
            "decision_before": decision_before.name,
            "decision_after": result.decision.name,
            "premium_before_pence": premium_before,
            "premium_after_pence": result.indicative_premium_pence,
            "lookup_error_before": error_before,
            "lookup_error_after": outcome.error,
            "resolved": resolved,
        },
        actor_id=actor_id,
    )
    await session.commit()

    # Same as the pipeline: AUTO_APPROVE with no quote is the priced-then-abandoned state D-030
    # exists to prevent, and a recheck can reach that decision just as the first rating can.
    if result.decision is Decision.AUTO_APPROVE:
        await issue_quote(session, submission)

    return RecheckOutcome(
        decision_before=decision_before,
        decision_after=result.decision,
        premium_before_pence=premium_before,
        premium_after_pence=result.indicative_premium_pence,
        resolved=resolved,
    )
