import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AuditActor, AuditEventType, Decision
from app.domain.rating import RatingResult
from app.models import AuditEvent
from app.schemas import rating_to_orm_kwargs


class AuditTrailIsAppendOnly(Exception):
    pass


def jsonable(value: Any) -> Any:
    """Coerce anything into something JSONB accepts. Never raises — see DECISIONS D-010."""
    # Enums before primitives: Decision is an int, and .value writes 0. See DECISIONS D-010.
    if isinstance(value, Decision):
        return value.name
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, RatingResult):
        return jsonable(rating_to_orm_kwargs(value))
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence | set | frozenset):
        return [jsonable(item) for item in value]
    return repr(value)


async def record_event(
    session: AsyncSession,
    submission_id: uuid.UUID,
    event_type: AuditEventType,
    actor: AuditActor,
    payload: Mapping[str, Any],
) -> AuditEvent:
    """Append one event. Flushes, so a bad submission_id fails here and not at commit."""
    recorded = AuditEvent(
        submission_id=submission_id,
        event_type=event_type,
        actor=actor,
        payload=jsonable(payload),
    )
    session.add(recorded)
    await session.flush()
    return recorded


@event.listens_for(AuditEvent, "before_update")
def _refuse_update(mapper, connection, target) -> None:
    raise AuditTrailIsAppendOnly(f"audit event {target.id} cannot be modified")


@event.listens_for(AuditEvent, "before_delete")
def _refuse_delete(mapper, connection, target) -> None:
    raise AuditTrailIsAppendOnly(f"audit event {target.id} cannot be deleted")
