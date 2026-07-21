"""Every number and string in RATING_SPEC.md §3, transcribed independently.

The expected values here are read off the spec, never imported from the engine — a test
that imports the table it is checking proves only that the table equals itself.
"""

from decimal import Decimal
from itertools import permutations

import pytest

from app.domain.enums import (
    TERMINAL_COMPANY_STATUSES,
    CompanyStatus,
    DataVolume,
    Decision,
    ReasonCode,
    RequestedLimit,
    Sector,
)
from app.domain.rating import Enrichment
from app.services import rating
from app.services.rating import rate
from tests.rating_baseline import CLEAN_ENRICHMENT, application, enrichment


def applied(result, code):
    return next(f for f in result.factors if f.code == code)


def rate_with(**overrides):
    return rate(application(**overrides), CLEAN_ENRICHMENT)


# --- §3 factor tables -------------------------------------------------------------------

LIMIT_ROWS = [
    (RequestedLimit.GBP_250K, "1.0", "£250,000 limit"),
    (RequestedLimit.GBP_500K, "1.4", "£500,000 limit"),
    (RequestedLimit.GBP_1M, "1.9", "£1,000,000 limit"),
    (RequestedLimit.GBP_2M, "2.6", "£2,000,000 limit"),
]

REVENUE_ROWS = [
    (5_000_000, "0.8", "under £100k"),
    (25_000_000, "1.0", "£100k – £500k"),
    (75_000_000, "1.3", "£500k – £2m"),
    (500_000_000, "1.7", "£2m – £10m"),
    (2_000_000_000, "2.2", "£10m or more"),
]

SECTOR_ROWS = [
    (Sector.SAAS, "1.0"),
    (Sector.ECOMMERCE, "1.1"),
    (Sector.MARKETPLACE, "1.1"),
    (Sector.AI_ML, "1.2"),
    (Sector.FINTECH, "1.35"),
    (Sector.HEALTHTECH, "1.35"),
    (Sector.OTHER, "1.35"),
    (Sector.CRYPTO, "1.5"),
]

DATA_VOLUME_ROWS = [
    (DataVolume.UNDER_10K, "0.9"),
    (DataVolume.TEN_K_TO_100K, "1.0"),
    (DataVolume.HUNDRED_K_TO_1M, "1.25"),
    (DataVolume.OVER_1M, "1.5"),
]

CLAIMS_ROWS = [
    (0, "1.0", "no prior claims"),
    (1, "1.4", "1 prior claim"),
    (2, "1.4", "2 or more prior claims"),
    (7, "1.4", "2 or more prior claims"),
]

MONTHS_TRADING_ROWS = [
    (3, "1.2", "under 6 months"),
    (12, "1.2", "6 months – under 2 years"),
    (36, "1.0", "2 years or more"),
]


@pytest.mark.parametrize(("limit", "factor", "label"), LIMIT_ROWS)
def test_limit_factor(limit, factor, label):
    row = applied(rate_with(requested_limit=limit), "LIMIT")
    assert (row.multiplier, row.band_label) == (Decimal(factor), label)


@pytest.mark.parametrize(("pence", "factor", "label"), REVENUE_ROWS)
def test_revenue_factor(pence, factor, label):
    row = applied(rate_with(annual_revenue_pence=pence), "REVENUE_BAND")
    assert (row.multiplier, row.band_label) == (Decimal(factor), label)


@pytest.mark.parametrize(("sector", "factor"), SECTOR_ROWS)
def test_sector_factor(sector, factor):
    row = applied(rate_with(sector=sector), "SECTOR")
    assert (row.multiplier, row.band_label) == (Decimal(factor), sector.value)


@pytest.mark.parametrize(("volume", "factor"), DATA_VOLUME_ROWS)
def test_data_volume_factor(volume, factor):
    row = applied(rate_with(data_records_held=volume), "DATA_VOLUME")
    assert (row.multiplier, row.band_label) == (Decimal(factor), volume.value)


@pytest.mark.parametrize(("count", "factor", "label"), CLAIMS_ROWS)
def test_prior_claims_factor(count, factor, label):
    row = applied(rate_with(prior_claims_count=count), "CLAIMS_HISTORY")
    assert (row.multiplier, row.band_label) == (Decimal(factor), label)


@pytest.mark.parametrize(("months", "factor", "label"), MONTHS_TRADING_ROWS)
def test_months_trading_factor(months, factor, label):
    row = applied(rate_with(months_trading=months), "MONTHS_TRADING")
    assert (row.multiplier, row.band_label) == (Decimal(factor), label)


def test_every_factor_code_is_exercised():
    codes = {f.code for f in rate_with().factors}
    assert codes == {
        "LIMIT",
        "REVENUE_BAND",
        "SECTOR",
        "DATA_VOLUME",
        "CLAIMS_HISTORY",
        "MONTHS_TRADING",
    }


# Adding an enum member or a band edge without a row above fails here, not silently.
@pytest.mark.parametrize(
    ("covered", "expected"),
    [
        ({row[0] for row in LIMIT_ROWS}, set(RequestedLimit)),
        ({row[0] for row in SECTOR_ROWS}, set(Sector)),
        ({row[0] for row in DATA_VOLUME_ROWS}, set(DataVolume)),
    ],
)
def test_lookup_tables_cover_every_enum_member(covered, expected):
    assert covered == expected


@pytest.mark.parametrize(
    ("rows", "edges"),
    [
        (REVENUE_ROWS, rating.REVENUE_EDGES_PENCE),
        (MONTHS_TRADING_ROWS, rating.MONTHS_TRADING_EDGES),
        (CLAIMS_ROWS, rating.PRIOR_CLAIMS_EDGES),
    ],
)
def test_band_tables_cover_every_band(rows, edges):
    assert len({row[2] for row in rows}) == len(edges) + 1


# --- §3 band boundaries, D4 half-open -----------------------------------------------------

REVENUE_BOUNDARIES = [
    (9_999_999, "0.8", "under £100k"),
    (10_000_000, "1.0", "£100k – £500k"),
    (49_999_999, "1.0", "£100k – £500k"),
    (50_000_000, "1.3", "£500k – £2m"),
    (199_999_999, "1.3", "£500k – £2m"),
    (200_000_000, "1.7", "£2m – £10m"),
    (999_999_999, "1.7", "£2m – £10m"),
    (1_000_000_000, "2.2", "£10m or more"),
]

MONTHS_TRADING_BOUNDARIES = [
    (5, "1.2", "under 6 months"),
    (6, "1.2", "6 months – under 2 years"),
    (23, "1.2", "6 months – under 2 years"),
    (24, "1.0", "2 years or more"),
]


@pytest.mark.parametrize(("pence", "factor", "label"), REVENUE_BOUNDARIES)
def test_revenue_boundary_opens_its_own_band(pence, factor, label):
    row = applied(rate_with(annual_revenue_pence=pence), "REVENUE_BAND")
    assert (row.multiplier, row.band_label) == (Decimal(factor), label)


@pytest.mark.parametrize(("months", "factor", "label"), MONTHS_TRADING_BOUNDARIES)
def test_months_trading_boundary_opens_its_own_band(months, factor, label):
    row = applied(rate_with(months_trading=months), "MONTHS_TRADING")
    assert (row.multiplier, row.band_label) == (Decimal(factor), label)


@pytest.mark.parametrize(
    ("months", "decision"),
    [(5, Decision.DECLINE), (6, Decision.AUTO_APPROVE)],
)
def test_six_months_is_the_first_acceptable_month(months, decision):
    assert rate_with(months_trading=months).decision is decision


@pytest.mark.parametrize(
    ("count", "decision"),
    [(0, Decision.AUTO_APPROVE), (1, Decision.REFER), (2, Decision.DECLINE)],
)
def test_each_claims_count_crosses_into_the_next_outcome(count, decision):
    assert rate_with(prior_claims_count=count).decision is decision


@pytest.mark.parametrize(
    ("pence", "refers"),
    [(999_999_999, False), (1_000_000_000, True)],
)
def test_binding_authority_starts_at_ten_million(pence, refers):
    result = rate_with(annual_revenue_pence=pence)
    fired = ReasonCode.REVENUE_ABOVE_AUTHORITY in {r.code for r in result.refer_reasons}
    assert fired is refers


@pytest.mark.parametrize(("confidence", "refers"), [(0.7, False), (0.69, True)])
def test_extraction_confidence_threshold_is_exclusive(confidence, refers):
    result = rate_with(extraction_confidence=confidence)
    fired = ReasonCode.LOW_EXTRACTION_CONFIDENCE in {r.code for r in result.refer_reasons}
    assert fired is refers


@pytest.mark.parametrize(("score", "refers"), [(0.85, False), (0.84, True)])
def test_name_match_threshold_is_exclusive(score, refers):
    result = rate(application(), enrichment(ch_name_match_score=score))
    fired = ReasonCode.CH_NAME_MISMATCH in {r.code for r in result.refer_reasons}
    assert fired is refers


# --- §3 hard rules, each firing alone -----------------------------------------------------

REFER_CODES = frozenset(
    {
        ReasonCode.LOW_EXTRACTION_CONFIDENCE,
        ReasonCode.MISSING_FIELDS,
        ReasonCode.CH_NOT_FOUND,
        ReasonCode.CH_NAME_MISMATCH,
        ReasonCode.CH_STATUS_NOT_ACTIVE,
        ReasonCode.CH_DISCREPANCY,
        ReasonCode.REVENUE_ABOVE_AUTHORITY,
        ReasonCode.SECTOR_UNCLASSIFIED,
        ReasonCode.PRIOR_CLAIM,
    }
)

DECLINE_CODES = frozenset(
    {
        ReasonCode.SECTOR_OUT_OF_APPETITE,
        ReasonCode.CLAIMS_HISTORY,
        ReasonCode.TOO_NEW,
        ReasonCode.CH_STATUS_TERMINAL,
    }
)

REFER_IN_ISOLATION = [
    pytest.param(
        {"extraction_confidence": 0.69},
        CLEAN_ENRICHMENT,
        ReasonCode.LOW_EXTRACTION_CONFIDENCE,
        id="low_extraction_confidence",
    ),
    pytest.param(
        {"missing_fields": ("annual_revenue_gbp",)},
        CLEAN_ENRICHMENT,
        ReasonCode.MISSING_FIELDS,
        id="missing_fields",
    ),
    pytest.param({}, Enrichment(ch_found=False), ReasonCode.CH_NOT_FOUND, id="ch_not_found"),
    pytest.param(
        {},
        enrichment(ch_name_match_score=0.84),
        ReasonCode.CH_NAME_MISMATCH,
        id="ch_name_mismatch",
    ),
    pytest.param(
        {},
        enrichment(ch_company_status=CompanyStatus.VOLUNTARY_ARRANGEMENT),
        ReasonCode.CH_STATUS_NOT_ACTIVE,
        id="ch_status_not_active",
    ),
    pytest.param(
        {},
        enrichment(discrepancies=("Incorporated in 2024, but the submission claims 5 years.",)),
        ReasonCode.CH_DISCREPANCY,
        id="ch_discrepancy",
    ),
    pytest.param(
        {"annual_revenue_pence": 1_000_000_000},
        CLEAN_ENRICHMENT,
        ReasonCode.REVENUE_ABOVE_AUTHORITY,
        id="revenue_above_authority",
    ),
    pytest.param(
        {"sector": Sector.OTHER},
        CLEAN_ENRICHMENT,
        ReasonCode.SECTOR_UNCLASSIFIED,
        id="sector_unclassified",
    ),
    pytest.param(
        {"prior_claims_count": 1},
        CLEAN_ENRICHMENT,
        ReasonCode.PRIOR_CLAIM,
        id="prior_claim",
    ),
]

DECLINE_IN_ISOLATION = [
    pytest.param(
        {"sector": Sector.CRYPTO},
        ReasonCode.SECTOR_OUT_OF_APPETITE,
        id="sector_out_of_appetite",
    ),
    pytest.param({"prior_claims_count": 2}, ReasonCode.CLAIMS_HISTORY, id="claims_history"),
    pytest.param({"months_trading": 5}, ReasonCode.TOO_NEW, id="too_new"),
]


@pytest.mark.parametrize(("overrides", "ch", "code"), REFER_IN_ISOLATION)
def test_hard_referral_rule_fires_alone(overrides, ch, code):
    result = rate(application(**overrides), ch)

    assert result.decision is Decision.REFER
    assert {r.code for r in result.refer_reasons} == {code}
    assert result.decline_reasons == ()
    assert result.annual_premium_pence == result.indicative_premium_pence


@pytest.mark.parametrize(("overrides", "code"), DECLINE_IN_ISOLATION)
def test_hard_decline_rule_fires_alone(overrides, code):
    result = rate(application(**overrides), CLEAN_ENRICHMENT)

    assert result.decision is Decision.DECLINE
    assert {r.code for r in result.decline_reasons} == {code}
    assert result.refer_reasons == ()
    assert result.annual_premium_pence is None
    assert result.indicative_premium_pence > 0


def test_isolation_cases_cover_every_reason_code():
    covered = {param.values[2] for param in REFER_IN_ISOLATION}
    covered |= {param.values[1] for param in DECLINE_IN_ISOLATION}

    # CH_STATUS_TERMINAL cannot fire alone — see the next test.
    assert covered == (REFER_CODES | DECLINE_CODES) - {ReasonCode.CH_STATUS_TERMINAL}
    assert set(ReasonCode) == REFER_CODES | DECLINE_CODES
    assert not REFER_CODES & DECLINE_CODES


@pytest.mark.parametrize("status", sorted(TERMINAL_COMPANY_STATUSES))
def test_terminal_status_declines_and_drags_the_not_active_referral(status):
    result = rate(application(), enrichment(ch_company_status=status))

    assert result.decision is Decision.DECLINE
    assert {r.code for r in result.decline_reasons} == {ReasonCode.CH_STATUS_TERMINAL}
    assert {r.code for r in result.refer_reasons} == {ReasonCode.CH_STATUS_NOT_ACTIVE}


@pytest.mark.parametrize(
    "status",
    sorted(set(CompanyStatus) - TERMINAL_COMPANY_STATUSES - {CompanyStatus.ACTIVE}),
)
def test_non_terminal_inactive_status_only_refers(status):
    result = rate(application(), enrichment(ch_company_status=status))

    assert result.decision is Decision.REFER
    assert {r.code for r in result.refer_reasons} == {ReasonCode.CH_STATUS_NOT_ACTIVE}


def test_too_new_still_applies_its_multiplier():
    result = rate_with(months_trading=5)

    assert applied(result, "MONTHS_TRADING").multiplier == Decimal("1.2")
    assert result.indicative_premium_pence > 0


def test_every_reason_message_is_a_sentence():
    result = rate(
        application(sector=Sector.OTHER, prior_claims_count=2, extraction_confidence=0.5),
        Enrichment(ch_found=False, discrepancies=("Dormant since 2023.",)),
    )
    messages = [r.message for r in result.refer_reasons + result.decline_reasons]

    assert messages
    assert all(m[0] == m[0].upper() and m.endswith(".") for m in messages)


# --- §4 calculation order and rounding ----------------------------------------------------

COMPOSITIONS = [
    pytest.param(
        {
            "requested_limit": RequestedLimit.GBP_2M,
            "annual_revenue_pence": 2_000_000_000,
            "sector": Sector.FINTECH,
            "data_records_held": DataVolume.OVER_1M,
            "prior_claims_count": 1,
            "months_trading": 12,
        },
        ["2.6", "2.2", "1.35", "1.5", "1.4", "1.2"],
        1_751_000,
        Decision.REFER,
        id="every_factor_at_its_heaviest",
    ),
    pytest.param(
        {
            "requested_limit": RequestedLimit.GBP_250K,
            "annual_revenue_pence": 5_000_000,
            "sector": Sector.SAAS,
            "data_records_held": DataVolume.UNDER_10K,
            "prior_claims_count": 0,
            "months_trading": 36,
        },
        ["1.0", "0.8", "1.0", "0.9", "1.0", "1.0"],
        65_000,
        Decision.AUTO_APPROVE,
        id="every_factor_at_its_lightest",
    ),
    pytest.param(
        {
            "requested_limit": RequestedLimit.GBP_500K,
            "annual_revenue_pence": 500_000_000,
            "sector": Sector.AI_ML,
            "data_records_held": DataVolume.TEN_K_TO_100K,
            "prior_claims_count": 0,
            "months_trading": 12,
        },
        ["1.4", "1.7", "1.2", "1.0", "1.0", "1.2"],
        308_000,
        Decision.AUTO_APPROVE,
        id="mid_book_risk",
    ),
]


@pytest.mark.parametrize(("overrides", "multipliers", "premium", "decision"), COMPOSITIONS)
def test_premium_composes_in_spec_order(overrides, multipliers, premium, decision):
    result = rate_with(**overrides)

    assert [f.multiplier for f in result.factors] == [Decimal(m) for m in multipliers]
    assert result.base_premium_pence == 90_000
    assert result.indicative_premium_pence == premium
    assert result.decision is decision

    running = Decimal(result.base_premium_pence)
    for multiplier in multipliers:
        running *= Decimal(multiplier)
    assert result.factors[-1].premium_after_pence == running


def test_exact_half_rounds_up_not_to_even():
    # 112,500 is a dead-on £5 tie; quantize defaults to HALF_EVEN, giving £1,120.
    result = rate_with(
        requested_limit=RequestedLimit.GBP_250K,
        annual_revenue_pence=25_000_000,
    )

    assert result.factors[-1].premium_after_pence == Decimal(112_500)
    assert result.indicative_premium_pence == 113_000


def test_premium_is_never_rounded_mid_calculation():
    result = rate_with(
        requested_limit=RequestedLimit.GBP_2M,
        annual_revenue_pence=2_000_000_000,
        sector=Sector.FINTECH,
        data_records_held=DataVolume.OVER_1M,
        prior_claims_count=1,
        months_trading=12,
    )
    steps = [f.premium_after_pence for f in result.factors]

    assert any(step != step.to_integral_value() for step in steps)
    assert any(step % 1_000 != 0 for step in steps)


# --- D7 the decision join -----------------------------------------------------------------


def test_decision_join_is_order_independent_and_idempotent():
    for size in range(1, len(Decision) + 1):
        for combination in permutations(Decision, size):
            assert Decision.worst(list(combination)) is max(combination)
            assert Decision.worst(list(combination) * 2) is max(combination)


def test_empty_decision_join_auto_approves():
    assert Decision.worst([]) is Decision.AUTO_APPROVE
