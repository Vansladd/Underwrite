from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import CompanyStatus


class CompanyProfile(BaseModel):
    """The subset of a Companies House `/company/{number}` payload we act on."""

    model_config = ConfigDict(extra="ignore")

    company_number: str
    company_name: str
    company_status: CompanyStatus
    company_status_detail: str | None = None
    date_of_creation: date | None = None
    # Absent (not empty) on many companies, and search hits never carry it. See R5.
    sic_codes: list[str] = Field(default_factory=list)
