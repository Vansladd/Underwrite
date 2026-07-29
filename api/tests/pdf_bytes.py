from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfWriter

from app.services.pdf import data_only_url_fetcher

EMAILS = Path(__file__).resolve().parent / "fixtures" / "extraction" / "emails"

# 1x1 PNG stretched over the page: an image-only "scan", no text layer anywhere in the file.
PIXEL_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _render(body: str) -> bytes:
    # WeasyPrint, not a hand-rolled PDF: a real writer's compressed streams and subset fonts are
    # what pypdf meets in production.
    import weasyprint

    return weasyprint.HTML(
        string=f"<html><body>{body}</body></html>", url_fetcher=data_only_url_fetcher()
    ).write_pdf()


def broker_email(name: str = "clean") -> str:
    return (EMAILS / f"{name}.txt").read_text()


def text_pdf(text: str | None = None) -> bytes:
    lines = (text if text is not None else broker_email()).splitlines()
    return _render("".join(f"<p>{line}</p>" for line in lines if line.strip()))


def scanned_pdf() -> bytes:
    return _render(
        f'<img src="data:image/png;base64,{PIXEL_PNG}" style="width:400px;height:600px">'
    )


def encrypted_pdf() -> bytes:
    writer = PdfWriter(clone_from=io.BytesIO(text_pdf()))
    writer.encrypt("hunter2")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
