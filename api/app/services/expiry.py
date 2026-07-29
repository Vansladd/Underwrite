from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AuditActor, AuditEventType, QuoteStatus
from app.models import Quote
from app.services.audit import record_event


async def expire_quotes(session: AsyncSession, *, today: date) -> list[str]:
    """Retire every live quote whose validity has passed, one audit event each.

    Idempotent by construction: the `issued` filter means a repeat run selects nothing. FOR UPDATE
    extends that to overlapping runs — the loser blocks, re-reads, and finds the rows no longer
    issued, so no quote is ever expired twice. See DECISIONS D-031.
    """
    stale = (
        await session.scalars(
            select(Quote)
            # valid_until is inclusive: a quote is live through that day and stale the day after.
            .where(Quote.status == QuoteStatus.ISSUED, Quote.valid_until < today)
            .order_by(Quote.valid_until, Quote.quote_ref)
            .with_for_update()
        )
    ).all()

    for quote in stale:
        quote.status = QuoteStatus.EXPIRED
        await record_event(
            session,
            quote.submission_id,
            AuditEventType.QUOTE_EXPIRED,
            AuditActor.SYSTEM,
            {"quote_ref": quote.quote_ref, "valid_until": quote.valid_until, "swept_on": today},
        )

    await session.commit()
    return [quote.quote_ref for quote in stale]
