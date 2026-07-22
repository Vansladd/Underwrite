import httpx
import pytest
import respx

from app.config import Settings
from app.domain.enums import CompanyStatus
from app.services.companies_house import CompaniesHouseClient, normalise_company_number

BASE = "https://api.company-information.service.gov.uk"


def profile_json(**overrides) -> dict:
    base = {
        "company_number": "09876543",
        "company_name": "ACME ROBOTICS LIMITED",
        "company_status": "active",
        "company_status_detail": None,
        "date_of_creation": "2019-01-01",
        "sic_codes": ["62012"],
    }
    return {**base, **overrides}


@pytest.fixture
async def ch():
    async with httpx.AsyncClient(base_url=BASE, auth=httpx.BasicAuth("k", "")) as client:
        yield CompaniesHouseClient(Settings(), client=client)


@pytest.mark.parametrize(
    "raw,padded",
    [("6", "00000006"), ("09876543", "09876543"), ("SC123456", "SC123456"), ("sc1234", "SC001234")],
)
def test_normalise_company_number_pads_and_keeps_prefix(raw, padded):
    assert normalise_company_number(raw) == padded


@respx.mock
async def test_found_by_number(ch):
    respx.get(f"{BASE}/company/09876543").mock(
        return_value=httpx.Response(200, json=profile_json())
    )

    result = await ch.lookup("09876543", "Acme Robotics Ltd")

    assert result.found
    assert result.profile.company_status is CompanyStatus.ACTIVE
    assert result.profile.sic_codes == ["62012"]
    assert not result.rate_limited


@respx.mock
async def test_number_is_zero_padded_in_the_request(ch):
    route = respx.get(f"{BASE}/company/00000006").mock(
        return_value=httpx.Response(200, json=profile_json(company_number="00000006"))
    )

    await ch.lookup("6", "Acme")

    assert route.called


@respx.mock
async def test_found_by_search_refetches_full_profile(ch):
    respx.get(f"{BASE}/search/companies").mock(
        return_value=httpx.Response(200, json={"items": [{"company_number": "09876543"}]})
    )
    fetch = respx.get(f"{BASE}/company/09876543").mock(
        return_value=httpx.Response(200, json=profile_json())
    )

    result = await ch.lookup(None, "Acme Robotics Ltd")

    assert result.found and fetch.called
    assert result.profile.sic_codes == ["62012"]


@respx.mock
async def test_number_404_falls_back_to_search(ch):
    respx.get(f"{BASE}/company/09876543").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE}/search/companies").mock(
        return_value=httpx.Response(200, json={"items": [{"company_number": "07777777"}]})
    )
    respx.get(f"{BASE}/company/07777777").mock(
        return_value=httpx.Response(200, json=profile_json(company_number="07777777"))
    )

    result = await ch.lookup("09876543", "Acme Robotics Ltd")

    assert result.found
    assert result.profile.company_number == "07777777"


@respx.mock
async def test_search_no_hits_is_not_found(ch):
    respx.get(f"{BASE}/company/09876543").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE}/search/companies").mock(return_value=httpx.Response(200, json={"items": []}))

    result = await ch.lookup("09876543", "Nonexistent Co")

    assert not result.found
    assert not result.rate_limited


@respx.mock
async def test_429_returns_rate_limited_without_blocking(ch):
    respx.get(f"{BASE}/company/09876543").mock(
        return_value=httpx.Response(429, headers={"X-Ratelimit-Remain": "0"})
    )

    result = await ch.lookup("09876543", "Acme")

    assert not result.found
    assert result.rate_limited


@respx.mock
async def test_missing_sic_codes_key_defaults_to_empty(ch):
    payload = profile_json()
    del payload["sic_codes"]
    respx.get(f"{BASE}/company/09876543").mock(return_value=httpx.Response(200, json=payload))

    result = await ch.lookup("09876543", "Acme")

    assert result.profile.sic_codes == []
