import contextlib
import re
import uuid
import zlib
from datetime import date, timedelta

import pytest

from app.models import Extraction, Quote, Rating, Submission
from app.services.pdf import LocalPdfRenderer
from app.services.quote_pdf import FACTOR_NAMES, QuoteNotReady, build_quote_html
from app.services.rating import rate
from app.services.storage import LocalStorage
from tests.factories import STRIKE_OFF
from tests.rating_baseline import application


def _submission(company_name: str = "Ledgerline Capital Ltd") -> Submission:
    today = date(2026, 7, 23)
    submission = Submission(id=uuid.UUID("12f45bef-0000-4000-8000-000000000001"), raw_input=None)
    submission.extraction = Extraction(company_name=company_name)
    submission.rating = Rating(
        rating_version="v1.0",
        base_premium_pence=90_000,
        indicative_premium_pence=537_000,
        annual_premium_pence=537_000,
        factors=[
            {
                "code": "LIMIT",
                "band_label": "£2,000,000",
                "multiplier": "2.6",
                "premium_after_pence": "234000",
            },
            {
                "code": "REVENUE_BAND",
                "band_label": "£2m – £10m",
                "multiplier": "1.7",
                "premium_after_pence": "397800",
            },
            {
                "code": "SECTOR",
                "band_label": "fintech",
                "multiplier": "1.35",
                "premium_after_pence": "537030",
            },
        ],
    )
    submission.quote = Quote(
        quote_ref="Q-2026-7C22DA",
        limit_pence=200_000_000,
        excess_pence=250_000,
        gross_premium_pence=537_000,
        inception_date=today,
        valid_until=today + timedelta(days=30),
    )
    return submission


def test_quote_html_carries_the_required_strings():
    html = build_quote_html(_submission())

    assert "Ledgerline Capital Ltd" in html
    assert "Q-2026-7C22DA" in html
    assert "£2,000,000" in html  # limit
    assert "£2,500" in html  # excess
    assert "£5,370" in html  # gross premium (537000 pence) and the final running total
    assert "£900" in html  # base rate, running column
    assert "2026-08-22" in html  # inception + 30 days
    assert "SPECIMEN" in html
    assert "v1.0" in html
    assert "12f45bef" in html  # submission id
    # Band labels reach the PDF verbatim (RATING_SPEC / UW-011).
    assert "£2m – £10m" in html
    assert "fintech" in html


def test_quote_html_embeds_the_three_ibm_plex_faces():
    html = build_quote_html(_submission())

    assert html.count("@font-face") == 3
    assert "IBM Plex Sans" in html
    assert "IBM Plex Mono" in html
    assert "data:font/woff;base64," in html


def test_quote_html_escapes_the_insured_name():
    html = build_quote_html(_submission('Evil <script>alert("x")</script> Ltd'))

    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_factor_names_cover_every_code_the_engine_emits():
    # Guards the raw-code fallback: a new/renamed factor in the engine that isn't named here
    # would otherwise print its machine code on a customer quote.
    result = rate(application(), STRIKE_OFF)

    for factor in result.factors:
        assert factor.code in FACTOR_NAMES, f"unnamed factor code: {factor.code}"


def test_build_quote_html_needs_a_quote():
    submission = Submission(id=uuid.uuid4(), raw_input=None)
    submission.extraction = Extraction(company_name="Unapproved Ltd")

    with pytest.raises(QuoteNotReady):
        build_quote_html(submission)


def test_quote_html_renders_to_a_valid_pdf(tmp_path):
    storage = LocalStorage(tmp_path, "http://testserver")

    key = LocalPdfRenderer(storage).render_and_store("q-quote", build_quote_html(_submission()))

    pdf = storage.read(key)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 5000


def _inflated_streams(pdf: bytes) -> bytes:
    out = b""
    for blob in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.DOTALL):
        with contextlib.suppress(zlib.error):
            out += zlib.decompress(blob)
    return out


def test_the_pdf_embeds_the_bundled_fonts_not_a_fallback(tmp_path):
    # Subsetting strips the plain-text font name, so assert on the fallback signal instead:
    # at least one embedded font program and no DejaVu. A broken font data: URI flips WeasyPrint
    # to its DejaVu fallback, which this catches (verified by mutation).
    storage = LocalStorage(tmp_path, "http://testserver")
    key = LocalPdfRenderer(storage).render_and_store("q-fonts", build_quote_html(_submission()))

    body = _inflated_streams(storage.read(key))
    assert b"FontFile" in body  # an embedded program (FontFile2 for TrueType, FontFile3 for CFF)
    assert b"DejaVu" not in body
