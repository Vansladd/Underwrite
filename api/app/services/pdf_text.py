from __future__ import annotations

import io
from collections.abc import Iterable
from typing import Any

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
        text = collapse_pages(reader.pages[:MAX_PAGES])
    except EncryptedPdf:
        raise
    except Exception as error:
        # Untrusted input: pypdf raises a wide family on malformed files, all one answer here.
        raise NotAPdf from error

    if len(text) < MIN_TEXT_CHARS:
        raise NoTextLayer
    return text


def collapse_pages(pages: Iterable[Any]) -> str:
    """Non-blank lines up to MAX_TEXT_CHARS, stopping as soon as the cap is reached.

    Joining every page first would decode the whole document into memory before truncating, and a
    flate-compressed PDF is small on disk and vast once decoded. One hostile page is still bounded
    only by pypdf. See D-028.
    """
    lines: list[str] = []
    total = 0
    for page in pages:
        for raw in (page.extract_text() or "").splitlines():
            line = raw.strip()
            if not line:
                continue
            lines.append(line)
            total += len(line) + 1
            if total >= MAX_TEXT_CHARS:
                return "\n".join(lines)[:MAX_TEXT_CHARS]
    return "\n".join(lines)
