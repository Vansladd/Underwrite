from __future__ import annotations

from datetime import date

from app.domain.enums import CompanyStatus
from app.schemas import CompanyProfile

STRIKE_OFF_DETAIL = "active-proposal-to-strike-off"
_DAYS_PER_YEAR = 365.25


def detect_discrepancies(
    years_trading: float | None,
    profile: CompanyProfile,
    today: date | None = None,
) -> list[str]:
    # Sentences: they render verbatim in the ops dashboard. See D-022.
    today = today or date.today()
    found: list[str] = []

    if years_trading is not None and profile.date_of_creation is not None:
        age = (today - profile.date_of_creation).days / _DAYS_PER_YEAR
        if abs(age - years_trading) > 1:
            found.append(
                f"The submission states {years_trading:g} years trading, but Companies House "
                f"records incorporation on {profile.date_of_creation.isoformat()} "
                f"(about {age:.0f} years ago)."
            )

    if profile.company_status is not CompanyStatus.ACTIVE:
        found.append(
            f"Companies House shows the company status as "
            f"'{profile.company_status.value}', not active."
        )
    elif profile.company_status_detail == STRIKE_OFF_DETAIL:
        found.append(
            "The company is active but has a proposal to strike it off the register — "
            "a strong risk signal."
        )

    return found
