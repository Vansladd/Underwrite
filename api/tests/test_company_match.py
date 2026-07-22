import pytest

from app.services.company_match import name_match_score, normalise_company_name


def test_ltd_matches_limited():
    assert name_match_score("Acme Ltd", "ACME LIMITED") >= 0.95


def test_a_genuinely_different_company_scores_low():
    assert name_match_score("Acme Ltd", "Globex Solutions LIMITED") < 0.85


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Acme Ltd", "ACME LIMITED"),
        ("The Acme Company", "ACME COMPANY"),
        ("M&S Ltd", "M AND S LIMITED"),
        ("Acme PLC", "ACME PUBLIC LIMITED COMPANY"),
        ("Acme LLP", "ACME LIMITED LIABILITY PARTNERSHIP"),
    ],
)
def test_normalisation(raw, expected):
    assert normalise_company_name(raw) == expected
