import json
import uuid

import pytest
from sqlalchemy import func, select

from app.api.routes.submissions import submissions_query
from app.db import get_db
from app.domain.enums import AuditEventType, DataVolume, RequestedLimit, Sector
from app.main import app
from app.models import AuditEvent, Extraction, Submission
from app.services.pdf_text import MAX_UPLOAD_BYTES
from tests.factories import make_full_submission, make_submission
from tests.pdf_bytes import encrypted_pdf, scanned_pdf, text_pdf

BROKER_EMAIL = "Please quote Example Ltd for £1m cyber cover. Turnover £750k, trading 3 years."

FORM_APPLICATION = {
    "company_name": "Example Ltd",
    "sector": Sector.SAAS.value,
    "annual_revenue_gbp": 750_000.0,
    "years_trading": 3.0,
    "prior_claims_count": 0,
    "data_records_held": DataVolume.HUNDRED_K_TO_1M.value,
    "requested_limit_gbp": RequestedLimit.GBP_1M.value,
}


async def test_route_tests_run_on_the_test_transaction(api, db):
    # TestClient builds its own engine from Settings and would write to the dev database.
    assert app.dependency_overrides[get_db]() is db


async def test_pasting_a_broker_email_creates_a_submission(api):
    response = await api.post(
        "/api/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["input_mode"] == "paste"
    assert body["raw_input"] == BROKER_EMAIL
    # Paste runs the whole pipeline: extracted, enriched, rated. CH not found -> referred.
    assert body["status"] == "referred"
    assert body["extraction"]["company_name"] == "Example Ltd"
    assert body["rating"]["decision"] == "REFER"
    # Quote generation is a later, ops-gated step (UW-036); the pipeline stops at rating.
    assert body["quote"] is None
    assert uuid.UUID(body["id"])


async def test_a_new_submission_starts_its_audit_trail(api, db):
    response = await api.post(
        "/api/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL}
    )

    events = (
        await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.submission_id == uuid.UUID(response.json()["id"]))
            .order_by(AuditEvent.occurred_at)
        )
    ).all()

    assert [each.event_type for each in events] == [
        AuditEventType.SUBMISSION_RECEIVED,
        AuditEventType.EXTRACTION_COMPLETED,
        AuditEventType.ENRICHMENT_COMPLETED,
        AuditEventType.RATING_COMPLETED,
    ]
    assert events[0].payload == {
        "input_mode": "paste",
        "raw_input_chars": len(BROKER_EMAIL),
    }


async def test_the_audit_payload_references_the_email_rather_than_copying_it(api, db):
    response = await api.post(
        "/api/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL}
    )
    event = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.submission_id == uuid.UUID(response.json()["id"]),
            AuditEvent.event_type == AuditEventType.SUBMISSION_RECEIVED,
        )
    )

    # An append-only payload is the one place personal data cannot be redacted (D-010).
    assert BROKER_EMAIL not in str(event.payload)


async def test_a_form_submission_persists_its_fields_in_storage_units(api, db):
    response = await api.post(
        "/api/submissions", json={"input_mode": "form", "application": FORM_APPLICATION}
    )

    assert response.status_code == 201
    extraction = await db.scalar(
        select(Extraction).where(Extraction.submission_id == uuid.UUID(response.json()["id"]))
    )

    assert extraction.annual_revenue_pence == 75_000_000
    assert extraction.months_trading == 36
    assert extraction.sector is Sector.SAAS
    assert extraction.requested_limit is RequestedLimit.GBP_1M
    assert extraction.model == "form"


async def test_a_form_submission_is_returned_with_its_extraction_nested(api):
    response = await api.post(
        "/api/submissions", json={"input_mode": "form", "application": FORM_APPLICATION}
    )

    extraction = response.json()["extraction"]
    assert extraction["company_name"] == "Example Ltd"
    assert extraction["annual_revenue_pence"] == 75_000_000


async def test_a_form_submission_records_extraction_in_the_trail(api, db):
    response = await api.post(
        "/api/submissions", json={"input_mode": "form", "application": FORM_APPLICATION}
    )

    events = (
        await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.submission_id == uuid.UUID(response.json()["id"]))
            .order_by(AuditEvent.occurred_at)
        )
    ).all()

    assert [each.event_type for each in events] == [
        AuditEventType.SUBMISSION_RECEIVED,
        AuditEventType.EXTRACTION_COMPLETED,
        AuditEventType.ENRICHMENT_COMPLETED,
        AuditEventType.RATING_COMPLETED,
    ]


async def test_a_form_submission_is_certain_by_construction(api, db, fake_extractor):
    response = await api.post(
        "/api/submissions", json={"input_mode": "form", "application": FORM_APPLICATION}
    )

    extraction = await db.scalar(
        select(Extraction).where(Extraction.submission_id == uuid.UUID(response.json()["id"]))
    )

    assert extraction.extraction_confidence == 1.0
    assert extraction.missing_fields == []
    assert fake_extractor.calls == []


async def test_a_form_submission_cannot_claim_its_own_confidence(api, db):
    response = await api.post(
        "/api/submissions",
        json={
            "input_mode": "form",
            "application": {**FORM_APPLICATION, "extraction_confidence": 0.2},
        },
    )

    assert response.status_code == 422
    assert await db.scalar(select(func.count()).select_from(Submission)) == 0


# --- pdf upload (UW-026) -------------------------------------------------------------------


def _upload(data: bytes, filename: str = "submission.pdf"):
    return {"file": (filename, data, "application/pdf")}


async def test_an_uploaded_pdf_flows_through_the_same_pipeline_to_a_rating(api, fake_extractor):
    response = await api.post("/api/submissions/pdf", files=_upload(text_pdf()))

    assert response.status_code == 201
    body = response.json()
    assert body["input_mode"] == "pdf_upload"
    # The parsed text is the submission: it is what the model saw and what the trail preserves.
    assert "Acme Robotics Ltd" in body["raw_input"]
    assert fake_extractor.calls == [body["raw_input"]]
    assert body["rating"] is not None


async def test_an_uploaded_pdf_records_the_filename_it_arrived_under(api, db):
    response = await api.post("/api/submissions/pdf", files=_upload(text_pdf(), "acme quote.pdf"))

    event = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.submission_id == uuid.UUID(response.json()["id"]),
            AuditEvent.event_type == AuditEventType.SUBMISSION_RECEIVED,
        )
    )

    assert event.payload["filename"] == "acme quote.pdf"
    assert event.payload["upload_bytes"] > 0


async def test_the_extracted_text_is_labelled_as_coming_from_a_pdf(api, db):
    response = await api.post("/api/submissions/pdf", files=_upload(text_pdf()))

    event = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.submission_id == uuid.UUID(response.json()["id"]),
            AuditEvent.event_type == AuditEventType.EXTRACTION_COMPLETED,
        )
    )

    assert event.payload["source"] == "uploaded_pdf"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        pytest.param(scanned_pdf(), "no selectable text", id="image-only scan"),
        pytest.param(encrypted_pdf(), "password-protected", id="encrypted"),
        pytest.param(b"just some text", "not a readable PDF", id="not a pdf"),
    ],
)
async def test_an_unreadable_pdf_is_refused_with_a_reason_and_stores_nothing(
    api, db, fake_extractor, data, expected
):
    response = await api.post("/api/submissions/pdf", files=_upload(data))

    assert response.status_code == 422
    assert expected in response.json()["detail"]
    assert await db.scalar(select(func.count()).select_from(Submission)) == 0
    # The point of the gate: an unreadable upload never reaches a paid extraction call.
    assert fake_extractor.calls == []


async def test_an_oversized_upload_is_refused(api, db):
    oversized = b"%PDF-1.7" + b"\0" * (MAX_UPLOAD_BYTES + 1)

    response = await api.post("/api/submissions/pdf", files=_upload(oversized))

    assert response.status_code == 413
    assert await db.scalar(select(func.count()).select_from(Submission)) == 0


async def test_an_oversized_body_is_refused_before_it_is_read(api):
    # httpx sends Content-Length, so this never reaches the route or the multipart parser.
    response = await api.post(
        "/api/submissions",
        content=b"x" * (MAX_UPLOAD_BYTES + 1),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert "larger than" in response.json()["detail"]


async def test_a_chunked_oversized_body_is_refused_too(api):
    # No Content-Length at all: an async iterator makes httpx stream it. A header check alone would
    # wave this through to the multipart parser, which spools the whole thing to disk first.
    async def stream():
        for _ in range(11):
            yield b"x" * (1024 * 1024)

    response = await api.post(
        "/api/submissions", content=stream(), headers={"content-type": "application/json"}
    )

    assert response.status_code == 413
    assert "larger than" in response.json()["detail"]


async def test_a_chunked_body_under_the_cap_still_gets_through(api):
    async def stream():
        yield json.dumps({"input_mode": "paste", "raw_input": BROKER_EMAIL}).encode()

    response = await api.post(
        "/api/submissions", content=stream(), headers={"content-type": "application/json"}
    )

    assert response.status_code == 201


async def test_an_ordinary_body_passes_the_size_gate(api):
    response = await api.post(
        "/api/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL}
    )

    assert response.status_code == 201


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"input_mode": "paste"}, "pasted submissions must carry raw_input"),
        ({"input_mode": "form"}, "form submissions must carry an application"),
        ({"input_mode": "pdf_upload"}, "/api/submissions/pdf"),
        ({"input_mode": "telepathy", "raw_input": "hi"}, "input_mode"),
        ({"raw_input": "hi"}, "input_mode"),
    ],
)
async def test_an_invalid_submission_is_rejected_not_stored(api, db, payload, expected):
    response = await api.post("/api/submissions", json=payload)

    assert response.status_code == 422
    assert expected in response.text
    assert await db.scalar(select(func.count()).select_from(Submission)) == 0


# --- reading -------------------------------------------------------------------------------


async def test_the_queue_row_carries_the_scannable_fields(api, db):
    submission = await make_full_submission(db)

    rows = (await api.get("/api/submissions")).json()
    row = next(each for each in rows if each["id"] == str(submission.id))

    assert row["company_name"] == "Example Ltd"
    assert row["sector"] == "saas"
    assert row["decision"] == "REFER"
    assert row["premium_pence"] is not None
    # The one reason previewed in the row (a strike-off discrepancy here).
    assert "strike" in row["headline"].lower()


async def test_stats_counts_the_whole_table_not_just_a_page(api, db):
    await make_full_submission(db)  # referred
    await make_submission(db, status="declined")
    await make_submission(db, status="declined")

    stats = (await api.get("/api/submissions/stats")).json()

    assert stats["total"] == 3
    assert stats["by_status"] == {"referred": 1, "declined": 2}


async def test_listing_returns_newest_first(api):
    written = [
        (
            await api.post(
                "/api/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL}
            )
        ).json()["id"]
        for _ in range(3)
    ]

    listed = [each["id"] for each in (await api.get("/api/submissions")).json()]

    # Identity, not timestamps: three rows sharing a created_at compare equal to their own sort.
    assert listed == list(reversed(written))


async def test_rows_written_together_still_get_distinct_timestamps(api):
    body = [
        (
            await api.post(
                "/api/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL}
            )
        ).json()["created_at"]
        for _ in range(3)
    ]

    # now() would give all three the transaction timestamp. See DECISIONS D-011.
    assert len(set(body)) == 3


async def test_listing_filters_by_status(api, db):
    await make_submission(db, status="referred")
    await make_submission(db, status="received")

    referred = (await api.get("/api/submissions", params={"status": "referred"})).json()
    received = (await api.get("/api/submissions", params={"status": "received"})).json()

    assert [each["status"] for each in referred] == ["referred"]
    assert [each["status"] for each in received] == ["received"]


async def test_listing_rejects_an_unknown_status(api):
    response = await api.get("/api/submissions", params={"status": "vibes"})

    assert response.status_code == 422


async def test_listing_is_bounded(api):
    assert (await api.get("/api/submissions", params={"limit": 201})).status_code == 422
    assert (await api.get("/api/submissions", params={"limit": 0})).status_code == 422
    assert (await api.get("/api/submissions", params={"limit": 200})).status_code == 200


def test_the_listing_query_breaks_timestamp_ties():
    # Structural: Postgres returns tied rows stably here, so a paging test proves nothing.
    compiled = str(submissions_query(None, 50, 0))

    assert "ORDER BY submissions.created_at DESC, submissions.id DESC" in compiled


async def test_listing_pages(api):
    for _ in range(3):
        await api.post("/api/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL})

    first = (await api.get("/api/submissions", params={"limit": 2})).json()
    second = (await api.get("/api/submissions", params={"limit": 2, "offset": 2})).json()

    assert len(first) == 2
    assert len(second) == 1
    assert {each["id"] for each in first}.isdisjoint({each["id"] for each in second})


async def test_reading_one_submission_nests_its_relations(api, db):
    submission = await make_submission(db)

    body = (await api.get(f"/api/submissions/{submission.id}")).json()

    assert body["id"] == str(submission.id)
    assert set(body) >= {"extraction", "enrichment", "rating", "quote", "audit_events"}


async def test_an_unknown_submission_is_not_found(api):
    missing = uuid.uuid4()

    response = await api.get(f"/api/submissions/{missing}")

    assert response.status_code == 404
    assert str(missing) in response.json()["detail"]


async def test_a_malformed_id_is_rejected_before_the_database(api):
    response = await api.get("/api/submissions/not-a-uuid")

    assert response.status_code == 422


async def test_the_created_submission_is_readable_by_id(api):
    created = (
        await api.post("/api/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL})
    ).json()

    fetched = (await api.get(f"/api/submissions/{created['id']}")).json()

    assert fetched == created
