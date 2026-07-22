from __future__ import annotations

from anthropic import AsyncAnthropic

from app.config import Settings
from app.schemas import ExtractedApplication

# Initial prompt; the full PRD ruleset + fixtures land in UW-021. See D-021.
EXTRACTION_SYSTEM_PROMPT = """\
You extract a Tech E&O / Cyber insurance application from a broker's free-text submission.

Rules:
- Never guess a numeric value. If revenue, years trading, or claims count is not stated, set the
  field to null and add its name to missing_fields.
- Map free-text descriptions of the business onto the sector enum; use "other" only when none fit.
- requested_limit_gbp must be one of the allowed limits; pick the nearest stated limit or null.
- Report extraction_confidence in [0,1]: how sure you are the fields reflect the submission.
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
