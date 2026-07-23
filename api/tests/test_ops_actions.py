from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.domain.enums import (
    AuditActor,
    AuditEventType,
    DataVolume,
    RequestedLimit,
    Sector,
    SubmissionStatus,
)
from app.models import AuditEvent, Extraction, Quote, Rating, Submission, User
from app.schemas import rating_to_orm_kwargs
from app.services.rating import rate
from tests.conftest import TEST_USER
from tests.factories import STRIKE_OFF, make_submission
from tests.rating_baseline import application


@pytest.fixture
async def operator(db):
    # actor_id is an FK to users; the injected TEST_USER is never persisted by the fixtures.
    db.add(
        User(
            id=TEST_USER.id,
            username="tester",
            password_hash="unused",
            display_name="Test Operator",
        )
    )
    await db.flush()


async def referred(db, *, rated=True) -> Submission:
    submission = await make_submission(db, status=SubmissionStatus.REFERRED)
    db.add(
        Extraction(
            submission_id=submission.id,
            company_name="Example Ltd",
            sector=Sector.SAAS,
            annual_revenue_pence=75_000_000,
            months_trading=36,
            prior_claims_count=0,
            data_records_held=DataVolume.HUNDRED_K_TO_1M,
            requested_limit=RequestedLimit.GBP_1M,
            extraction_confidence=0.94,
            missing_fields=[],
            model="claude-sonnet-5",
        )
    )
    if rated:
        db.add(
            Rating(
                submission_id=submission.id, **rating_to_orm_kwargs(rate(application(), STRIKE_OFF))
            )
        )
    await db.flush()
    return submission


async def test_approving_a_referral_issues_a_quote_and_flips_to_quoted(api, db, operator):
    submission = await referred(db)

    body = (await api.post(f"/api/submissions/{submission.id}/approve")).json()

    assert body["status"] == "quoted"
    quote = body["quote"]
    assert quote["quote_ref"].startswith("Q-")
    assert quote["excess_pence"] == 250_000
    assert quote["limit_pence"] == 100_000_000  # £1m
    assert quote["gross_premium_pence"] == body["rating"]["annual_premium_pence"]
    valid_from = date.fromisoformat(quote["inception_date"])
    assert quote["valid_until"] == (valid_from + timedelta(days=30)).isoformat()


async def test_approval_names_the_underwriter_not_just_the_role(api, db, operator):
    submission = await referred(db)

    await api.post(f"/api/submissions/{submission.id}/approve")

    event = (
        await db.scalars(
            select(AuditEvent).where(
                AuditEvent.submission_id == submission.id,
                AuditEvent.event_type == AuditEventType.SUBMISSION_APPROVED,
            )
        )
    ).one()
    assert event.actor is AuditActor.OPS
    assert event.actor_id == TEST_USER.id


async def test_the_timeline_carries_the_operator_name(api, db, operator):
    submission = await referred(db)

    body = (await api.post(f"/api/submissions/{submission.id}/approve")).json()

    approved = [e for e in body["audit_events"] if e["event_type"] == "submission_approved"]
    assert len(approved) == 1
    assert approved[0]["actor"] == "ops"
    assert approved[0]["actor_name"] == "Test Operator"


async def test_cannot_approve_a_non_referred_submission(api, db, operator):
    submission = await make_submission(db, status=SubmissionStatus.AUTO_APPROVED)

    response = await api.post(f"/api/submissions/{submission.id}/approve")

    assert response.status_code == 409


async def test_cannot_approve_a_referral_without_a_premium(api, db, operator):
    submission = await referred(db, rated=False)

    response = await api.post(f"/api/submissions/{submission.id}/approve")

    assert response.status_code == 422
    assert (await db.get(Submission, submission.id)).status is SubmissionStatus.REFERRED


async def test_declining_a_referral_flips_to_declined_and_stores_a_trimmed_reason(
    api, db, operator
):
    submission = await make_submission(db, status=SubmissionStatus.REFERRED)

    body = (
        await api.post(
            f"/api/submissions/{submission.id}/decline", json={"reason": "  Outside appetite.  "}
        )
    ).json()

    assert body["status"] == "declined"
    event = (
        await db.scalars(
            select(AuditEvent).where(
                AuditEvent.submission_id == submission.id,
                AuditEvent.event_type == AuditEventType.SUBMISSION_DECLINED,
            )
        )
    ).one()
    assert event.actor is AuditActor.OPS
    assert event.actor_id == TEST_USER.id
    assert event.payload["reason"] == "Outside appetite."


async def test_decline_requires_a_reason(api, db, operator):
    submission = await make_submission(db, status=SubmissionStatus.REFERRED)

    response = await api.post(f"/api/submissions/{submission.id}/decline", json={"reason": ""})

    assert response.status_code == 422


async def test_decline_rejects_a_blank_reason(api, db, operator):
    submission = await make_submission(db, status=SubmissionStatus.REFERRED)

    response = await api.post(f"/api/submissions/{submission.id}/decline", json={"reason": "   "})

    assert response.status_code == 422
    assert (await db.get(Submission, submission.id)).status is SubmissionStatus.REFERRED


async def test_approve_conflicts_when_a_quote_already_exists(api, db, operator):
    # Stand in for a lost approve/approve race: the quote row is already present.
    submission = await referred(db)
    db.add(
        Quote(
            submission_id=submission.id,
            quote_ref="Q-EXISTING",
            limit_pence=1,
            excess_pence=1,
            gross_premium_pence=1,
            inception_date=date(2026, 1, 1),
            valid_until=date(2026, 2, 1),
        )
    )
    await db.flush()

    response = await api.post(f"/api/submissions/{submission.id}/approve")

    assert response.status_code == 409


async def test_cannot_decline_a_non_referred_submission(api, db, operator):
    submission = await make_submission(db, status=SubmissionStatus.DECLINED)

    response = await api.post(f"/api/submissions/{submission.id}/decline", json={"reason": "no"})

    assert response.status_code == 409
