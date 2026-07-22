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


@pytest.mark.llm
async def test_live_extraction_returns_populated_application():
    application = await AnthropicExtractor(Settings()).extract(
        "Please quote Acme Robotics Ltd (company no 09876543), a SaaS platform. "
        "Annual revenue about £2.5m, trading 6 years, no prior claims. They hold roughly "
        "500,000 customer records and want a £1m limit."
    )
    assert application.company_name
    assert application.sector is not None
    assert 0 <= application.extraction_confidence <= 1
