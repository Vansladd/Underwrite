import pytest

from app.services.pdf_text import (
    MAX_TEXT_CHARS,
    MAX_UPLOAD_BYTES,
    EncryptedPdf,
    NotAPdf,
    NoTextLayer,
    PdfTooLarge,
    extract_text,
)
from tests.pdf_bytes import encrypted_pdf, scanned_pdf, text_pdf


def test_a_broker_submission_keeps_the_fields_the_extractor_reads():
    text = extract_text(text_pdf())

    assert "Acme Robotics Ltd" in text
    assert "09876543" in text
    assert "£2,500,000" in text


def test_blank_lines_are_collapsed_so_the_model_sees_prose_not_whitespace():
    text = extract_text(text_pdf("Insured: Example Ltd\n\n\n\nRequested limit: £1,000,000\n\n"))

    assert text == "Insured: Example Ltd\nRequested limit: £1,000,000"


def test_an_image_only_scan_is_rejected_rather_than_sent_to_the_model():
    with pytest.raises(NoTextLayer):
        extract_text(scanned_pdf())


def test_a_password_protected_pdf_is_rejected():
    with pytest.raises(EncryptedPdf):
        extract_text(encrypted_pdf())


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"Insured: Example Ltd, limit 1m, revenue 750k", id="plain text"),
        pytest.param(b"%PDF-1.7\nnot actually a pdf body", id="header only"),
        pytest.param(text_pdf()[:400], id="truncated pdf"),
    ],
)
def test_anything_pypdf_cannot_read_is_one_answer(data):
    with pytest.raises(NotAPdf):
        extract_text(data)


def test_an_oversized_upload_is_rejected_before_it_is_parsed():
    with pytest.raises(PdfTooLarge):
        extract_text(b"%PDF-1.7" + b"\0" * MAX_UPLOAD_BYTES)


def test_text_is_truncated_to_the_cap_that_bounds_the_anthropic_call():
    text = extract_text(text_pdf("Insured: Example Ltd. " * 1_200))

    assert len(text) == MAX_TEXT_CHARS
