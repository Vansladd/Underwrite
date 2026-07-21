import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import CompanyStatus
from app.models.base import Base, created_at, json_list, pg_enum, uuid_pk

if TYPE_CHECKING:
    from app.models.submission import Submission


class Enrichment(Base):
    __tablename__ = "enrichments"

    id: Mapped[uuid_pk]
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"),
        unique=True,
    )

    ch_found: Mapped[bool]
    ch_company_number: Mapped[str | None]
    ch_company_name: Mapped[str | None]
    ch_company_status: Mapped[CompanyStatus | None] = mapped_column(
        pg_enum(CompanyStatus, "company_status")
    )
    # 'active' + 'active-proposal-to-strike-off' is a live company being struck off.
    ch_company_status_detail: Mapped[str | None]
    ch_date_of_creation: Mapped[date | None]
    ch_name_match_score: Mapped[float | None]

    # Strings, never ints: SIC codes carry leading zeros.
    sic_codes: Mapped[json_list]
    discrepancies: Mapped[json_list]

    rate_limited: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[created_at]

    submission: Mapped["Submission"] = relationship(back_populates="enrichment")
