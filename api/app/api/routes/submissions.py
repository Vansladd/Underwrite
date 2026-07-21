import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import DbSession
from app.domain.enums import AuditActor, AuditEventType, SubmissionStatus
from app.models import Submission
from app.schemas import SubmissionCreate, SubmissionDetail, SubmissionRead
from app.services.audit import record_event
from app.services.pipeline import run_pipeline

router = APIRouter(prefix="/submissions", tags=["submissions"])

MAX_PAGE = 200

NESTED = (
    selectinload(Submission.extraction),
    selectinload(Submission.enrichment),
    selectinload(Submission.rating),
    selectinload(Submission.quote),
    selectinload(Submission.audit_events),
)


async def load_detail(db: DbSession, submission_id: uuid.UUID) -> Submission:
    submission = await db.scalar(
        select(Submission).where(Submission.id == submission_id).options(*NESTED)
    )
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no submission {submission_id}")
    return submission


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_submission(payload: SubmissionCreate, db: DbSession) -> SubmissionDetail:
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
    await run_pipeline(db, submission, payload.application)
    await db.commit()

    return SubmissionDetail.model_validate(await load_detail(db, submission.id))


@router.get("")
async def list_submissions(
    db: DbSession,
    submission_status: Annotated[SubmissionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SubmissionRead]:
    query = select(Submission).order_by(Submission.created_at.desc()).limit(limit).offset(offset)
    if submission_status is not None:
        query = query.where(Submission.status == submission_status)

    return [SubmissionRead.model_validate(each) for each in (await db.scalars(query)).all()]


@router.get("/{submission_id}")
async def get_submission(submission_id: uuid.UUID, db: DbSession) -> SubmissionDetail:
    return SubmissionDetail.model_validate(await load_detail(db, submission_id))
