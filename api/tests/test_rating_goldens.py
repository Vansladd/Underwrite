"""Frozen `RatingResult`s for a representative book.

A factor change lands as a reviewable JSON diff rather than a spreadsheet exercise: the
question "what did this do to prices?" is answered in the pull request. Regenerate with
`make regen-goldens`, and read the diff before committing it — that diff is the point.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.enums import CompanyStatus, DataVolume, RequestedLimit, Sector
from app.domain.rating import Enrichment
from app.services.rating import RATING_VERSION, rate
from tests.rating_baseline import CLEAN_ENRICHMENT, application, enrichment

GOLDEN_PATH = Path(__file__).parent / "goldens" / "rating_v1_0.json"

STRIKE_OFF = enrichment(
    ch_company_status=CompanyStatus.ACTIVE,
    discrepancies=("Companies House shows an active proposal to strike off.",),
)

BOOK = [
    ("saas_micro", {"annual_revenue_pence": 5_000_000}, CLEAN_ENRICHMENT),
    ("saas_small", {"annual_revenue_pence": 25_000_000}, CLEAN_ENRICHMENT),
    ("saas_mid_spec_example", {}, CLEAN_ENRICHMENT),
    ("saas_large", {"annual_revenue_pence": 500_000_000}, CLEAN_ENRICHMENT),
    ("saas_above_authority", {"annual_revenue_pence": 2_000_000_000}, CLEAN_ENRICHMENT),
    ("sector_ecommerce", {"sector": Sector.ECOMMERCE}, CLEAN_ENRICHMENT),
    ("sector_marketplace", {"sector": Sector.MARKETPLACE}, CLEAN_ENRICHMENT),
    ("sector_ai_ml", {"sector": Sector.AI_ML}, CLEAN_ENRICHMENT),
    ("sector_fintech", {"sector": Sector.FINTECH}, CLEAN_ENRICHMENT),
    ("sector_healthtech", {"sector": Sector.HEALTHTECH}, CLEAN_ENRICHMENT),
    ("sector_other_unclassified", {"sector": Sector.OTHER}, CLEAN_ENRICHMENT),
    ("sector_crypto_declined", {"sector": Sector.CRYPTO}, CLEAN_ENRICHMENT),
    ("limit_250k", {"requested_limit": RequestedLimit.GBP_250K}, CLEAN_ENRICHMENT),
    ("limit_500k", {"requested_limit": RequestedLimit.GBP_500K}, CLEAN_ENRICHMENT),
    ("limit_1m", {"requested_limit": RequestedLimit.GBP_1M}, CLEAN_ENRICHMENT),
    ("limit_2m", {"requested_limit": RequestedLimit.GBP_2M}, CLEAN_ENRICHMENT),
    ("data_under_10k", {"data_records_held": DataVolume.UNDER_10K}, CLEAN_ENRICHMENT),
    ("data_10k_100k", {"data_records_held": DataVolume.TEN_K_TO_100K}, CLEAN_ENRICHMENT),
    ("data_100k_1m", {"data_records_held": DataVolume.HUNDRED_K_TO_1M}, CLEAN_ENRICHMENT),
    ("data_over_1m", {"data_records_held": DataVolume.OVER_1M}, CLEAN_ENRICHMENT),
    ("one_prior_claim", {"prior_claims_count": 1}, CLEAN_ENRICHMENT),
    ("two_prior_claims", {"prior_claims_count": 2}, CLEAN_ENRICHMENT),
    ("trading_5_months", {"months_trading": 5}, CLEAN_ENRICHMENT),
    ("trading_exactly_6_months", {"months_trading": 6}, CLEAN_ENRICHMENT),
    ("trading_exactly_24_months", {"months_trading": 24}, CLEAN_ENRICHMENT),
    ("low_extraction_confidence", {"extraction_confidence": 0.55}, CLEAN_ENRICHMENT),
    ("missing_revenue", {"missing_fields": ("annual_revenue_gbp",)}, CLEAN_ENRICHMENT),
    ("companies_house_down", {}, Enrichment(ch_found=False)),
    ("name_mismatch", {}, enrichment(ch_name_match_score=0.62)),
    ("company_dissolved", {}, enrichment(ch_company_status=CompanyStatus.DISSOLVED)),
    ("proposal_to_strike_off", {}, STRIKE_OFF),
    (
        "everything_wrong",
        {
            "sector": Sector.CRYPTO,
            "annual_revenue_pence": 2_000_000_000,
            "months_trading": 3,
            "prior_claims_count": 4,
            "data_records_held": DataVolume.OVER_1M,
            "requested_limit": RequestedLimit.GBP_2M,
            "extraction_confidence": 0.3,
            "missing_fields": ("months_trading",),
        },
        Enrichment(ch_found=False, discrepancies=("No such company.",)),
    ),
]


def as_jsonable(result):
    return {
        "decision": result.decision.name,
        "base_premium_pence": result.base_premium_pence,
        "indicative_premium_pence": result.indicative_premium_pence,
        "annual_premium_pence": result.annual_premium_pence,
        "factors": [
            {
                "code": factor.code,
                "band_label": factor.band_label,
                # str, not float: a Decimal through JSON loses the exactness D6 exists to keep.
                "multiplier": str(factor.multiplier),
                "reason": factor.reason,
                "premium_before_pence": str(factor.premium_before_pence),
                "premium_after_pence": str(factor.premium_after_pence),
            }
            for factor in result.factors
        ],
        "refer_reasons": [
            {"code": r.code.value, "message": r.message} for r in result.refer_reasons
        ],
        "decline_reasons": [
            {"code": r.code.value, "message": r.message} for r in result.decline_reasons
        ],
    }


def rate_the_book():
    return {
        "rating_version": RATING_VERSION,
        "risks": {
            name: as_jsonable(rate(application(**overrides), found))
            for name, overrides, found in BOOK
        },
    }


def test_book_names_are_unique():
    names = [name for name, _, _ in BOOK]
    assert len(names) == len(set(names))


def test_rating_results_match_the_goldens(request):
    current = rate_the_book()

    if request.config.getoption("--regen-goldens"):
        GOLDEN_PATH.parent.mkdir(exist_ok=True)
        GOLDEN_PATH.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n")
        pytest.skip(f"regenerated {GOLDEN_PATH.name} — review the diff before committing")

    golden = json.loads(GOLDEN_PATH.read_text())

    assert golden["rating_version"] == RATING_VERSION, (
        "the goldens were frozen against a different rating version; "
        "bump RATING_VERSION and regenerate deliberately"
    )
    assert current["risks"].keys() == golden["risks"].keys()
    for name in golden["risks"]:
        assert current["risks"][name] == golden["risks"][name], f"golden drift in {name}"


def test_golden_multipliers_survive_the_json_round_trip():
    golden = json.loads(GOLDEN_PATH.read_text())
    factors = golden["risks"]["saas_mid_spec_example"]["factors"]

    running = Decimal(golden["risks"]["saas_mid_spec_example"]["base_premium_pence"])
    for factor in factors:
        running *= Decimal(factor["multiplier"])

    assert running == Decimal("277875")
