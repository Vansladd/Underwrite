from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.enums import (
    CompanyStatus,
    DataVolume,
    Decision,
    ReasonCode,
    RequestedLimit,
    Sector,
)


@dataclass(frozen=True, slots=True)
class Application:
    company_name: str
    sector: Sector
    annual_revenue_pence: int
    months_trading: int
    prior_claims_count: int
    data_records_held: DataVolume
    requested_limit: RequestedLimit
    extraction_confidence: float = 1.0
    missing_fields: tuple[str, ...] = ()

    # A raw string compares equal to its StrEnum member but is not identical.
    def __post_init__(self) -> None:
        object.__setattr__(self, "sector", Sector(self.sector))
        object.__setattr__(self, "data_records_held", DataVolume(self.data_records_held))
        object.__setattr__(self, "requested_limit", RequestedLimit(self.requested_limit))
        object.__setattr__(self, "missing_fields", tuple(self.missing_fields))

        for name in ("annual_revenue_pence", "months_trading", "prior_claims_count"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must not be negative, got {value}")

        if not 0.0 <= self.extraction_confidence <= 1.0:
            raise ValueError(
                f"extraction_confidence must be between 0 and 1, got {self.extraction_confidence}"
            )


@dataclass(frozen=True, slots=True)
class Enrichment:
    ch_found: bool
    ch_company_status: CompanyStatus | None = None
    ch_name_match_score: float | None = None
    discrepancies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.ch_company_status is not None:
            object.__setattr__(self, "ch_company_status", CompanyStatus(self.ch_company_status))
        object.__setattr__(self, "discrepancies", tuple(self.discrepancies))

        if self.ch_name_match_score is not None and not 0.0 <= self.ch_name_match_score <= 1.0:
            raise ValueError(
                f"ch_name_match_score must be between 0 and 1, got {self.ch_name_match_score}"
            )


@dataclass(frozen=True, slots=True)
class Reason:
    code: ReasonCode
    message: str


# Decimal, not int: rounding happens once, in rate().
@dataclass(frozen=True, slots=True)
class FactorApplication:
    code: str
    band_label: str
    multiplier: Decimal
    reason: str
    premium_before_pence: Decimal
    premium_after_pence: Decimal


@dataclass(frozen=True, slots=True)
class RatingResult:
    rating_version: str
    decision: Decision
    base_premium_pence: int
    factors: tuple[FactorApplication, ...]
    indicative_premium_pence: int
    annual_premium_pence: int | None
    refer_reasons: tuple[Reason, ...] = field(default_factory=tuple)
    decline_reasons: tuple[Reason, ...] = field(default_factory=tuple)
