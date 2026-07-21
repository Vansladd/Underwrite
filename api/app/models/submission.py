from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import InputMode, SubmissionStatus
from app.models.base import Base, created_at, long_text, pg_enum, updated_at, uuid_pk

if TYPE_CHECKING:
    from app.models.audit_event import AuditEvent
    from app.models.enrichment import Enrichment
    from app.models.extraction import Extraction
    from app.models.quote import Quote
    from app.models.rating import Rating


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid_pk]
    status: Mapped[SubmissionStatus] = mapped_column(
        pg_enum(SubmissionStatus, "submission_status"),
        default=SubmissionStatus.RECEIVED,
        index=True,
    )
    input_mode: Mapped[InputMode] = mapped_column(pg_enum(InputMode, "input_mode"))
    raw_input: Mapped[long_text]
    created_at: Mapped[created_at]
    updated_at: Mapped[updated_at]

    extraction: Mapped["Extraction | None"] = relationship(back_populates="submission")
    enrichment: Mapped["Enrichment | None"] = relationship(back_populates="submission")
    rating: Mapped["Rating | None"] = relationship(back_populates="submission")
    quote: Mapped["Quote | None"] = relationship(back_populates="submission")
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="submission",
        order_by="AuditEvent.occurred_at",
    )
