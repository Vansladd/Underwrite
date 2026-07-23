import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer

from app.domain.enums import (
    AuditActor,
    AuditEventType,
    CompanyStatus,
    DataVolume,
    Decision,
    InputMode,
    QuoteStatus,
    ReasonCode,
    RequestedLimit,
    Sector,
    SubmissionStatus,
)

# String on the way out too: a JSON number would be a double again in the browser.
ExactDecimal = Annotated[Decimal, PlainSerializer(str, return_type=str)]

# By name; unknown names fall through to pydantic. See DECISIONS D-009.
DecisionName = Annotated[
    Decision,
    BeforeValidator(lambda v: Decision.__members__.get(v, v) if isinstance(v, str) else v),
    PlainSerializer(lambda d: d.name, return_type=str),
]


class Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FactorRead(Read):
    code: str
    band_label: str
    multiplier: ExactDecimal
    reason: str
    premium_before_pence: ExactDecimal
    premium_after_pence: ExactDecimal


class ReasonRead(Read):
    code: ReasonCode
    message: str


class ExtractionRead(Read):
    id: uuid.UUID
    company_name: str | None
    company_number: str | None
    sector: Sector | None
    annual_revenue_pence: int | None
    months_trading: int | None
    prior_claims_count: int | None
    data_records_held: DataVolume | None
    requested_limit: RequestedLimit | None
    extraction_confidence: float
    missing_fields: list[str]
    model: str
    created_at: datetime


class EnrichmentRead(Read):
    id: uuid.UUID
    ch_found: bool
    ch_company_number: str | None
    ch_company_name: str | None
    ch_company_status: CompanyStatus | None
    ch_company_status_detail: str | None
    ch_date_of_creation: date | None
    ch_name_match_score: float | None
    sic_codes: list[str]
    discrepancies: list[str]
    rate_limited: bool
    created_at: datetime


class RatingRead(Read):
    id: uuid.UUID
    rating_version: str
    decision: DecisionName
    base_premium_pence: int
    indicative_premium_pence: int
    annual_premium_pence: int | None
    factors: list[FactorRead]
    refer_reasons: list[ReasonRead]
    decline_reasons: list[ReasonRead]
    created_at: datetime


class QuoteRead(Read):
    id: uuid.UUID
    quote_ref: str
    status: QuoteStatus
    limit_pence: int
    excess_pence: int
    gross_premium_pence: int
    inception_date: date
    valid_until: date
    pdf_s3_key: str | None
    created_at: datetime


class AuditEventRead(Read):
    id: uuid.UUID
    event_type: AuditEventType
    actor: AuditActor
    actor_name: str | None = None
    payload: dict[str, Any]
    occurred_at: datetime


class SubmissionRead(Read):
    id: uuid.UUID
    status: SubmissionStatus
    input_mode: InputMode
    raw_input: str | None
    created_at: datetime
    updated_at: datetime


# The queue row: flattens the fields the operator scans before opening a submission.
class SubmissionListItem(Read):
    id: uuid.UUID
    status: SubmissionStatus
    input_mode: InputMode
    created_at: datetime
    company_name: str | None
    company_number: str | None
    sector: Sector | None
    annual_revenue_pence: int | None
    requested_limit: RequestedLimit | None
    premium_pence: int | None
    decision: DecisionName | None
    headline: str | None


class SubmissionDetail(SubmissionRead):
    extraction: ExtractionRead | None = None
    enrichment: EnrichmentRead | None = None
    rating: RatingRead | None = None
    quote: QuoteRead | None = None
    audit_events: list[AuditEventRead] = Field(default_factory=list)


# Whole-table counts for the queue tabs, so they don't under-report a paginated page.
class SubmissionStats(BaseModel):
    total: int
    by_status: dict[str, int]
