"""RATING_SPEC §7 invariants, over generated inputs rather than chosen ones.

The example tests in test_rating_tables.py prove the engine is right about the risks I
thought of. These prove properties that must hold for every risk in the domain — the ones
that catch a mistyped factor row no example test would have looked at.
"""

from dataclasses import replace
from decimal import Decimal

from hypothesis import example, given
from hypothesis import strategies as st

from app.domain.enums import CompanyStatus, DataVolume, Decision, RequestedLimit, Sector
from app.domain.rating import Application, Enrichment, RatingResult
from app.services import rating
from app.services.rating import rate
from tests.rating_baseline import CLEAN_ENRICHMENT, application

MAX_MONTHS = 600
MAX_CLAIMS = 20
MAX_REVENUE_PENCE = 5_000_000_000

applications = st.builds(
    Application,
    company_name=st.text(min_size=1, max_size=20),
    sector=st.sampled_from(Sector),
    annual_revenue_pence=st.integers(min_value=0, max_value=MAX_REVENUE_PENCE),
    months_trading=st.integers(min_value=0, max_value=MAX_MONTHS),
    prior_claims_count=st.integers(min_value=0, max_value=MAX_CLAIMS),
    data_records_held=st.sampled_from(DataVolume),
    requested_limit=st.sampled_from(RequestedLimit),
    extraction_confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    missing_fields=st.lists(
        st.sampled_from(["annual_revenue_gbp", "months_trading", "sector"]),
        max_size=3,
    ).map(tuple),
)

enrichments = st.builds(
    Enrichment,
    ch_found=st.booleans(),
    ch_company_status=st.one_of(st.none(), st.sampled_from(CompanyStatus)),
    ch_name_match_score=st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    ),
    discrepancies=st.lists(st.text(min_size=1, max_size=20), max_size=3).map(tuple),
)


# Hypothesis lands on an exact band edge by chance almost never, so every edge is pinned.
@given(applications, enrichments)
@example(application(annual_revenue_pence=10_000_000), CLEAN_ENRICHMENT)
@example(application(annual_revenue_pence=50_000_000), CLEAN_ENRICHMENT)
@example(application(annual_revenue_pence=200_000_000), CLEAN_ENRICHMENT)
@example(application(annual_revenue_pence=1_000_000_000), CLEAN_ENRICHMENT)
@example(application(months_trading=6), CLEAN_ENRICHMENT)
@example(application(months_trading=24), CLEAN_ENRICHMENT)
@example(application(prior_claims_count=1), CLEAN_ENRICHMENT)
@example(application(prior_claims_count=2), CLEAN_ENRICHMENT)
def test_trace_always_folds_back_to_the_premium(app, enrichment):
    result = rate(app, enrichment)

    running = Decimal(result.base_premium_pence)
    for factor in result.factors:
        assert factor.premium_before_pence == running
        running *= factor.multiplier
        assert factor.premium_after_pence == running

    assert rating._round_to_nearest(running, 1_000) == result.indicative_premium_pence


@given(applications, enrichments)
def test_rating_is_total(app, enrichment):
    result = rate(app, enrichment)

    assert isinstance(result, RatingResult)
    assert result.rating_version == rating.RATING_VERSION
    assert len(result.factors) == 6


@given(applications, enrichments)
def test_rating_is_deterministic(app, enrichment):
    assert rate(app, enrichment) == rate(app, enrichment)


@given(applications, enrichments)
def test_a_declined_risk_never_carries_an_annual_premium(app, enrichment):
    result = rate(app, enrichment)

    declined = result.decision is Decision.DECLINE
    assert declined == (result.annual_premium_pence is None)
    assert declined == bool(result.decline_reasons)


@given(applications, enrichments)
def test_premium_is_positive_and_rounded_to_ten_pounds(app, enrichment):
    result = rate(app, enrichment)

    assert result.indicative_premium_pence > 0
    assert result.indicative_premium_pence % 1_000 == 0
    assert result.annual_premium_pence in (None, result.indicative_premium_pence)


@given(applications, enrichments)
def test_reasons_never_repeat_a_code(app, enrichment):
    result = rate(app, enrichment)

    for reasons in (result.refer_reasons, result.decline_reasons):
        codes = [r.code for r in reasons]
        assert len(codes) == len(set(codes))


# --- monotonicity: the properties that catch a mistyped factor row ------------------------


def premium_with(app, enrichment, **overrides):
    return rate(replace(app, **overrides), enrichment).indicative_premium_pence


@given(
    applications,
    enrichments,
    st.integers(min_value=0, max_value=MAX_REVENUE_PENCE),
    st.integers(min_value=0, max_value=MAX_REVENUE_PENCE),
)
def test_more_revenue_never_costs_less(app, enrichment, first, second):
    lower, higher = sorted((first, second))

    assert premium_with(app, enrichment, annual_revenue_pence=lower) <= premium_with(
        app, enrichment, annual_revenue_pence=higher
    )


@given(applications, enrichments, st.sampled_from(RequestedLimit), st.sampled_from(RequestedLimit))
def test_more_cover_never_costs_less(app, enrichment, first, second):
    lower, higher = sorted((first, second))

    assert premium_with(app, enrichment, requested_limit=lower) <= premium_with(
        app, enrichment, requested_limit=higher
    )


@given(
    applications,
    enrichments,
    st.integers(min_value=0, max_value=MAX_MONTHS),
    st.integers(min_value=0, max_value=MAX_MONTHS),
)
def test_a_longer_trading_history_never_costs_more(app, enrichment, first, second):
    shorter, longer = sorted((first, second))

    assert premium_with(app, enrichment, months_trading=longer) <= premium_with(
        app, enrichment, months_trading=shorter
    )


@given(
    applications,
    enrichments,
    st.integers(min_value=0, max_value=MAX_CLAIMS),
    st.integers(min_value=0, max_value=MAX_CLAIMS),
)
def test_more_claims_never_costs_less(app, enrichment, first, second):
    fewer, more = sorted((first, second))

    assert premium_with(app, enrichment, prior_claims_count=fewer) <= premium_with(
        app, enrichment, prior_claims_count=more
    )


@given(applications, enrichments)
def test_a_worse_outcome_is_never_reached_by_removing_a_problem(app, enrichment):
    result = rate(app, enrichment)
    cleaned = rate(
        replace(app, missing_fields=(), extraction_confidence=1.0),
        CLEAN_ENRICHMENT,
    )

    assert cleaned.decision <= result.decision
