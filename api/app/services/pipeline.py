from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AuditActor, AuditEventType
from app.models import Extraction, Submission
from app.schemas import ExtractedApplication
from app.services.audit import record_event

FORM_MODEL = "form"


async def run_pipeline(
    session: AsyncSession,
    submission: Submission,
    application: ExtractedApplication | None,
) -> None:
    """Stub for UW-025. Form mode already has its fields, so only they are persisted."""
    if application is None:
        return

    session.add(Extraction(submission_id=submission.id, **application.to_orm_kwargs(FORM_MODEL)))
    await session.flush()
    await record_event(
        session,
        submission.id,
        AuditEventType.EXTRACTION_COMPLETED,
        AuditActor.APPLICANT,
        {"model": FORM_MODEL, "fields": sorted(application.model_fields_set)},
    )
