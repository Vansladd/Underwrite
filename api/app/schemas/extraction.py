from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import DataVolume, RequestedLimit, Sector
from app.domain.rating import Application

REQUIRED_FOR_RATING = (
    "company_name",
    "sector",
    "annual_revenue_gbp",
    "years_trading",
    "prior_claims_count",
    "data_records_held",
    "requested_limit_gbp",
)


class IncompleteExtraction(Exception):
    def __init__(self, missing: tuple[str, ...]) -> None:
        self.missing = missing
        super().__init__(f"cannot rate without {', '.join(missing)}")


def to_pence(pounds: float) -> int:
    # Decimal(str(x)), never x * 100: int(8.7 * 100) is 869.
    return int((Decimal(str(pounds)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def to_months(years: float) -> int:
    # RATING_SPEC D5: convert once here, never compare the float again.
    return int((Decimal(str(years)) * 12).quantize(Decimal(1), rounding=ROUND_HALF_UP))


class ExtractedApplication(BaseModel):
    """The `messages.parse()` output format — broker units, not storage units."""

    # forbid + allow_inf_nan close two silent-null holes. See DECISIONS D-009.
    model_config = ConfigDict(extra="forbid")

    company_name: str | None = None
    company_number: str | None = None
    sector: Sector | None = None
    annual_revenue_gbp: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    years_trading: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    prior_claims_count: int | None = Field(default=None, ge=0)
    data_records_held: DataVolume | None = None
    requested_limit_gbp: RequestedLimit | None = None
    extraction_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    missing_fields: list[str] = Field(default_factory=list)

    def missing_rated_fields(self) -> tuple[str, ...]:
        return tuple(name for name in REQUIRED_FOR_RATING if getattr(self, name) is None)

    def to_domain(self) -> Application:
        missing = self.missing_rated_fields()
        if missing:
            raise IncompleteExtraction(missing)

        return Application(
            company_name=self.company_name,
            sector=self.sector,
            annual_revenue_pence=to_pence(self.annual_revenue_gbp),
            months_trading=to_months(self.years_trading),
            prior_claims_count=self.prior_claims_count,
            data_records_held=self.data_records_held,
            requested_limit=self.requested_limit_gbp,
            extraction_confidence=self.extraction_confidence,
            missing_fields=tuple(self.missing_fields),
        )

    # Only the three columns whose name or unit differs; a new field needs no edit here.
    def to_orm_kwargs(self, model: str) -> dict:
        converted = {"annual_revenue_gbp", "years_trading", "requested_limit_gbp"}
        return {
            **self.model_dump(exclude=converted),
            "annual_revenue_pence": (
                None if self.annual_revenue_gbp is None else to_pence(self.annual_revenue_gbp)
            ),
            "months_trading": (
                None if self.years_trading is None else to_months(self.years_trading)
            ),
            "requested_limit": self.requested_limit_gbp,
            "model": model,
        }
