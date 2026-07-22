import uuid

from sqlalchemy import func, select

from app.domain.enums import AuditEventType, Decision, ReasonCode, SubmissionStatus
from app.models import AuditEvent, Rating, Submission
from app.seed import SCENARIOS, SEED_NAMESPACE, seed


def scenario_id(slug: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NAMESPACE, slug)


async def count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def test_seeding_twice_is_idempotent(db):
    await seed(db)
    assert await count(db, Submission) == len(SCENARIOS) == 6

    await seed(db)
    assert await count(db, Submission) == 6

    # The trail must not grow on the second pass either.
    received = await db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.submission_id == scenario_id("acme-robotics"),
            AuditEvent.event_type == AuditEventType.SUBMISSION_RECEIVED,
        )
    )
    assert received == 1


async def test_the_seed_covers_the_decision_spectrum(db):
    await seed(db)

    statuses = (await db.scalars(select(Submission.status))).all()
    spread = {status: statuses.count(status) for status in set(statuses)}

    assert spread == {
        SubmissionStatus.AUTO_APPROVED: 1,
        SubmissionStatus.REFERRED: 3,
        SubmissionStatus.DECLINED: 2,
    }


async def test_a_declined_seed_has_no_annual_premium(db):
    await seed(db)

    rating = await db.scalar(
        select(Rating).where(Rating.submission_id == scenario_id("blockspire"))
    )
    assert rating.decision is Decision.DECLINE
    assert rating.annual_premium_pence is None


async def test_the_incomplete_seed_is_referred_without_a_rating(db):
    await seed(db)

    submission = await db.get(Submission, scenario_id("nimbus-health"))
    assert submission.status is SubmissionStatus.REFERRED

    assert await db.scalar(select(Rating).where(Rating.submission_id == submission.id)) is None

    trail = (
        await db.scalars(
            select(AuditEvent.event_type)
            .where(AuditEvent.submission_id == submission.id)
            .order_by(AuditEvent.occurred_at)
        )
    ).all()
    assert trail[-1] is AuditEventType.RATING_FAILED


async def test_the_name_mismatch_seed_records_its_reason(db):
    await seed(db)

    rating = await db.scalar(
        select(Rating).where(Rating.submission_id == scenario_id("ledgerline-capital"))
    )
    codes = [reason["code"] for reason in rating.refer_reasons]
    assert ReasonCode.CH_NAME_MISMATCH.value in codes
