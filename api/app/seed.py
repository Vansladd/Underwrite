from __future__ import annotations

import asyncio
import sys
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import build_engine, build_sessionmaker
from app.domain.enums import (
    AuditActor,
    AuditEventType,
    CompanyStatus,
    DataVolume,
    InputMode,
    RequestedLimit,
    Sector,
)
from app.models import Submission, User
from app.schemas import CompanyProfile, ExtractedApplication
from app.services.audit import record_event
from app.services.auth import hash_password
from app.services.companies_house import CompaniesHouseLookup
from app.services.pipeline import run_pipeline

# Fixed namespace: submission ids are uuid5(namespace, slug), so re-seeding is a no-op.
SEED_NAMESPACE = uuid.UUID("5eed0000-0000-4000-8000-000000000027")
SEED_MODEL = "claude-sonnet-5"
OPERATOR_SLUG = "user:operator"
OPERATOR_DISPLAY_NAME = "Demo Underwriter"


def years_ago(years: float) -> date:
    return date.today() - timedelta(days=round(years * 365.25))


class _CannedExtractor:
    def __init__(self, result: ExtractedApplication) -> None:
        self._result = result

    @property
    def model(self) -> str:
        return SEED_MODEL

    async def extract(self, raw_input: str) -> ExtractedApplication:
        return self._result


class _CannedCh:
    def __init__(self, lookup: CompaniesHouseLookup) -> None:
        self._lookup = lookup

    async def lookup(self, company_number: str | None, company_name: str) -> CompaniesHouseLookup:
        return self._lookup


@dataclass(frozen=True)
class Scenario:
    slug: str
    raw_input: str
    application: ExtractedApplication
    lookup: CompaniesHouseLookup


def _found(
    number: str,
    name: str,
    sic: list[str],
    trading_years: float,
    *,
    status: CompanyStatus = CompanyStatus.ACTIVE,
    status_detail: str | None = None,
) -> CompaniesHouseLookup:
    return CompaniesHouseLookup(
        CompanyProfile(
            company_number=number,
            company_name=name,
            company_status=status,
            company_status_detail=status_detail,
            date_of_creation=years_ago(trading_years),
            sic_codes=sic,
        )
    )


SCENARIOS: list[Scenario] = [
    # Auto-approve: clean SaaS, Companies House matches and is active.
    Scenario(
        slug="acme-robotics",
        raw_input=(
            "Please quote Acme Robotics Ltd (CH 09876543): SaaS for warehouse automation, "
            "revenue £2.5m, trading 6 years, no prior claims, ~500,000 customer records, "
            "£1,000,000 limit."
        ),
        application=ExtractedApplication(
            company_name="Acme Robotics Ltd",
            company_number="09876543",
            sector=Sector.SAAS,
            annual_revenue_gbp=2_500_000.0,
            years_trading=6.0,
            prior_claims_count=0,
            data_records_held=DataVolume.HUNDRED_K_TO_1M,
            requested_limit_gbp=RequestedLimit.GBP_1M,
            extraction_confidence=0.96,
        ),
        lookup=_found("09876543", "ACME ROBOTICS LIMITED", ["62012"], 6.0),
    ),
    # Refer: the submitted name matches the Companies House record too weakly.
    Scenario(
        slug="ledgerline-capital",
        raw_input=(
            "New business — Ledgerline Capital Ltd (SC123456), a fintech running a small-business "
            "lending product. Over a million customer records, no claims, £2m limit please."
        ),
        application=ExtractedApplication(
            company_name="Ledgerline Capital Ltd",
            company_number="SC123456",
            sector=Sector.FINTECH,
            annual_revenue_gbp=4_200_000.0,
            years_trading=5.0,
            prior_claims_count=0,
            data_records_held=DataVolume.OVER_1M,
            requested_limit_gbp=RequestedLimit.GBP_2M,
            extraction_confidence=0.90,
        ),
        lookup=_found("SC123456", "LEDGERLINE HOLDINGS LIMITED", ["64191"], 5.0),
    ),
    # Refer: revenue was never stated, so the engine cannot rate — a human must complete it.
    Scenario(
        slug="nimbus-health",
        raw_input=(
            "Cyber quote — Nimbus Health Ltd (07654321), a clinical data platform for GP "
            "surgeries. Trading 4 years, one settled breach in 2023, ~2 million records, £500,000 "
            "limit. Revenue to follow separately."
        ),
        application=ExtractedApplication(
            company_name="Nimbus Health Ltd",
            company_number="07654321",
            sector=Sector.HEALTHTECH,
            annual_revenue_gbp=None,
            years_trading=4.0,
            prior_claims_count=1,
            data_records_held=DataVolume.OVER_1M,
            requested_limit_gbp=RequestedLimit.GBP_500K,
            extraction_confidence=0.82,
            missing_fields=["annual_revenue_gbp"],
        ),
        lookup=_found("07654321", "NIMBUS HEALTH LIMITED", ["86900"], 4.0),
    ),
    # Refer: active, but with a live proposal to strike the company off the register.
    Scenario(
        slug="harbor-point",
        raw_input=(
            "Quote Harbor Point Systems Ltd (10234567): B2B SaaS, revenue £1.8m, trading 4 years, "
            "no claims, ~40,000 records, £500,000 limit."
        ),
        application=ExtractedApplication(
            company_name="Harbor Point Systems Ltd",
            company_number="10234567",
            sector=Sector.SAAS,
            annual_revenue_gbp=1_800_000.0,
            years_trading=4.0,
            prior_claims_count=0,
            data_records_held=DataVolume.TEN_K_TO_100K,
            requested_limit_gbp=RequestedLimit.GBP_500K,
            extraction_confidence=0.93,
        ),
        lookup=_found(
            "10234567",
            "HARBOR POINT SYSTEMS LIMITED",
            ["62020"],
            4.0,
            status_detail="active-proposal-to-strike-off",
        ),
    ),
    # Decline: crypto is outside appetite for this product.
    Scenario(
        slug="blockspire",
        raw_input=(
            "Blockspire Ltd (11223344) — digital-asset custody platform. Revenue £3m, trading "
            "3 years, no claims, ~600,000 records, £1m limit."
        ),
        application=ExtractedApplication(
            company_name="Blockspire Ltd",
            company_number="11223344",
            sector=Sector.CRYPTO,
            annual_revenue_gbp=3_000_000.0,
            years_trading=3.0,
            prior_claims_count=0,
            data_records_held=DataVolume.HUNDRED_K_TO_1M,
            requested_limit_gbp=RequestedLimit.GBP_1M,
            extraction_confidence=0.90,
        ),
        lookup=_found("11223344", "BLOCKSPIRE LIMITED", ["64999"], 3.0),
    ),
    # Decline: three months trading is below the minimum.
    Scenario(
        slug="dayzero-labs",
        raw_input=(
            "Dayzero Labs Ltd (13571357) — early-stage AI tooling startup, three months trading. "
            "Revenue £400k run-rate, no claims, under 10k records, £250,000 limit."
        ),
        application=ExtractedApplication(
            company_name="Dayzero Labs Ltd",
            company_number="13571357",
            sector=Sector.AI_ML,
            annual_revenue_gbp=400_000.0,
            years_trading=0.25,
            prior_claims_count=0,
            data_records_held=DataVolume.UNDER_10K,
            requested_limit_gbp=RequestedLimit.GBP_250K,
            extraction_confidence=0.88,
        ),
        lookup=_found("13571357", "DAYZERO LABS LIMITED", ["62012"], 0.25),
    ),
]


async def seed(session: AsyncSession) -> int:
    """Insert the canned submissions, running each through the real pipeline. Idempotent."""
    inserted = 0
    for scenario in SCENARIOS:
        submission_id = uuid.uuid5(SEED_NAMESPACE, scenario.slug)
        if await session.get(Submission, submission_id) is not None:
            continue

        submission = Submission(
            id=submission_id,
            input_mode=InputMode.PASTE,
            raw_input=scenario.raw_input,
        )
        session.add(submission)
        await session.flush()
        await record_event(
            session,
            submission.id,
            AuditEventType.SUBMISSION_RECEIVED,
            AuditActor.APPLICANT,
            {"input_mode": "paste", "raw_input_chars": len(scenario.raw_input)},
        )
        await session.commit()

        await run_pipeline(
            session,
            submission,
            None,
            _CannedExtractor(scenario.application),
            _CannedCh(scenario.lookup),
        )
        inserted += 1
    return inserted


async def seed_operator(
    session: AsyncSession,
    username: str,
    password: str,
    display_name: str = OPERATOR_DISPLAY_NAME,
) -> User:
    """Upsert the operator so its password always tracks the configured secret. See D-026."""
    operator_id = uuid.uuid5(SEED_NAMESPACE, OPERATOR_SLUG)
    user = await session.get(User, operator_id)
    if user is None:
        user = User(id=operator_id)
        session.add(user)
    user.username = username
    user.display_name = display_name
    user.password_hash = hash_password(password)
    await session.commit()
    return user


async def main() -> int:
    settings = get_settings()
    engine = build_engine(settings)
    sessionmaker = build_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            inserted = await seed(session)
            await seed_operator(
                session, settings.seed_operator_username, settings.seed_operator_password
            )
            rows = (await session.scalars(select(Submission.status))).all()
            total = await session.scalar(select(func.count()).select_from(Submission))
    finally:
        await engine.dispose()

    by_status = Counter(status.value for status in rows)
    print(f"seeded {inserted} new submission(s); {total} total")
    print(f"operator: {settings.seed_operator_username}")
    for status, count in sorted(by_status.items()):
        print(f"  {status}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
