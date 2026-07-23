import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import ChClientDep, CurrentUser, ExtractorDep
from app.db import DbSession
from app.domain.enums import AuditActor, AuditEventType, SubmissionStatus
from app.models import AuditEvent, Submission
from app.schemas import (
    DeclineRequest,
    SubmissionCreate,
    SubmissionDetail,
    SubmissionListItem,
    SubmissionStats,
)
from app.services.audit import record_event
from app.services.pipeline import run_pipeline
from app.services.quote import NotQuotable, build_quote

router = APIRouter(prefix="/api/submissions", tags=["submissions"])

MAX_PAGE = 200

NESTED = (
    selectinload(Submission.extraction),
    selectinload(Submission.enrichment),
    selectinload(Submission.rating),
    selectinload(Submission.quote),
    # operator too: the timeline names the underwriter, not just the role (D-026).
    selectinload(Submission.audit_events).selectinload(AuditEvent.operator),
)

# The list needs the three the queue row reads; not quote/audit_events.
LIST_NESTED = (
    selectinload(Submission.extraction),
    selectinload(Submission.rating),
    selectinload(Submission.enrichment),
)


_FIELD_LABELS = {
    "annual_revenue_gbp": "Annual revenue",
    "years_trading": "Years trading",
    "prior_claims_count": "Prior claims",
    "requested_limit_gbp": "Requested limit",
    "data_records_held": "Data volume",
    "sector": "Sector",
    "company_name": "Company name",
}


def _headline(submission: Submission) -> str | None:
    """The one reason the operator sees before opening the row."""
    rating = submission.rating
    if rating is not None:
        if rating.decline_reasons:
            return rating.decline_reasons[0]["message"]
        if rating.refer_reasons:
            return rating.refer_reasons[0]["message"]
        if submission.enrichment is not None and submission.enrichment.ch_found:
            return "Companies House matched, active"
        return None
    extraction = submission.extraction
    if extraction is not None and extraction.missing_fields:
        field = extraction.missing_fields[0]
        return f"{_FIELD_LABELS.get(field, field)} not stated"
    return None


def _to_list_item(submission: Submission) -> SubmissionListItem:
    extraction = submission.extraction
    rating = submission.rating
    return SubmissionListItem(
        id=submission.id,
        status=submission.status,
        input_mode=submission.input_mode,
        created_at=submission.created_at,
        company_name=extraction.company_name if extraction else None,
        company_number=extraction.company_number if extraction else None,
        sector=extraction.sector if extraction else None,
        annual_revenue_pence=extraction.annual_revenue_pence if extraction else None,
        requested_limit=extraction.requested_limit if extraction else None,
        premium_pence=rating.annual_premium_pence if rating else None,
        decision=rating.decision if rating else None,
        headline=_headline(submission),
    )


async def load_detail(db: AsyncSession, submission_id: uuid.UUID) -> Submission:
    # populate_existing: after approve/decline mutates in-session, refresh the eager relationships
    # (quote, audit_events) rather than returning the stale versions loaded before the write.
    submission = await db.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(*NESTED)
        .execution_options(populate_existing=True)
    )
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no submission {submission_id}")
    return submission


def submissions_query(submission_status: SubmissionStatus | None, limit: int, offset: int):
    # id breaks ties: LIMIT/OFFSET over equal timestamps can repeat or skip a row.
    query = (
        select(Submission)
        .order_by(Submission.created_at.desc(), Submission.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if submission_status is None:
        return query
    return query.where(Submission.status == submission_status)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_submission(
    payload: SubmissionCreate,
    db: DbSession,
    user: CurrentUser,
    extractor: ExtractorDep,
    ch_client: ChClientDep,
) -> SubmissionDetail:
    submission = Submission(input_mode=payload.input_mode, raw_input=payload.raw_input)
    db.add(submission)
    await db.flush()

    # References, not copies: raw_input is already a column. See DECISIONS D-010.
    await record_event(
        db,
        submission.id,
        AuditEventType.SUBMISSION_RECEIVED,
        AuditActor.APPLICANT,
        {
            "input_mode": payload.input_mode.value,
            "raw_input_chars": len(payload.raw_input or ""),
        },
    )
    # Committed before the pipeline so a stage failure leaves it recoverable (UW-025).
    await db.commit()

    # The pipeline commits after each stage; no trailing commit needed here.
    await run_pipeline(db, submission, payload.application, extractor, ch_client)

    return await load_detail(db, submission.id)


@router.get("")
async def list_submissions(
    db: DbSession,
    user: CurrentUser,
    submission_status: Annotated[SubmissionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SubmissionListItem]:
    query = submissions_query(submission_status, limit, offset).options(*LIST_NESTED)
    return [_to_list_item(each) for each in (await db.scalars(query)).all()]


# Before /{submission_id}: "stats" is not a UUID and would 422 against the detail route.
@router.get("/stats")
async def submission_stats(db: DbSession, user: CurrentUser) -> SubmissionStats:
    rows = (
        await db.execute(select(Submission.status, func.count()).group_by(Submission.status))
    ).all()
    by_status = {status.value: count for status, count in rows}
    return SubmissionStats(total=sum(by_status.values()), by_status=by_status)


@router.get("/{submission_id}")
async def get_submission(
    submission_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> SubmissionDetail:
    return await load_detail(db, submission_id)


def _require_referred(submission: Submission, action: str) -> None:
    # Only a referral is an operator's to decide; anything else is already terminal.
    if submission.status is not SubmissionStatus.REFERRED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cannot {action} a {submission.status.value} submission",
        )


@router.post("/{submission_id}/approve")
async def approve_submission(
    submission_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> SubmissionDetail:
    # Only the two relations build_quote reads; the full detail is loaded once, after the write.
    submission = await db.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(selectinload(Submission.rating), selectinload(Submission.extraction))
    )
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no submission {submission_id}")
    _require_referred(submission, "approve")
    try:
        quote = build_quote(submission, today=date.today())
    except NotQuotable as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    db.add(quote)
    submission.status = SubmissionStatus.QUOTED
    try:
        # record_event flushes, so a racing approve's duplicate quote fails here, not at commit.
        await record_event(
            db,
            submission.id,
            AuditEventType.SUBMISSION_APPROVED,
            AuditActor.OPS,
            {"quote_ref": quote.quote_ref, "gross_premium_pence": quote.gross_premium_pence},
            actor_id=user.id,
        )
        await db.commit()
    except IntegrityError as exc:
        # A concurrent approve won the race and already quoted this submission (quote unique key).
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "submission already has a quote") from exc
    return await load_detail(db, submission.id)


@router.post("/{submission_id}/decline")
async def decline_submission(
    submission_id: uuid.UUID, payload: DeclineRequest, db: DbSession, user: CurrentUser
) -> SubmissionDetail:
    submission = await db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no submission {submission_id}")
    _require_referred(submission, "decline")

    submission.status = SubmissionStatus.DECLINED
    await record_event(
        db,
        submission.id,
        AuditEventType.SUBMISSION_DECLINED,
        AuditActor.OPS,
        {"reason": payload.reason},
        actor_id=user.id,
    )
    await db.commit()
    return await load_detail(db, submission.id)
