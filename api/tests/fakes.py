from __future__ import annotations

from app.schemas import ExtractedApplication
from app.services.companies_house import CompaniesHouseLookup


class FakeExtractor:
    def __init__(
        self,
        result: ExtractedApplication | None = None,
        error: Exception | None = None,
        model: str = "claude-sonnet-5",
    ) -> None:
        self.result = result
        self.error = error
        self._model = model
        self.calls: list[str] = []

    @property
    def model(self) -> str:
        return self._model

    async def extract(self, raw_input: str) -> ExtractedApplication:
        self.calls.append(raw_input)
        if self.error is not None:
            raise self.error
        assert self.result is not None, "FakeExtractor called without a result configured"
        return self.result

    async def aclose(self) -> None:
        pass


class FakeRenderer:
    """Records calls and returns a key, or raises `error` to exercise the best-effort path."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def render_and_store(self, quote_id: str, html: str) -> str:
        self.calls.append((quote_id, html))
        if self.error is not None:
            raise self.error
        return f"generated/{quote_id}.pdf"


class FakeChClient:
    def __init__(
        self,
        lookup: CompaniesHouseLookup | None = None,
        error: Exception | None = None,
    ) -> None:
        self.lookup_result = lookup or CompaniesHouseLookup(None)
        self.error = error
        self.calls: list[tuple[str | None, str]] = []

    async def lookup(self, company_number: str | None, company_name: str) -> CompaniesHouseLookup:
        self.calls.append((company_number, company_name))
        if self.error is not None:
            raise self.error
        return self.lookup_result

    async def aclose(self) -> None:
        pass
