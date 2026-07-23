import logging

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.domain.enums import AuditActor, AuditEventType
from app.models import Submission
from app.services.audit import record_event
from app.services.pdf import PdfRenderer
from app.services.quote_pdf import build_quote_html

log = logging.getLogger("uvicorn.error")


async def generate_quote_pdf(
    db: AsyncSession, submission: Submission, renderer: PdfRenderer
) -> str | None:
    """Render the quote PDF, store it, and record it. Best-effort: a render failure leaves
    pdf_s3_key null and never propagates, so an approval is not lost because rendering failed
    (UW-052). Returns the stored key, or None on failure. Needs quote/rating/extraction loaded."""
    quote = submission.quote
    if quote is None:
        return None

    html = build_quote_html(submission)
    try:
        # render_and_store blocks (Lambda invoke / WeasyPrint); keep it off the event loop.
        key = await run_in_threadpool(renderer.render_and_store, quote.quote_ref, html)
    except Exception as exc:  # noqa: BLE001 — render is best-effort; the approval must survive.
        log.warning("quote render failed for %s: %s", quote.quote_ref, exc)
        await record_event(
            db,
            submission.id,
            AuditEventType.QUOTE_RENDER_FAILED,
            AuditActor.SYSTEM,
            {"quote_ref": quote.quote_ref, "error": str(exc)},
        )
        await db.commit()
        return None

    quote.pdf_s3_key = key
    await record_event(
        db,
        submission.id,
        AuditEventType.QUOTE_GENERATED,
        AuditActor.SYSTEM,
        {"quote_ref": quote.quote_ref, "pdf_s3_key": key},
    )
    await db.commit()
    return key
