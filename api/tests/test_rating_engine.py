import ast
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.enums import (
    CompanyStatus,
    DataVolume,
    Decision,
    ReasonCode,
    Sector,
)
from app.domain.rating import Enrichment
from app.services import rating
from app.services.rating import rate
from tests.rating_baseline import CLEAN_ENRICHMENT, application

BANNED_IMPORTS = {"sqlalchemy", "httpx", "anthropic", "fastapi", "boto3", "app.db"}


def test_rating_module_imports_nothing_impure():
    source = Path(rating.__file__).read_text()
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    offenders = {name for name in imported if any(name.startswith(b) for b in BANNED_IMPORTS)}
    assert not offenders, f"rating engine must stay pure, found: {offenders}"


def test_worked_example_from_the_spec():
    result = rate(application(), CLEAN_ENRICHMENT)

    assert result.indicative_premium_pence == 278_000
    assert result.annual_premium_pence == 278_000
    assert result.decision is Decision.AUTO_APPROVE
    assert result.rating_version == "v1.0"
    assert result.refer_reasons == ()
    assert result.decline_reasons == ()


def test_worked_example_factor_sequence():
    result = rate(application(), CLEAN_ENRICHMENT)

    assert [(f.code, f.multiplier) for f in result.factors] == [
        ("LIMIT", Decimal("1.9")),
        ("REVENUE_BAND", Decimal("1.3")),
        ("SECTOR", Decimal("1.0")),
        ("DATA_VOLUME", Decimal("1.25")),
        ("CLAIMS_HISTORY", Decimal("1.0")),
        ("MONTHS_TRADING", Decimal("1.0")),
    ]


def test_trace_folds_back_to_the_premium():
    result = rate(application(), CLEAN_ENRICHMENT)

    running = Decimal(result.base_premium_pence)
    for factor in result.factors:
        assert factor.premium_before_pence == running
        running *= factor.multiplier
        assert factor.premium_after_pence == running

    assert rating._round_to_nearest(running, 1_000) == result.indicative_premium_pence


def test_declined_risk_has_no_annual_premium_but_keeps_an_indication():
    result = rate(application(sector=Sector.CRYPTO), CLEAN_ENRICHMENT)

    assert result.decision is Decision.DECLINE
    assert result.annual_premium_pence is None
    assert result.indicative_premium_pence > 0
    assert [r.code for r in result.decline_reasons] == [ReasonCode.SECTOR_OUT_OF_APPETITE]


def test_decline_outranks_refer_and_keeps_both_reason_sets():
    result = rate(
        application(sector=Sector.CRYPTO, prior_claims_count=1),
        CLEAN_ENRICHMENT,
    )

    assert result.decision is Decision.DECLINE
    assert ReasonCode.PRIOR_CLAIM in {r.code for r in result.refer_reasons}
    assert ReasonCode.SECTOR_OUT_OF_APPETITE in {r.code for r in result.decline_reasons}


def test_unmatched_company_does_not_evaluate_companies_house_rules():
    result = rate(application(), Enrichment(ch_found=False))

    assert result.decision is Decision.REFER
    assert [r.code for r in result.refer_reasons] == [ReasonCode.CH_NOT_FOUND]


@pytest.mark.parametrize(
    ("edges", "factors", "labels", "message"),
    [
        ((2, 1), (Decimal(1),) * 3, ("a", "b", "c"), "strictly increasing"),
        ((1, 2), (Decimal(1),) * 2, ("a", "b"), "expected 3 factors"),
        ((1, 2), (Decimal(1),) * 3, ("a", "b"), "expected 3 labels"),
    ],
)
def test_malformed_band_tables_fail_loudly(edges, factors, labels, message):
    with pytest.raises(ValueError, match=message):
        rating._validate_band("probe", edges, factors, labels)


def test_enum_fields_coerce_from_raw_values():
    coerced = application(sector="crypto", data_records_held="over_1m")
    found = Enrichment(ch_found=True, ch_company_status="dissolved")

    assert coerced.sector is Sector.CRYPTO
    assert coerced.data_records_held is DataVolume.OVER_1M
    assert found.ch_company_status is CompanyStatus.DISSOLVED

    result = rate(coerced, found)
    assert {r.code for r in result.decline_reasons} == {
        ReasonCode.SECTOR_OUT_OF_APPETITE,
        ReasonCode.CH_STATUS_TERMINAL,
    }


def test_unknown_enum_value_is_rejected_at_construction():
    with pytest.raises(ValueError, match="not a valid Sector"):
        application(sector="quantum_blockchain")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("annual_revenue_pence", -1),
        ("months_trading", -1),
        ("prior_claims_count", -1),
    ],
)
def test_negative_numeric_fields_are_rejected(field, value):
    with pytest.raises(ValueError, match="must not be negative"):
        application(**{field: value})


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_extraction_confidence_outside_zero_to_one_is_rejected(confidence):
    with pytest.raises(ValueError, match="between 0 and 1"):
        application(extraction_confidence=confidence)


def test_name_match_score_outside_zero_to_one_is_rejected():
    with pytest.raises(ValueError, match="between 0 and 1"):
        Enrichment(ch_found=True, ch_name_match_score=1.4)


def test_mutable_sequences_are_frozen_into_tuples():
    frozen = application(missing_fields=["annual_revenue_pence"])
    found = Enrichment(ch_found=False, discrepancies=["incorporated 2024"])

    assert frozen.missing_fields == ("annual_revenue_pence",)
    assert found.discrepancies == ("incorporated 2024",)
    assert isinstance(hash(frozen), int)
    assert isinstance(hash(found), int)


def test_discrepancies_still_refer_when_no_company_was_matched():
    result = rate(
        application(),
        Enrichment(ch_found=False, discrepancies=("incorporated 2024, claims 5 years",)),
    )

    assert {r.code for r in result.refer_reasons} == {
        ReasonCode.CH_DISCREPANCY,
        ReasonCode.CH_NOT_FOUND,
    }


def test_missing_companies_house_status_reads_sensibly():
    result = rate(application(), Enrichment(ch_found=True, ch_name_match_score=0.99))

    (reason,) = result.refer_reasons
    assert reason.code is ReasonCode.CH_STATUS_NOT_ACTIVE
    assert reason.message == "Companies House did not return a company status."


def test_missing_factor_for_an_enum_member_fails_loudly():
    with pytest.raises(ValueError, match="no factor defined for"):
        rating._validate_lookup("sector", {Sector.SAAS: Decimal("1.0")}, Sector)


@pytest.mark.parametrize(
    ("pence", "expected"),
    [(75_000_000, "£750,000"), (75_000_050, "£750,000.50"), (0, "£0"), (99, "£0.99")],
)
def test_money_is_rendered_without_losing_pence(pence, expected):
    assert rating._format_gbp(pence) == expected
