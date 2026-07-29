from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import DataVolume, InputMode, RequestedLimit, Sector
from app.schemas.extraction import ExtractedApplication


class FormApplication(BaseModel):
    """What the applicant types. No confidence field: the form is not a guess. See D-028."""

    model_config = ConfigDict(extra="forbid")

    company_name: str | None = None
    company_number: str | None = None
    sector: Sector | None = None
    annual_revenue_gbp: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    years_trading: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    prior_claims_count: int | None = Field(default=None, ge=0)
    data_records_held: DataVolume | None = None
    requested_limit_gbp: RequestedLimit | None = None

    def to_extracted(self) -> ExtractedApplication:
        return ExtractedApplication(
            **self.model_dump(), extraction_confidence=1.0, missing_fields=[]
        )


class SubmissionCreate(BaseModel):
    input_mode: InputMode
    raw_input: str | None = Field(default=None, min_length=1)
    application: FormApplication | None = None

    @model_validator(mode="after")
    def check_the_mode_carries_its_payload(self) -> "SubmissionCreate":
        if self.input_mode is InputMode.PDF_UPLOAD:
            raise ValueError("upload a PDF to /api/submissions/pdf, not to this route")
        if self.input_mode is InputMode.FORM and self.application is None:
            raise ValueError("form submissions must carry an application")
        if self.input_mode is InputMode.PASTE and self.raw_input is None:
            raise ValueError("pasted submissions must carry raw_input")
        return self


class DeclineRequest(BaseModel):
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def reason_is_not_blank(cls, value: str) -> str:
        # min_length counts characters; a reason of only whitespace is no reason.
        stripped = value.strip()
        if not stripped:
            raise ValueError("reason must not be blank")
        return stripped
