import json
from pathlib import Path

import anthropic
import httpx
import pytest
import respx
from anthropic import AsyncAnthropic

from app.config import Settings
from app.domain.enums import DataVolume, RequestedLimit, Sector
from app.schemas import ExtractedApplication
from app.services.extraction import AnthropicExtractor, ExtractionRefused

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"
MESSAGES_URL = "https://api.anthropic.com/v1/messages"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def extractor(client: AsyncAnthropic) -> AnthropicExtractor:
    return AnthropicExtractor(Settings(extraction_model="claude-sonnet-5"), client=client)


def make_client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key="test", max_retries=0)


@respx.mock
async def test_extract_returns_populated_application_from_recorded_fixture():
    respx.post(MESSAGES_URL).mock(return_value=httpx.Response(200, json=load("acme_saas.json")))

    application = await extractor(make_client()).extract("Acme Robotics Ltd, SaaS, £2.5m rev")

    assert isinstance(application, ExtractedApplication)
    assert application.company_name == "Acme Robotics Ltd"
    assert application.sector is Sector.SAAS
    assert application.annual_revenue_gbp == 2_500_000
    assert application.data_records_held is DataVolume.HUNDRED_K_TO_1M
    assert application.requested_limit_gbp is RequestedLimit.GBP_1M
    assert application.missing_fields == []


@respx.mock
async def test_extract_sends_model_thinking_and_json_schema_format():
    route = respx.post(MESSAGES_URL).mock(
        return_value=httpx.Response(200, json=load("acme_saas.json"))
    )

    await extractor(make_client()).extract("...")

    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "claude-sonnet-5"
    assert body["thinking"] == {"type": "disabled"}
    assert body["output_config"]["format"]["type"] == "json_schema"


@respx.mock
async def test_refusal_raises_extraction_refused():
    respx.post(MESSAGES_URL).mock(return_value=httpx.Response(200, json=load("refusal.json")))

    with pytest.raises(ExtractionRefused):
        await extractor(make_client()).extract("...")


@respx.mock
async def test_server_error_propagates_without_retry_loop():
    respx.post(MESSAGES_URL).mock(return_value=httpx.Response(500, json={"error": {}}))

    with pytest.raises(anthropic.APIStatusError):
        await extractor(make_client()).extract("...")


EMAILS = FIXTURES / "emails"


def email(name: str) -> str:
    return (EMAILS / name).read_text()


@pytest.fixture
async def live_extractor():
    # Context-managed so the real socket closes (filterwarnings=error rejects the leak).
    async with AsyncAnthropic() as client:
        yield AnthropicExtractor(Settings(), client=client)


@pytest.mark.llm
async def test_clean_email_extracts_all_rated_fields(live_extractor):
    application = await live_extractor.extract(email("clean.txt"))

    assert application.company_name
    assert application.sector is Sector.SAAS
    assert application.annual_revenue_gbp == 2_500_000
    assert application.requested_limit_gbp is RequestedLimit.GBP_1M
    assert application.prior_claims_count == 0
    assert application.missing_fields == []


@pytest.mark.llm
async def test_rambling_email_resolves_buried_fields(live_extractor):
    application = await live_extractor.extract(email("rambling.txt"))

    assert application.company_name
    assert application.sector is Sector.FINTECH
    assert application.requested_limit_gbp is RequestedLimit.GBP_2M
    assert application.prior_claims_count == 0
    assert application.data_records_held is DataVolume.OVER_1M
    assert 0 <= application.extraction_confidence <= 1


@pytest.mark.llm
async def test_missing_revenue_email_never_guesses(live_extractor):
    application = await live_extractor.extract(email("missing_revenue.txt"))

    # The assertion that proves the never-guess rule (UW-021 DoD).
    assert application.annual_revenue_gbp is None
    assert "annual_revenue_gbp" in application.missing_fields
    assert application.sector is Sector.HEALTHTECH
    assert application.requested_limit_gbp is RequestedLimit.GBP_500K
    assert application.prior_claims_count == 1
