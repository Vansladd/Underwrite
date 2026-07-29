from datetime import date

from app.domain.enums import CompanyStatus
from app.schemas import CompanyProfile
from app.services.discrepancies import detect_discrepancies

TODAY = date(2026, 1, 1)


def profile(**overrides) -> CompanyProfile:
    base = {
        "company_number": "09876543",
        "company_name": "ACME LIMITED",
        "company_status": CompanyStatus.ACTIVE,
        "company_status_detail": None,
        "date_of_creation": date(2020, 1, 1),
        "sic_codes": [],
    }
    return CompanyProfile(**{**base, **overrides})


def test_clean_active_matching_age_has_no_discrepancies():
    assert detect_discrepancies(6, profile(), today=TODAY) == []


def test_within_one_year_tolerance_is_not_flagged():
    assert detect_discrepancies(6, profile(date_of_creation=date(2020, 3, 1)), today=TODAY) == []


def test_age_mismatch_is_flagged():
    found = detect_discrepancies(2, profile(date_of_creation=date(2015, 1, 1)), today=TODAY)
    assert len(found) == 1
    assert "years trading" in found[0]


def test_non_active_status_is_flagged():
    found = detect_discrepancies(6, profile(company_status=CompanyStatus.DISSOLVED), today=TODAY)
    assert any("not active" in sentence for sentence in found)


def test_active_proposal_to_strike_off_is_flagged():
    found = detect_discrepancies(
        6, profile(company_status_detail="active-proposal-to-strike-off"), today=TODAY
    )
    assert any("strike it off" in sentence for sentence in found)


def test_a_single_year_is_not_reported_as_1_years():
    # These strings render verbatim in the queue headline and the drawer.
    found = detect_discrepancies(
        3.0,
        profile(date_of_creation=date(2025, 7, 1)),
        today=date(2026, 7, 1),
    )

    assert "1 year ago" in found[0]
    assert "1 years" not in found[0]


def test_a_single_stated_year_is_singular_too():
    found = detect_discrepancies(
        1.0,
        profile(date_of_creation=date(2016, 7, 1)),
        today=date(2026, 7, 1),
    )

    assert "states 1 year trading" in found[0]
