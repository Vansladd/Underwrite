import sys
import uuid
from datetime import date, timedelta

import httpx

from app.config import get_settings
from app.models import Extraction, Quote, Rating, Submission
from app.services.pdf import build_renderer
from app.services.quote_pdf import build_quote_html
from app.services.storage import get_storage


def _canned_quote_html() -> str:
    # A transient (un-persisted) approved submission, so `make demo` renders the real template.
    today = date.today()
    submission = Submission(id=uuid.uuid4(), raw_input=None)
    submission.extraction = Extraction(company_name="Acme Robotics Ltd")
    submission.rating = Rating(
        rating_version="v1.0",
        base_premium_pence=90_000,
        indicative_premium_pence=171_000,
        annual_premium_pence=171_000,
        factors=[
            {"code": "LIMIT", "band_label": "£1,000,000", "multiplier": "1.9"},
            {"code": "REVENUE_BAND", "band_label": "£100k – £500k", "multiplier": "1.0"},
            {"code": "SECTOR", "band_label": "saas", "multiplier": "1.0"},
        ],
    )
    submission.quote = Quote(
        quote_ref="Q-2026-DEMO01",
        limit_pence=100_000_000,
        excess_pence=250_000,
        gross_premium_pence=171_000,
        inception_date=today,
        valid_until=today + timedelta(days=30),
    )
    return build_quote_html(submission)


def main() -> int:
    settings = get_settings()
    base = settings.quote_base_url.rstrip("/")

    # Render the real quote template (no LLM, no AWS), then prove it serves through the gated
    # documents route with a real session cookie (UW-019).
    renderer = build_renderer(settings, get_storage())
    key = renderer.render_and_store("demo-quote", _canned_quote_html())
    print(f"rendered + stored {key} (LOCAL_PDF={settings.local_pdf})")

    with httpx.Client(base_url=base, timeout=10) as client:
        login = client.post(
            "/api/auth/login",
            json={
                "username": settings.seed_operator_username,
                "password": settings.seed_operator_password,
            },
        )
        if login.status_code == 401:
            raise SystemExit("login failed — run `make seed` to create the demo operator first")
        login.raise_for_status()

        pdf = client.get(f"/api/documents/{key}")
        pdf.raise_for_status()
        if pdf.content[:4] != b"%PDF":
            raise SystemExit("served document is not a PDF")

    print(f"OK - {len(pdf.content)} byte PDF at {base}/api/documents/{key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
