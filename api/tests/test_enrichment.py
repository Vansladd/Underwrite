import pytest

from app.domain.enums import CompanyStatus, DataVolume, RequestedLimit, Sector
from app.schemas import CompanyProfile, ExtractedApplication
from app.services.companies_house import CompaniesHouseLookup
from app.services.enrichment import enrich
from tests.fakes import FakeChClient


def application(**overrides) -> ExtractedApplication:
    base = {
        "company_name": "Example Ltd",
        "company_number": "00000006",
        "sector": Sector.SAAS,
        "annual_revenue_gbp": 750_000.0,
        "years_trading": 3.0,
        "prior_claims_count": 0,
        "data_records_held": DataVolume.HUNDRED_K_TO_1M,
        "requested_limit_gbp": RequestedLimit.GBP_1M,
        "extraction_confidence": 0.94,
    }
    return ExtractedApplication(**{**base, **overrides})


def profile(**overrides) -> CompanyProfile:
    base = {
        "company_number": "00000006",
        "company_name": "EXAMPLE LIMITED",
        "company_status": CompanyStatus.ACTIVE,
        # None keeps the age-vs-incorporation check out; strike-off below is date-independent.
        "date_of_creation": None,
        "sic_codes": ["62012"],
    }
    return CompanyProfile(**{**base, **overrides})


async def test_a_matched_company_populates_the_enrichment():
    ch = FakeChClient(CompaniesHouseLookup(profile()))

    outcome = await enrich(ch, application())

    assert outcome.error is None
    assert outcome.orm_kwargs["ch_found"] is True
    assert outcome.orm_kwargs["ch_company_name"] == "EXAMPLE LIMITED"
    assert outcome.orm_kwargs["sic_codes"] == ["62012"]
    assert outcome.orm_kwargs["ch_name_match_score"] >= 0.95
    assert outcome.domain.ch_found is True
    assert outcome.domain.ch_company_status is CompanyStatus.ACTIVE


async def test_a_strike_off_detail_becomes_a_discrepancy():
    ch = FakeChClient(
        CompaniesHouseLookup(profile(company_status_detail="active-proposal-to-strike-off"))
    )

    outcome = await enrich(ch, application())

    assert len(outcome.orm_kwargs["discrepancies"]) == 1
    assert "strike" in outcome.orm_kwargs["discrepancies"][0]
    assert outcome.domain.discrepancies == tuple(outcome.orm_kwargs["discrepancies"])


async def test_no_match_leaves_ch_not_found_without_an_error():
    ch = FakeChClient(CompaniesHouseLookup(None, rate_limited=True))

    outcome = await enrich(ch, application())

    assert outcome.error is None
    assert outcome.orm_kwargs["ch_found"] is False
    assert outcome.orm_kwargs["rate_limited"] is True
    assert outcome.domain.ch_found is False


async def test_a_lookup_exception_is_swallowed_into_a_best_effort_result():
    ch = FakeChClient(error=RuntimeError("companies house is down"))

    outcome = await enrich(ch, application())

    # Best-effort: the exception is recorded, not propagated (the #30-review fix).
    assert outcome.orm_kwargs["ch_found"] is False
    assert "companies house is down" in outcome.error
    assert outcome.domain.ch_found is False


async def test_a_missing_company_name_skips_the_lookup_entirely():
    ch = FakeChClient(error=RuntimeError("must not be called"))

    outcome = await enrich(ch, application(company_name=None))

    assert ch.calls == []
    assert outcome.orm_kwargs["ch_found"] is False
    assert outcome.error is None


async def test_the_swallow_is_load_bearing():
    # Mutation guard: enrich() must not let a raising client escape. See D-023.
    ch = FakeChClient(error=RuntimeError("boom"))

    outcome = await enrich(ch, application())

    with pytest.raises(RuntimeError):
        await ch.lookup("00000006", "Example Ltd")
    assert outcome.error is not None
