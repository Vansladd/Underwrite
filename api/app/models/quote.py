import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import QuoteStatus
from app.models.base import Base, calendar_date, pence, pg_enum, uuid_pk, written_at

if TYPE_CHECKING:
    from app.models.submission import Submission


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid_pk]
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"),
        unique=True,
    )

    quote_ref: Mapped[str] = mapped_column(unique=True)
    status: Mapped[QuoteStatus] = mapped_column(
        pg_enum(QuoteStatus, "quote_status"),
        default=QuoteStatus.ISSUED,
        server_default=text(f"'{QuoteStatus.ISSUED.value}'"),
        index=True,
    )

    limit_pence: Mapped[pence]
    excess_pence: Mapped[pence]
    gross_premium_pence: Mapped[pence]
    inception_date: Mapped[calendar_date]
    valid_until: Mapped[calendar_date] = mapped_column(index=True)

    # Nullable: a render failure must not lose the approval (UW-052).
    pdf_s3_key: Mapped[str | None]
    created_at: Mapped[written_at]

    submission: Mapped["Submission"] = relationship(back_populates="quote")
