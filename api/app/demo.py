import sys

import httpx

from app.config import get_settings
from app.services.pdf import build_renderer
from app.services.storage import get_storage

QUOTE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><style>
  body { font-family: "DejaVu Sans", sans-serif; margin: 2cm; color: #111; }
  h1 { font-size: 22pt; }
  .muted { color: #666; }
  table { border-collapse: collapse; margin-top: 1cm; }
  td { padding: 4px 24px 4px 0; }
</style></head><body>
  <h1>Underwrite &mdash; Indicative Quote</h1>
  <p class="muted">Tech E&amp;O / Cyber &middot; specimen</p>
  <table>
    <tr><td>Insured</td><td>Acme Robotics Ltd</td></tr>
    <tr><td>Limit</td><td>&pound;1,000,000</td></tr>
    <tr><td>Excess</td><td>&pound;10,000</td></tr>
    <tr><td>Gross premium</td><td>&pound;4,250</td></tr>
  </table>
</body></html>"""


def main() -> int:
    settings = get_settings()
    base = settings.quote_base_url.rstrip("/")

    submission = httpx.post(
        f"{base}/api/submissions",
        json={"input_mode": "paste", "raw_input": "Acme Robotics Ltd - SaaS, GBP 1m limit"},
        timeout=10,
    )
    submission.raise_for_status()
    submission_id = submission.json()["id"]
    print(f"created submission {submission_id}")

    renderer = build_renderer(settings, get_storage())
    key = renderer.render_and_store(f"demo-{submission_id}", QUOTE_HTML)
    print(f"rendered + stored {key} (LOCAL_PDF={settings.local_pdf})")

    pdf = httpx.get(f"{base}/api/documents/{key}", timeout=10)
    pdf.raise_for_status()
    if pdf.content[:4] != b"%PDF":
        raise SystemExit("served document is not a PDF")

    print(f"OK - {len(pdf.content)} byte PDF at {base}/api/documents/{key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
