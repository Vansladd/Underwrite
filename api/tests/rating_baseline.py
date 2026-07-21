from app.domain.enums import CompanyStatus, DataVolume, RequestedLimit, Sector
from app.domain.rating import Application, Enrichment

CLEAN_ENRICHMENT = Enrichment(
    ch_found=True,
    ch_company_status=CompanyStatus.ACTIVE,
    ch_name_match_score=0.99,
)

# RATING_SPEC §4's worked example, so one override isolates one rule.
SPEC_EXAMPLE = {
    "company_name": "Example Ltd",
    "sector": Sector.SAAS,
    "annual_revenue_pence": 75_000_000,
    "months_trading": 36,
    "prior_claims_count": 0,
    "data_records_held": DataVolume.HUNDRED_K_TO_1M,
    "requested_limit": RequestedLimit.GBP_1M,
}


def application(**overrides) -> Application:
    return Application(**{**SPEC_EXAMPLE, **overrides})


def enrichment(**overrides) -> Enrichment:
    base = {
        "ch_found": True,
        "ch_company_status": CompanyStatus.ACTIVE,
        "ch_name_match_score": 0.99,
    }
    return Enrichment(**{**base, **overrides})
