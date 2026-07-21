import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import DataVolume, RequestedLimit, Sector
from app.models.base import (
    Base,
    created_at,
    json_list,
    optional_pence,
    pg_enum,
    pg_enum_by_name,
    uuid_pk,
)

if TYPE_CHECKING:
    from app.models.submission import Submission


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[uuid_pk]
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"),
        unique=True,
    )

    # Nullable: the never-guess rule returns null plus a missing_fields entry.
    company_name: Mapped[str | None]
    company_number: Mapped[str | None]
    sector: Mapped[Sector | None] = mapped_column(pg_enum(Sector, "sector"))
    annual_revenue_pence: Mapped[optional_pence]
    months_trading: Mapped[int | None]
    prior_claims_count: Mapped[int | None]
    data_records_held: Mapped[DataVolume | None] = mapped_column(pg_enum(DataVolume, "data_volume"))
    requested_limit: Mapped[RequestedLimit | None] = mapped_column(
        pg_enum_by_name(RequestedLimit, "requested_limit")
    )

    extraction_confidence: Mapped[float]
    missing_fields: Mapped[json_list]
    model: Mapped[str]
    created_at: Mapped[created_at]

    submission: Mapped["Submission"] = relationship(back_populates="extraction")
