from __future__ import annotations

import io

from pypdf import PdfReader

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PAGES = 30
# The extracted text goes straight into a paid Anthropic call; this bounds that spend.
MAX_TEXT_CHARS = 20_000
# Below this a "text layer" is stray artefacts, not a submission. See D-028.
MIN_TEXT_CHARS = 40


class PdfTextError(Exception):
    """Base for the ways an uploaded PDF fails to yield text.

    `str()` is a finished sentence: the route passes it straight to the applicant as the 4xx detail.
    """


class PdfTooLarge(PdfTextError):
    def __init__(self) -> None:
        super().__init__(f"That PDF is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.")


class NotAPdf(PdfTextError):
    def __init__(self) -> None:
        super().__init__("That file is not a readable PDF.")


class EncryptedPdf(PdfTextError):
    def __init__(self) -> None:
        super().__init__("That PDF is password-protected. Remove the password and try again.")


class NoTextLayer(PdfTextError):
    def __init__(self) -> None:
        super().__init__(
            "That PDF has no selectable text — it looks scanned. Paste the text instead."
        )


def extract_text(data: bytes) -> str:
    """Text of an uploaded PDF, or a PdfTextError naming what the applicant should do about it."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise PdfTooLarge
    if not data.startswith(b"%PDF-"):
        raise NotAPdf

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise EncryptedPdf
        pages = "\n".join(page.extract_text() or "" for page in reader.pages[:MAX_PAGES])
    except EncryptedPdf:
        raise
    except Exception as error:
        # Untrusted input: pypdf raises a wide family on malformed files, all one answer here.
        raise NotAPdf from error

    text = _collapse(pages)
    if len(text) < MIN_TEXT_CHARS:
        raise NoTextLayer
    return text[:MAX_TEXT_CHARS]


def _collapse(text: str) -> str:
    return "\n".join(line for line in (each.strip() for each in text.splitlines()) if line).strip()
