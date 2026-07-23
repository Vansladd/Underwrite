import uuid
from datetime import date, timedelta

from app.domain.enums import QuoteStatus
from app.models import Quote, Submission

EXCESS_PENCE = 250_000  # £2,500 standing excess. See RATING_SPEC / UW-037.
VALIDITY_DAYS = 30


class NotQuotable(ValueError):
    """The submission has no bound premium or limit to quote against."""


def build_quote(submission: Submission, *, today: date) -> Quote:
    rating = submission.rating
    extraction = submission.extraction
    # DECLINE ⟺ annual_premium_pence is None (RATING_SPEC); an incomplete extraction has no rating.
    if rating is None or rating.annual_premium_pence is None:
        raise NotQuotable("no bound premium to quote")
    if extraction is None or extraction.requested_limit is None:
        raise NotQuotable("no requested limit to quote")
    return Quote(
        submission_id=submission.id,
        quote_ref=_quote_ref(today),
        status=QuoteStatus.ISSUED,
        limit_pence=extraction.requested_limit.pence,
        excess_pence=EXCESS_PENCE,
        gross_premium_pence=rating.annual_premium_pence,
        inception_date=today,
        valid_until=today + timedelta(days=VALIDITY_DAYS),
    )


def _quote_ref(today: date) -> str:
    return f"Q-{today.year}-{uuid.uuid4().hex[:6].upper()}"
