import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import AuditActor, AuditEventType
from app.models.base import Base, json_object, pg_enum, uuid_pk, written_at

if TYPE_CHECKING:
    from app.models.submission import Submission
    from app.models.user import User


class AuditTrailIsAppendOnly(Exception):
    pass


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index(None, "submission_id", "occurred_at"),)

    id: Mapped[uuid_pk]
    # RESTRICT: a trail a DELETE can erase is not a trail.
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="RESTRICT")
    )

    event_type: Mapped[AuditEventType] = mapped_column(pg_enum(AuditEventType, "audit_event_type"))
    actor: Mapped[AuditActor] = mapped_column(pg_enum(AuditActor, "audit_actor"))
    # Names the operator when actor is OPS; null otherwise. See D-026.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    payload: Mapped[json_object]
    occurred_at: Mapped[written_at]

    submission: Mapped["Submission"] = relationship(back_populates="audit_events")
    # Read-only join on actor_id; selectinload it to populate actor_name (async, no lazy load).
    operator: Mapped["User | None"] = relationship(viewonly=True, lazy="raise")

    @property
    def actor_name(self) -> str | None:
        # None when not eager-loaded, rather than tripping lazy='raise' during serialization.
        if "operator" in inspect(self).unloaded:
            return None
        return self.operator.display_name if self.operator is not None else None


# Registered here so a Lambda importing only models still gets the guard. See DECISIONS D-010.
@event.listens_for(AuditEvent, "before_update")
def _refuse_update(mapper, connection, target) -> None:
    raise AuditTrailIsAppendOnly(f"audit event {target.id} cannot be modified")


@event.listens_for(AuditEvent, "before_delete")
def _refuse_delete(mapper, connection, target) -> None:
    raise AuditTrailIsAppendOnly(f"audit event {target.id} cannot be deleted")
