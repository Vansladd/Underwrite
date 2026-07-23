from __future__ import annotations

from base64 import b64encode
from functools import cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.domain.money import format_gbp, format_gbp_round
from app.models import Submission

_HERE = Path(__file__).parent
_FONTS = _HERE / "fonts"

# Machine codes → the underwriter-facing factor names, mirroring the drawer's FACTOR_LABELS.
FACTOR_NAMES = {
    "LIMIT": "Limit",
    "REVENUE_BAND": "Revenue band",
    "SECTOR": "Sector",
    "DATA_VOLUME": "Data volume",
    "CLAIMS_HISTORY": "Claims history",
    "MONTHS_TRADING": "Months trading",
}


class QuoteNotReady(ValueError):
    """The submission has no quote/rating/extraction to render."""


@cache
def _font_uri(filename: str) -> str:
    # woff, not woff2: zlib decompression is always available; woff2 would need brotli.
    encoded = b64encode((_FONTS / filename).read_bytes()).decode()
    return f"data:font/woff;base64,{encoded}"


@cache
def _env() -> Environment:
    # autoescape=True unconditionally: the insured name is LLM-extracted, never trusted HTML.
    return Environment(loader=FileSystemLoader(_HERE / "templates"), autoescape=True)


def build_quote_html(submission: Submission) -> str:
    quote = submission.quote
    rating = submission.rating
    extraction = submission.extraction
    if quote is None or rating is None or extraction is None:
        raise QuoteNotReady("submission is not approved into a quote")

    # rating.factors is JSONB (list of dicts); multiplier/premium are Decimal strings (D-004).
    # running rounds to whole pounds (intermediate premiums carry fractional pence).
    factors = [
        {
            "name": FACTOR_NAMES.get(factor["code"], factor["code"]),
            "band_label": factor["band_label"],
            "multiplier": factor["multiplier"],
            "running": format_gbp_round(factor["premium_after_pence"]),
        }
        for factor in rating.factors
    ]
    return (
        _env()
        .get_template("quote.html.jinja")
        .render(
            insured=extraction.company_name or "Unnamed insured",
            quote_ref=quote.quote_ref,
            limit=format_gbp(quote.limit_pence),
            excess=format_gbp(quote.excess_pence),
            premium=format_gbp(quote.gross_premium_pence),
            base_premium=format_gbp(rating.base_premium_pence),
            inception=quote.inception_date.isoformat(),
            valid_until=quote.valid_until.isoformat(),
            rating_version=rating.rating_version,
            submission_id=str(submission.id),
            factors=factors,
            fonts={
                "sans_400": _font_uri("ibm-plex-sans-400.woff"),
                "sans_600": _font_uri("ibm-plex-sans-600.woff"),
                "mono_400": _font_uri("ibm-plex-mono-400.woff"),
            },
        )
    )
