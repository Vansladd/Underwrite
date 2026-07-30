from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_sweeper_token
from app.db import DbSession
from app.domain.period import InvalidPeriod, YearMonth
from app.schemas import BordereauRun, ExpirySweep
from app.services.bordereau import export_bordereau
from app.services.expiry import expire_quotes
from app.services.storage import StorageDep

# Gate on the router, not the route: an unclassified internal route can never be added ungated.
router = APIRouter(
    prefix="/api/internal",
    tags=["internal"],
    dependencies=[Depends(require_sweeper_token)],
)


@router.post("/quotes/expire")
async def sweep_expired_quotes(db: DbSession) -> ExpirySweep:
    # The server picks the date; a caller-supplied one would let the schedule expire the future.
    today = date.today()
    refs = await expire_quotes(db, today=today)
    return ExpirySweep(swept_on=today, expired=len(refs), quote_refs=refs)


# Declared before /{period}, which would otherwise swallow "latest" and 422 it as a bad format.
@router.post("/bordereaux/latest")
async def export_last_closed(db: DbSession, storage: StorageDep) -> BordereauRun:
    """The month that just closed. The server picks it, in the reporting zone — a caller deriving
    it from its own UTC clock files the wrong month for an hour each BST 1st, and logs success."""
    return _as_run(await export_bordereau(db, storage, period=YearMonth.last_closed()))


@router.post("/bordereaux/{period}")
async def export_period(period: str, db: DbSession, storage: StorageDep) -> BordereauRun:
    try:
        month = YearMonth.parse(period)
    except InvalidPeriod as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    # A month that has not finished cannot be reported: the CSV would be a partial the carrier
    # reconciles as complete, and re-running would silently change an already-filed figure.
    if month >= YearMonth.current():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"period {month} has not closed yet"
        )

    return _as_run(await export_bordereau(db, storage, period=month))


def _as_run(run) -> BordereauRun:
    return BordereauRun(
        period=run.period, s3_key=run.s3_key, quotes=run.quotes, size_bytes=run.size_bytes
    )
