import ast
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.enums import (
    CompanyStatus,
    DataVolume,
    Decision,
    ReasonCode,
    RequestedLimit,
    Sector,
)
from app.domain.rating import Application, Enrichment
from app.services import rating
from app.services.rating import rate

BANNED_IMPORTS = {"sqlalchemy", "httpx", "anthropic", "fastapi", "boto3", "app.db"}

CLEAN_ENRICHMENT = Enrichment(
    ch_found=True,
    ch_company_status=CompanyStatus.ACTIVE,
    ch_name_match_score=0.99,
)


def spec_example_application(**overrides):
    defaults = dict(
        company_name="Example Ltd",
        sector=Sector.SAAS,
        annual_revenue_pence=75_000_000,
        months_trading=36,
        prior_claims_count=0,
        data_records_held=DataVolume.HUNDRED_K_TO_1M,
        requested_limit=RequestedLimit.GBP_1M,
    )
    return Application(**{**defaults, **overrides})


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
    result = rate(spec_example_application(), CLEAN_ENRICHMENT)

    assert result.indicative_premium_pence == 278_000
    assert result.annual_premium_pence == 278_000
    assert result.decision is Decision.AUTO_APPROVE
    assert result.rating_version == "v1.0"
    assert result.refer_reasons == ()
    assert result.decline_reasons == ()


def test_worked_example_factor_sequence():
    result = rate(spec_example_application(), CLEAN_ENRICHMENT)

    assert [(f.code, f.multiplier) for f in result.factors] == [
        ("LIMIT", Decimal("1.9")),
        ("REVENUE_BAND", Decimal("1.3")),
        ("SECTOR", Decimal("1.0")),
        ("DATA_VOLUME", Decimal("1.25")),
        ("CLAIMS_HISTORY", Decimal("1.0")),
        ("MONTHS_TRADING", Decimal("1.0")),
    ]


def test_trace_folds_back_to_the_premium():
    result = rate(spec_example_application(), CLEAN_ENRICHMENT)

    running = Decimal(result.base_premium_pence)
    for factor in result.factors:
        assert factor.premium_before_pence == running
        running *= factor.multiplier
        assert factor.premium_after_pence == running

    assert rating._round_to_nearest(running, 1_000) == result.indicative_premium_pence


def test_declined_risk_has_no_annual_premium_but_keeps_an_indication():
    result = rate(spec_example_application(sector=Sector.CRYPTO), CLEAN_ENRICHMENT)

    assert result.decision is Decision.DECLINE
    assert result.annual_premium_pence is None
    assert result.indicative_premium_pence > 0
    assert [r.code for r in result.decline_reasons] == [ReasonCode.SECTOR_OUT_OF_APPETITE]


def test_decline_outranks_refer_and_keeps_both_reason_sets():
    result = rate(
        spec_example_application(sector=Sector.CRYPTO, prior_claims_count=1),
        CLEAN_ENRICHMENT,
    )

    assert result.decision is Decision.DECLINE
    assert ReasonCode.PRIOR_CLAIM in {r.code for r in result.refer_reasons}
    assert ReasonCode.SECTOR_OUT_OF_APPETITE in {r.code for r in result.decline_reasons}


def test_unmatched_company_does_not_evaluate_companies_house_rules():
    result = rate(spec_example_application(), Enrichment(ch_found=False))

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
    application = spec_example_application(sector="crypto", data_records_held="over_1m")
    enrichment = Enrichment(ch_found=True, ch_company_status="dissolved")

    assert application.sector is Sector.CRYPTO
    assert application.data_records_held is DataVolume.OVER_1M
    assert enrichment.ch_company_status is CompanyStatus.DISSOLVED

    result = rate(application, enrichment)
    assert {r.code for r in result.decline_reasons} == {
        ReasonCode.SECTOR_OUT_OF_APPETITE,
        ReasonCode.CH_STATUS_TERMINAL,
    }


def test_unknown_enum_value_is_rejected_at_construction():
    with pytest.raises(ValueError, match="not a valid Sector"):
        spec_example_application(sector="quantum_blockchain")
