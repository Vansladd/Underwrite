import uuid

import pytest
from sqlalchemy import select

from app.db import get_db
from app.domain.enums import AuditEventType, DataVolume, RequestedLimit, Sector
from app.main import app
from app.models import AuditEvent, Extraction
from tests.factories import make_submission

BROKER_EMAIL = "Please quote Example Ltd for £1m cyber cover. Turnover £750k, trading 3 years."

FORM_APPLICATION = {
    "company_name": "Example Ltd",
    "sector": Sector.SAAS.value,
    "annual_revenue_gbp": 750_000.0,
    "years_trading": 3.0,
    "prior_claims_count": 0,
    "data_records_held": DataVolume.HUNDRED_K_TO_1M.value,
    "requested_limit_gbp": RequestedLimit.GBP_1M.value,
    "extraction_confidence": 1.0,
}


async def test_route_tests_run_on_the_test_transaction(api, db):
    # TestClient builds its own engine from Settings and would write to the dev database.
    assert app.dependency_overrides[get_db]() is db


async def test_pasting_a_broker_email_creates_a_submission(api):
    response = await api.post(
        "/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "received"
    assert body["input_mode"] == "paste"
    assert body["raw_input"] == BROKER_EMAIL
    assert (body["extraction"], body["rating"], body["quote"]) == (None, None, None)
    assert uuid.UUID(body["id"])


async def test_a_new_submission_starts_its_audit_trail(api, db):
    response = await api.post(
        "/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL}
    )

    events = (
        await db.scalars(
            select(AuditEvent).where(AuditEvent.submission_id == uuid.UUID(response.json()["id"]))
        )
    ).all()

    assert [each.event_type for each in events] == [AuditEventType.SUBMISSION_RECEIVED]
    assert events[0].payload == {
        "input_mode": "paste",
        "raw_input_chars": len(BROKER_EMAIL),
    }


async def test_the_audit_payload_references_the_email_rather_than_copying_it(api, db):
    response = await api.post(
        "/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL}
    )
    event = await db.scalar(
        select(AuditEvent).where(AuditEvent.submission_id == uuid.UUID(response.json()["id"]))
    )

    # An append-only payload is the one place personal data cannot be redacted (D-010).
    assert BROKER_EMAIL not in str(event.payload)


async def test_a_form_submission_persists_its_fields_in_storage_units(api, db):
    response = await api.post(
        "/submissions", json={"input_mode": "form", "application": FORM_APPLICATION}
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
        "/submissions", json={"input_mode": "form", "application": FORM_APPLICATION}
    )

    extraction = response.json()["extraction"]
    assert extraction["company_name"] == "Example Ltd"
    assert extraction["annual_revenue_pence"] == 75_000_000


async def test_a_form_submission_records_extraction_in_the_trail(api, db):
    response = await api.post(
        "/submissions", json={"input_mode": "form", "application": FORM_APPLICATION}
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
    ]


async def test_a_pdf_upload_needs_no_text_yet(api):
    response = await api.post("/submissions", json={"input_mode": "pdf_upload"})

    assert response.status_code == 201
    assert response.json()["raw_input"] is None


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"input_mode": "paste"}, "pasted submissions must carry raw_input"),
        ({"input_mode": "form"}, "form submissions must carry an application"),
        ({"input_mode": "telepathy", "raw_input": "hi"}, "input_mode"),
        ({"raw_input": "hi"}, "input_mode"),
    ],
)
async def test_an_invalid_submission_is_rejected_not_stored(api, payload, expected):
    response = await api.post("/submissions", json=payload)

    assert response.status_code == 422
    assert expected in response.text


# --- reading -------------------------------------------------------------------------------


async def test_listing_returns_newest_first(api, db):
    for _ in range(3):
        await api.post("/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL})

    body = (await api.get("/submissions")).json()
    created = [each["created_at"] for each in body]

    assert len(body) == 3
    assert created == sorted(created, reverse=True)


async def test_listing_filters_by_status(api, db):
    await make_submission(db, status="referred")
    await api.post("/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL})

    referred = (await api.get("/submissions", params={"status": "referred"})).json()
    received = (await api.get("/submissions", params={"status": "received"})).json()

    assert [each["status"] for each in referred] == ["referred"]
    assert [each["status"] for each in received] == ["received"]


async def test_listing_rejects_an_unknown_status(api):
    response = await api.get("/submissions", params={"status": "vibes"})

    assert response.status_code == 422


async def test_listing_is_bounded(api):
    assert (await api.get("/submissions", params={"limit": 201})).status_code == 422
    assert (await api.get("/submissions", params={"limit": 0})).status_code == 422
    assert (await api.get("/submissions", params={"limit": 200})).status_code == 200


async def test_listing_pages(api):
    for _ in range(3):
        await api.post("/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL})

    first = (await api.get("/submissions", params={"limit": 2})).json()
    second = (await api.get("/submissions", params={"limit": 2, "offset": 2})).json()

    assert len(first) == 2
    assert len(second) == 1
    assert {each["id"] for each in first}.isdisjoint({each["id"] for each in second})


async def test_reading_one_submission_nests_its_relations(api, db):
    submission = await make_submission(db)

    body = (await api.get(f"/submissions/{submission.id}")).json()

    assert body["id"] == str(submission.id)
    assert set(body) >= {"extraction", "enrichment", "rating", "quote", "audit_events"}


async def test_an_unknown_submission_is_not_found(api):
    missing = uuid.uuid4()

    response = await api.get(f"/submissions/{missing}")

    assert response.status_code == 404
    assert str(missing) in response.json()["detail"]


async def test_a_malformed_id_is_rejected_before_the_database(api):
    response = await api.get("/submissions/not-a-uuid")

    assert response.status_code == 422


async def test_the_created_submission_is_readable_by_id(api):
    created = (
        await api.post("/submissions", json={"input_mode": "paste", "raw_input": BROKER_EMAIL})
    ).json()

    fetched = (await api.get(f"/submissions/{created['id']}")).json()

    assert fetched == created
