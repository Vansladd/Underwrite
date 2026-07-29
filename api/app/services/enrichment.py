from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.rating import Enrichment
from app.schemas import ExtractedApplication
from app.services.companies_house import CompaniesHouseClient, CompaniesHouseUnavailable
from app.services.company_match import name_match_score
from app.services.discrepancies import detect_discrepancies


@dataclass(frozen=True)
class EnrichmentOutcome:
    orm_kwargs: dict[str, Any]
    domain: Enrichment
    error: str | None = None


def _empty(lookup_error: str | None = None, rate_limited: bool = False) -> EnrichmentOutcome:
    # Either way the lookup never produced an answer about the register. See D-029.
    failed = lookup_error is not None or rate_limited
    return EnrichmentOutcome(
        orm_kwargs={
            "ch_found": False,
            "ch_company_number": None,
            "ch_company_name": None,
            "ch_company_status": None,
            "ch_company_status_detail": None,
            "ch_date_of_creation": None,
            "ch_name_match_score": None,
            "sic_codes": [],
            "discrepancies": [],
            "rate_limited": rate_limited,
            "lookup_error": lookup_error,
        },
        domain=Enrichment(ch_found=False, lookup_failed=failed),
        error=lookup_error,
    )


async def enrich(
    ch_client: CompaniesHouseClient, application: ExtractedApplication
) -> EnrichmentOutcome:
    if application.company_name is None:
        return _empty()

    try:
        lookup = await ch_client.lookup(application.company_number, application.company_name)
    except CompaniesHouseUnavailable as error:
        # Best-effort: a failed lookup degrades to CH_UNAVAILABLE -> REFER, never a stage failure.
        return _empty(lookup_error=error.reason)
    except Exception:
        # Backstop for anything the client did not classify; the pipeline must not fail here.
        return _empty(lookup_error="unknown")

    if lookup.profile is None:
        return _empty(rate_limited=lookup.rate_limited)

    profile = lookup.profile
    score = name_match_score(application.company_name, profile.company_name)
    discrepancies = detect_discrepancies(application.years_trading, profile)

    return EnrichmentOutcome(
        orm_kwargs={
            "ch_found": True,
            "ch_company_number": profile.company_number,
            "ch_company_name": profile.company_name,
            "ch_company_status": profile.company_status,
            "ch_company_status_detail": profile.company_status_detail,
            "ch_date_of_creation": profile.date_of_creation,
            "ch_name_match_score": score,
            "sic_codes": profile.sic_codes,
            "discrepancies": discrepancies,
            "rate_limited": lookup.rate_limited,
            "lookup_error": None,
        },
        domain=Enrichment(
            ch_found=True,
            ch_company_status=profile.company_status,
            ch_name_match_score=score,
            discrepancies=tuple(discrepancies),
        ),
    )
