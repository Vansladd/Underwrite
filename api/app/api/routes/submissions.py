import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import ChClientDep, ExtractorDep, OpsUser
from app.db import DbSession
from app.domain.enums import AuditActor, AuditEventType, SubmissionStatus
from app.models import Submission
from app.schemas import SubmissionCreate, SubmissionDetail, SubmissionRead
from app.services.audit import record_event
from app.services.pipeline import run_pipeline

router = APIRouter(prefix="/api/submissions", tags=["submissions"])

MAX_PAGE = 200

NESTED = (
    selectinload(Submission.extraction),
    selectinload(Submission.enrichment),
    selectinload(Submission.rating),
    selectinload(Submission.quote),
    selectinload(Submission.audit_events),
)


async def load_detail(db: AsyncSession, submission_id: uuid.UUID) -> Submission:
    submission = await db.scalar(
        select(Submission).where(Submission.id == submission_id).options(*NESTED)
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
    ops: OpsUser,
    submission_status: Annotated[SubmissionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SubmissionRead]:
    query = submissions_query(submission_status, limit, offset)
    return list((await db.scalars(query)).all())


@router.get("/{submission_id}")
async def get_submission(submission_id: uuid.UUID, db: DbSession) -> SubmissionDetail:
    return await load_detail(db, submission_id)
