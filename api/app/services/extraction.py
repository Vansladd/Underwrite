from __future__ import annotations

from anthropic import AsyncAnthropic

from app.config import Settings
from app.schemas import ExtractedApplication

# See D-021. The response schema (with enum values) is sent by the SDK; this adds the mapping
# and never-guess rules the schema alone can't express.
EXTRACTION_SYSTEM_PROMPT = """\
You extract a Tech E&O / Cyber insurance application from a broker's free-text submission
(usually an email). Populate the structured fields from what the submission actually states.

Never guess a number. If annual revenue, years trading, or prior claims count is not stated,
set that field to null and add its exact field name to missing_fields. "A few years", "a
handful of claims", or a revenue you infer from headcount are all not-stated — do not convert
them into a number. An explicit "no claims" or "clean record" means prior_claims_count = 0; that
is stated, not guessed.

Map the business description onto the sector enum: SaaS/platform → saas; payments/lending/banking
→ fintech; medical/clinical/health data → healthtech; online retail/store → ecommerce; models or
LLMs as the core product → ai_ml; a two-sided platform connecting buyers and sellers → marketplace;
digital assets/blockchain/tokens → crypto. Use other only when none genuinely fit.

requested_limit_gbp must be one of the allowed limits; pick the nearest one to the amount the
broker asks for, or null if no limit is mentioned. company_number only when a Companies House
number is clearly given (an 8-character alphanumeric code), else null. data_records_held maps the
count of personal/customer records to its band.

extraction_confidence is your own [0,1] estimate of how faithfully these fields reflect the
submission — lower it when fields are inferred, ambiguous, or the text is vague. It is not a
probability and is not calibrated; a low value is a signal to refer, not a measured error rate.
Return only the structured fields."""


class ExtractionRefused(Exception):
    def __init__(self, stop_details: object) -> None:
        super().__init__(f"the model refused to extract: {stop_details!r}")
        self.stop_details = stop_details


class AnthropicExtractor:
    def __init__(self, settings: Settings, client: AsyncAnthropic | None = None) -> None:
        self._model = settings.extraction_model
        self._max_tokens = settings.extraction_max_tokens
        self._client = client or AsyncAnthropic(api_key=settings.anthropic_api_key or None)

    @property
    def model(self) -> str:
        return self._model

    async def extract(self, raw_input: str) -> ExtractedApplication:
        response = await self._client.messages.parse(
            model=self._model,
            max_tokens=self._max_tokens,
            # Disabled, not adaptive: extraction is mechanical and cost-sensitive. See D-021.
            thinking={"type": "disabled"},
            system=[
                {
                    "type": "text",
                    "text": EXTRACTION_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": raw_input}],
            output_format=ExtractedApplication,
        )
        if response.stop_reason == "refusal":
            raise ExtractionRefused(response.stop_details)
        return response.parsed_output

    async def aclose(self) -> None:
        await self._client.close()
