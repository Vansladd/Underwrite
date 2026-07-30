"""Recovering the submissions a Companies House outage referred. See D-037."""

import pytest
from sqlalchemy import func, select

from app.domain.enums import (
    AuditActor,
    AuditEventType,
    CompanyStatus,
    DataVolume,
    RequestedLimit,
    Sector,
)
from app.models import AuditEvent, Enrichment, Rating
from app.services.companies_house import (
    CompaniesHouseLookup,
    CompaniesHouseUnavailable,
    CompanyProfile,
)

# Clean enough to auto-approve once the register answers: small revenue, no claims, established.
APPLICATION = {
    "company_name": "Example Ltd",
    "company_number": "00000006",
    "sector": Sector.SAAS.value,
    "annual_revenue_gbp": 750_000.0,
    "years_trading": 6.0,
    "prior_claims_count": 0,
    "data_records_held": DataVolume.TEN_K_TO_100K.value,
    "requested_limit_gbp": RequestedLimit.GBP_500K.value,
}


def active_profile(**overrides) -> CompaniesHouseLookup:
    base = {
        "company_number": "00000006",
        "company_name": "EXAMPLE LTD",
        "company_status": CompanyStatus.ACTIVE,
        "date_of_creation": None,
        "sic_codes": ["62012"],
    }
    return CompaniesHouseLookup(CompanyProfile(**{**base, **overrides}))


async def submit_during_an_outage(api, fake_ch_client, **overrides):
    """A real referral produced by a real outage, not a hand-built row."""
    fake_ch_client.error = CompaniesHouseUnavailable("timeout")
    response = await api.post(
        "/api/submissions",
        json={"input_mode": "form", "application": {**APPLICATION, **overrides}},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "referred"
    assert "CH_UNAVAILABLE" in [r["code"] for r in body["rating"]["refer_reasons"]]
    return body


def register_recovers(fake_ch_client, lookup=None) -> None:
    fake_ch_client.error = None
    fake_ch_client.lookup_result = lookup or active_profile()


async def events_of(db, submission_id, event_type) -> list[AuditEvent]:
    return list(
        (
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.submission_id == submission_id,
                    AuditEvent.event_type == event_type,
                )
            )
        ).all()
    )


async def test_a_recheck_after_the_register_returns_clears_the_referral(
    api, db, fake_ch_client, operator
):
    submission = await submit_during_an_outage(api, fake_ch_client)
    register_recovers(fake_ch_client)

    response = await api.post(f"/api/submissions/{submission['id']}/recheck")

    assert response.status_code == 200
    body = response.json()
    assert "CH_UNAVAILABLE" not in [r["code"] for r in body["rating"]["refer_reasons"]]
    assert body["enrichment"]["ch_found"] is True
    assert body["enrichment"]["lookup_error"] is None


async def test_the_recheck_updates_the_rows_rather_than_adding_second_ones(
    api, db, fake_ch_client, operator
):
    # Both tables are unique on submission_id, so a second row is an IntegrityError rather than a
    # silent duplicate — but the count is what says the update path was taken at all.
    submission = await submit_during_an_outage(api, fake_ch_client)
    register_recovers(fake_ch_client)

    await api.post(f"/api/submissions/{submission['id']}/recheck")

    for model in (Enrichment, Rating):
        count = await db.scalar(
            select(func.count()).select_from(model).where(model.submission_id == submission["id"])
        )
        assert count == 1


async def test_the_recheck_records_both_sides_of_the_decision(api, db, fake_ch_client, operator):
    submission = await submit_during_an_outage(api, fake_ch_client)
    before = submission["rating"]["decision"]
    register_recovers(fake_ch_client)

    await api.post(f"/api/submissions/{submission['id']}/recheck")

    events = await events_of(db, submission["id"], AuditEventType.SUBMISSION_RECHECKED)
    assert len(events) == 1
    payload = events[0].payload
    # The row now holds only the second value, so the trail is the only record of the first.
    assert payload["decision_before"] == before
    assert payload["lookup_error_before"] == "timeout"
    assert payload["lookup_error_after"] is None
    assert payload["resolved"] is True


async def test_the_recheck_is_attributed_to_the_operator_who_asked_for_it(
    api, db, fake_ch_client, operator
):
    # Unlike the sweeper, a human pressed this — borrowing SYSTEM would falsify the trail.
    submission = await submit_during_an_outage(api, fake_ch_client)
    register_recovers(fake_ch_client)

    await api.post(f"/api/submissions/{submission['id']}/recheck")

    event = (await events_of(db, submission["id"], AuditEventType.SUBMISSION_RECHECKED))[0]
    assert event.actor is AuditActor.OPS
    assert event.actor_id is not None


async def test_a_recheck_while_the_register_is_still_down_changes_nothing(
    api, db, fake_ch_client, operator
):
    submission = await submit_during_an_outage(api, fake_ch_client)
    fake_ch_client.error = CompaniesHouseUnavailable("network")

    response = await api.post(f"/api/submissions/{submission['id']}/recheck")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "referred"
    assert "CH_UNAVAILABLE" in [r["code"] for r in body["rating"]["refer_reasons"]]
    payload = (await events_of(db, submission["id"], AuditEventType.SUBMISSION_RECHECKED))[
        0
    ].payload
    assert payload["resolved"] is False
    assert payload["lookup_error_after"] == "network"


async def test_a_recheck_that_reaches_auto_approve_issues_the_quote(
    api, db, fake_ch_client, operator
):
    # D-030: auto-approved with no quote is priced-then-abandoned, and a recheck can reach that
    # decision exactly as the first rating can. Asserted unconditionally — an `if` around this
    # asserts nothing the day the scenario drifts, which is how it was first written.
    submission = await submit_during_an_outage(api, fake_ch_client)
    register_recovers(fake_ch_client)

    body = (await api.post(f"/api/submissions/{submission['id']}/recheck")).json()

    assert body["rating"]["decision"] == "AUTO_APPROVE"
    assert body["status"] == "auto_approved"
    assert body["quote"] is not None, "auto-approved with no quote is the D-030 state"
    # The pipeline renders in the route, not the service, so the recheck route has to as well —
    # found live: the first version issued the quote and left it without a document.
    assert body["quote"]["pdf_s3_key"] is not None


async def test_a_submission_that_referred_for_another_reason_is_refused(
    api, fake_ch_client, operator
):
    fake_ch_client.error = None
    fake_ch_client.lookup_result = active_profile(company_name="SOMETHING ELSE ENTIRELY LTD")
    created = await api.post(
        "/api/submissions", json={"input_mode": "form", "application": APPLICATION}
    )
    body = created.json()
    assert body["status"] == "referred"
    assert "CH_UNAVAILABLE" not in [r["code"] for r in body["rating"]["refer_reasons"]]

    response = await api.post(f"/api/submissions/{body['id']}/recheck")

    assert response.status_code == 409
    assert "Companies House was unreachable" in response.json()["detail"]


async def test_an_approved_submission_is_refused_because_re_rating_would_move_its_premium(
    api, fake_ch_client, operator
):
    submission = await submit_during_an_outage(api, fake_ch_client)
    approved = await api.post(f"/api/submissions/{submission['id']}/approve")
    assert approved.status_code == 200
    register_recovers(fake_ch_client)

    response = await api.post(f"/api/submissions/{submission['id']}/recheck")

    assert response.status_code == 409
    # The specific guard, not just the status: every gate returns 409, so asserting the code alone
    # cannot tell which one fired and leaves the others free to be deleted.
    assert "already has a quote" in response.json()["detail"]


async def test_a_declined_submission_is_refused(api, fake_ch_client, operator):
    submission = await submit_during_an_outage(api, fake_ch_client)
    declined = await api.post(
        f"/api/submissions/{submission['id']}/decline", json={"reason": "out of appetite"}
    )
    assert declined.status_code == 200
    register_recovers(fake_ch_client)

    response = await api.post(f"/api/submissions/{submission['id']}/recheck")

    assert response.status_code == 409
    assert "only a referred submission" in response.json()["detail"]


async def test_an_unknown_submission_is_a_404(api):
    response = await api.post("/api/submissions/00000000-0000-0000-0000-000000000000/recheck")

    assert response.status_code == 404


@pytest.mark.parametrize("code", ["CH_UNAVAILABLE"])
async def test_the_queue_can_be_filtered_to_the_outage_referrals(api, fake_ch_client, code):
    outage = await submit_during_an_outage(api, fake_ch_client)
    fake_ch_client.error = None
    fake_ch_client.lookup_result = active_profile(company_name="SOMETHING ELSE ENTIRELY LTD")
    other = (
        await api.post("/api/submissions", json={"input_mode": "form", "application": APPLICATION})
    ).json()

    listed = (await api.get(f"/api/submissions?reason={code}")).json()

    ids = [row["id"] for row in listed]
    assert outage["id"] in ids
    assert other["id"] not in ids


async def test_the_reason_filter_composes_with_the_status_filter(api, fake_ch_client, operator):
    outage = await submit_during_an_outage(api, fake_ch_client)

    referred = (await api.get("/api/submissions?status=referred&reason=CH_UNAVAILABLE")).json()
    declined = (await api.get("/api/submissions?status=declined&reason=CH_UNAVAILABLE")).json()

    assert outage["id"] in [row["id"] for row in referred]
    assert declined == []


async def test_a_decline_only_code_finds_the_submissions_it_declined(api, fake_ch_client):
    """Four ReasonCode members appear only in decline_reasons, never in refer_reasons.

    Searching one array answered "none exist" to a quarter of the codes it accepts — with a 200,
    so nothing said the question had gone unanswered rather than the answer being empty.
    """
    fake_ch_client.error = None
    fake_ch_client.lookup_result = active_profile()
    declined = (
        await api.post(
            "/api/submissions",
            json={
                "input_mode": "form",
                "application": {**APPLICATION, "sector": Sector.CRYPTO.value},
            },
        )
    ).json()
    assert declined["status"] == "declined"
    codes = [r["code"] for r in declined["rating"]["decline_reasons"]]
    assert "SECTOR_OUT_OF_APPETITE" in codes

    listed = (await api.get("/api/submissions?reason=SECTOR_OUT_OF_APPETITE")).json()

    assert declined["id"] in [row["id"] for row in listed]


async def test_an_unknown_reason_is_rejected_rather_than_ignored(api):
    # Silently returning everything would read as "no submissions match", which is a lie.
    response = await api.get("/api/submissions?reason=NOT_A_REASON")

    assert response.status_code == 422
