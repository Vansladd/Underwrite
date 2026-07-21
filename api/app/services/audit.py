import uuid
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AuditActor, AuditEventType, Decision
from app.domain.rating import RatingResult
from app.models import AuditEvent
from app.schemas import rating_to_orm_kwargs

MAX_DEPTH = 12
BYTES_PREVIEW = 64


def jsonable(value: Any) -> Any:
    """Coerce anything into something JSONB accepts. Never raises — see DECISIONS D-010."""
    return _coerce(value, depth=0, seen=frozenset())


def _coerce(value: Any, depth: int, seen: frozenset[int]) -> Any:
    # Enums before primitives: Decision is an int, and .value writes 0. See DECISIONS D-010.
    if isinstance(value, Decision):
        return value.name
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, str):
        return _safe_text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    # Before the Sequence branch, which would render a 2MB PDF as two million integers.
    if isinstance(value, bytes | bytearray | memoryview):
        return _describe_bytes(bytes(value))

    if depth >= MAX_DEPTH:
        return repr(value)
    if id(value) in seen:
        return f"<cycle: {type(value).__name__}>"

    deeper, marked = depth + 1, seen | {id(value)}
    try:
        return _coerce_container(value, deeper, marked)
    except Exception:
        # Total by construction: a payload must never be able to fail the caller's flush.
        return repr(value)


def _coerce_container(value: Any, depth: int, seen: frozenset[int]) -> Any:
    if isinstance(value, RatingResult):
        return _coerce(rating_to_orm_kwargs(value), depth, seen)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        # fields()/getattr, not asdict(): asdict deep-copies, and deepcopy raises on a socket.
        return {f.name: _coerce(getattr(value, f.name), depth, seen) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _coerce(item, depth, seen) for key, item in value.items()}
    if isinstance(value, Sequence | set | frozenset):
        return [_coerce(item, depth, seen) for item in value]
    return repr(value)


def _safe_text(value: str) -> str:
    # Postgres rejects \u0000 inside a jsonb string with UntranslatableCharacterError.
    return value.replace("\x00", "\\x00") if "\x00" in value else value


def _describe_bytes(raw: bytes) -> str:
    try:
        text = raw.decode()
    except UnicodeDecodeError:
        return f"<{len(raw)} bytes>"
    if "\x00" in text:
        return f"<{len(raw)} bytes>"
    return text if len(text) <= BYTES_PREVIEW else f"{text[:BYTES_PREVIEW]}… ({len(raw)} bytes)"


async def record_event(
    session: AsyncSession,
    submission_id: uuid.UUID,
    event_type: AuditEventType,
    actor: AuditActor,
    payload: Mapping[str, Any],
) -> AuditEvent:
    """Append one event. Flushes, so a bad submission_id fails here and not at commit."""
    if not isinstance(payload, Mapping):
        raise TypeError(f"payload must be a mapping, got {type(payload).__name__}")

    recorded = AuditEvent(
        submission_id=submission_id,
        event_type=event_type,
        actor=actor,
        payload=jsonable(payload),
    )
    session.add(recorded)
    await session.flush()
    return recorded
