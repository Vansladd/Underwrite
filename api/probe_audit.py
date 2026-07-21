import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.enums import AuditActor, AuditEventType, InputMode
from app.models import AuditEvent, Submission

URL = "postgresql+asyncpg://underwrite:underwrite@db:5432/underwrite"


async def main():
    engine = create_async_engine(URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        sub = Submission(input_mode=InputMode.PASTE, raw_input="probe")
        s.add(sub)
        await s.flush()
        for label, payload in [
            ("Decimal", {"multiplier": Decimal("1.35")}),
            ("datetime", {"at": datetime.now(UTC)}),
            ("enum", {"actor": AuditActor.SYSTEM}),
            ("uuid", {"id": sub.id}),
            ("tuple-key", {(1, 2): "x"}),
        ]:
            s.add(
                AuditEvent(
                    submission_id=sub.id,
                    event_type=AuditEventType.RATING_COMPLETED,
                    actor=AuditActor.SYSTEM,
                    payload=payload,
                )
            )
            try:
                await s.flush()
                print(f"{label:12} ok")
            except Exception as e:
                print(f"{label:12} {type(e).__name__}: {str(e)[:70]}")
                await s.rollback()
                return
        await s.rollback()
    await engine.dispose()


asyncio.run(main())
