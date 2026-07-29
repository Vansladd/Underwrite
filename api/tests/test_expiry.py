from datetime import date, timedelta

from sqlalchemy import select

from app.domain.enums import AuditActor, AuditEventType, QuoteStatus
from app.models import AuditEvent, Quote
from app.services.expiry import expire_quotes
from tests.factories import make_submission

TODAY = date(2026, 8, 1)


async def make_quote(db, *, valid_until: date, ref: str, status=QuoteStatus.ISSUED) -> Quote:
    submission = await make_submission(db)
    quote = Quote(
        submission_id=submission.id,
        quote_ref=ref,
        status=status,
        limit_pence=100_000_000,
        excess_pence=250_000,
        gross_premium_pence=278_000,
        inception_date=valid_until - timedelta(days=30),
        valid_until=valid_until,
    )
    db.add(quote)
    await db.flush()
    return quote


async def expiry_events(db) -> list[AuditEvent]:
    return list(
        await db.scalars(
            select(AuditEvent).where(AuditEvent.event_type == AuditEventType.QUOTE_EXPIRED)
        )
    )


# --- the sweep itself ---


async def test_a_quote_past_its_validity_is_expired(db):
    quote = await make_quote(db, valid_until=TODAY - timedelta(days=1), ref="Q-2026-AAAAAA")

    swept = await expire_quotes(db, today=TODAY)

    assert swept == ["Q-2026-AAAAAA"]
    assert quote.status is QuoteStatus.EXPIRED


async def test_expiring_a_quote_writes_a_system_actor_audit_event(db):
    await make_quote(db, valid_until=TODAY - timedelta(days=1), ref="Q-2026-BBBBBB")

    await expire_quotes(db, today=TODAY)

    (event,) = await expiry_events(db)
    assert event.actor is AuditActor.SYSTEM
    # A system actor names no operator; borrowing one would falsify the trail.
    assert event.actor_id is None
    assert event.payload == {
        "quote_ref": "Q-2026-BBBBBB",
        "valid_until": "2026-07-31",
        "swept_on": "2026-08-01",
    }


async def test_a_quote_valid_until_today_is_still_live(db):
    quote = await make_quote(db, valid_until=TODAY, ref="Q-2026-CCCCCC")

    swept = await expire_quotes(db, today=TODAY)

    assert swept == []
    assert quote.status is QuoteStatus.ISSUED
    assert await expiry_events(db) == []


async def test_a_second_sweep_expires_nothing_and_writes_no_second_event(db):
    await make_quote(db, valid_until=TODAY - timedelta(days=1), ref="Q-2026-DDDDDD")
    await expire_quotes(db, today=TODAY)

    swept = await expire_quotes(db, today=TODAY + timedelta(days=1))

    assert swept == []
    assert len(await expiry_events(db)) == 1


async def test_an_already_expired_quote_is_not_swept_again(db):
    await make_quote(
        db,
        valid_until=TODAY - timedelta(days=90),
        ref="Q-2026-EEEEEE",
        status=QuoteStatus.EXPIRED,
    )

    assert await expire_quotes(db, today=TODAY) == []
    assert await expiry_events(db) == []


async def test_a_sweep_with_nothing_to_do_writes_nothing(db):
    await make_quote(db, valid_until=TODAY + timedelta(days=29), ref="Q-2026-FFFFFF")

    assert await expire_quotes(db, today=TODAY) == []
    assert await expiry_events(db) == []


# --- the internal endpoint ---


async def test_the_sweep_endpoint_expires_and_reports(anon_api, db, sweeper_token):
    today = date.today()
    await make_quote(db, valid_until=today - timedelta(days=1), ref="Q-2026-111111")

    response = await anon_api.post(
        "/api/internal/quotes/expire", headers={"X-Sweeper-Token": sweeper_token}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["expired"] == 1
    assert body["quote_refs"] == ["Q-2026-111111"]
    # Bounded, not equal: the route calls date.today() itself, which can tick over mid-test.
    assert date.fromisoformat(body["swept_on"]) >= today


async def test_the_sweep_endpoint_refuses_a_wrong_token(anon_api, db, sweeper_token):
    await make_quote(db, valid_until=date.today() - timedelta(days=1), ref="Q-2026-222222")

    response = await anon_api.post(
        "/api/internal/quotes/expire", headers={"X-Sweeper-Token": "not-the-token"}
    )

    assert response.status_code == 401
    assert await expiry_events(db) == []


async def test_the_sweep_endpoint_refuses_a_missing_token(anon_api, sweeper_token):
    assert (await anon_api.post("/api/internal/quotes/expire")).status_code == 401


async def test_the_sweep_endpoint_is_closed_when_no_token_is_configured(anon_api, no_sweeper_token):
    # Unconfigured must not mean "an absent header matches an empty secret".
    response = await anon_api.post("/api/internal/quotes/expire", headers={"X-Sweeper-Token": ""})

    assert response.status_code == 503


async def test_an_operator_session_does_not_open_the_internal_route(api, sweeper_token):
    # `api` is authenticated as TEST_USER; the machine gate is a separate credential.
    assert (await api.post("/api/internal/quotes/expire")).status_code == 401
