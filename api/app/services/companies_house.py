from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import Settings
from app.schemas import CompanyProfile


def normalise_company_number(raw: str) -> str:
    # 8 chars: an optional alpha prefix (SC/NI/OC/FC/...) then zero-padded digits. Integer
    # parsing drops Scotland, NI, and every LLP. See R5.1.
    cleaned = "".join(raw.split()).upper()
    prefix = "".join(c for c in cleaned if c.isalpha())
    digits = cleaned[len(prefix) :]
    return prefix + digits.zfill(8 - len(prefix))


@dataclass(frozen=True)
class CompaniesHouseLookup:
    profile: CompanyProfile | None
    rate_limited: bool = False

    @property
    def found(self) -> bool:
        return self.profile is not None


class CompaniesHouseClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=settings.companies_house_base_url,
            auth=httpx.BasicAuth(settings.companies_house_api_key, ""),
            timeout=10.0,
        )

    async def lookup(self, company_number: str | None, company_name: str) -> CompaniesHouseLookup:
        if company_number:
            profile, limited = await self._get_company(normalise_company_number(company_number))
            if limited:
                return CompaniesHouseLookup(None, rate_limited=True)
            if profile is not None:
                return CompaniesHouseLookup(profile)

        number, limited = await self._search(company_name)
        if limited or number is None:
            return CompaniesHouseLookup(None, rate_limited=limited)

        # Refetch by number: search hits carry no sic_codes. See R5.
        profile, limited = await self._get_company(number)
        return CompaniesHouseLookup(profile, rate_limited=limited)

    async def _get_company(self, number: str) -> tuple[CompanyProfile | None, bool]:
        response = await self._client.get(f"/company/{number}")
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            return None, True
        if response.status_code == httpx.codes.NOT_FOUND:
            return None, False
        response.raise_for_status()
        return CompanyProfile.model_validate(response.json()), False

    async def _search(self, name: str) -> tuple[str | None, bool]:
        response = await self._client.get(
            "/search/companies", params={"q": name, "items_per_page": 1}
        )
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            return None, True
        response.raise_for_status()
        items = response.json().get("items", [])
        return (items[0]["company_number"] if items else None), False
