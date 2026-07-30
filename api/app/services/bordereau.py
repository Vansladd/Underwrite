import csv
import io
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.domain.enums import AuditActor, AuditEventType
from app.domain.money import pounds_csv
from app.domain.period import YearMonth
from app.models import Quote, Submission
from app.services.audit import record_event
from app.services.companies_house import normalise_company_number
from app.services.rating import MIN_NAME_MATCH_SCORE
from app.services.storage import DocumentStorage

COLUMNS = (
    "quote_ref",
    "insured_name",
    "company_number",
    "inception_date",
    "expiry_date",
    "limit",
    "excess",
    "gross_premium",
    "sector",
    "sic_codes",
    "rating_version",
)


@dataclass(frozen=True)
class BordereauExport:
    period: str
    s3_key: str
    quotes: int
    size_bytes: int


def storage_key(period: YearMonth) -> str:
    return f"bordereaux/{period}.csv"


async def export_bordereau(
    session: AsyncSession, storage: DocumentStorage, *, period: YearMonth
) -> BordereauExport:
    """Report every quote issued in the period, whatever became of it since.

    Keyed on `created_at`, not status: a quote issued in July and expired in August is still July's
    business, and a bordereau the carrier can reconcile must not retract it. See DECISIONS D-032.
    """
    quotes = await _issued_in(session, period)
    body = build_csv(quotes)
    key = storage_key(period)

    # Stored before the trail is written: an audited export that does not exist is the worse lie,
    # and a re-run overwrites the same key. put() blocks (boto3), so keep it off the event loop.
    await run_in_threadpool(storage.put, key, body, "text/csv")

    for quote in quotes:
        await record_event(
            session,
            quote.submission_id,
            AuditEventType.BORDEREAU_EXPORTED,
            AuditActor.SYSTEM,
            {"period": str(period), "s3_key": key, "quote_ref": quote.quote_ref},
        )
    await session.commit()

    return BordereauExport(str(period), key, len(quotes), len(body))


async def _issued_in(session: AsyncSession, period: YearMonth) -> list[Quote]:
    start, end = period.bounds()
    return list(
        await session.scalars(
            select(Quote)
            .where(Quote.created_at >= start, Quote.created_at < end)
            .order_by(Quote.created_at, Quote.quote_ref)
            .options(
                selectinload(Quote.submission).selectinload(Submission.extraction),
                selectinload(Quote.submission).selectinload(Submission.enrichment),
                selectinload(Quote.submission).selectinload(Submission.rating),
            )
        )
    )


def build_csv(quotes: list[Quote]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    writer.writerows(_row(quote) for quote in quotes)
    return buffer.getvalue().encode()


def _row(quote: Quote) -> list[str]:
    extraction = quote.submission.extraction
    enrichment = quote.submission.enrichment
    rating = quote.submission.rating
    return [
        quote.quote_ref,
        # The applicant's name, not the register's: it is who was quoted, and a poor name match
        # would otherwise silently report a different company than the one underwritten.
        (extraction.company_name if extraction else None) or "",
        _company_number(extraction, enrichment),
        quote.inception_date.isoformat(),
        quote.valid_until.isoformat(),
        pounds_csv(quote.limit_pence),
        pounds_csv(quote.excess_pence),
        pounds_csv(quote.gross_premium_pence),
        (extraction.sector.value if extraction and extraction.sector else ""),
        " ".join(enrichment.sic_codes or []) if enrichment else "",
        rating.rating_version if rating else "",
    ]


def _company_number(extraction, enrichment) -> str:
    """The number for the company in the name column beside it, never a different one.

    `lookup` falls back to a name search when no number was submitted, so the register's number can
    belong to a company nobody underwrote. Pairing that with the applicant's name gives a carrier a
    row whose two identifiers disagree, and nothing in the CSV says so. See DECISIONS D-032.
    """
    submitted = extraction.company_number if extraction else None
    if submitted:
        # Canonical form of what was underwritten. Where the register agrees this is its number
        # too; where it does not, the name column is still the applicant's.
        return normalise_company_number(submitted)

    # Nothing submitted, so the register hit came from a name search: trustworthy only if the name
    # actually matched. Below the threshold it names another company, and no number beats that.
    score = enrichment.ch_name_match_score if enrichment else None
    verified = enrichment.ch_company_number if enrichment else None
    if verified and score is not None and score >= MIN_NAME_MATCH_SCORE:
        return verified
    return ""
