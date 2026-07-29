from datetime import date

from fastapi import APIRouter, Depends

from app.api.deps import require_sweeper_token
from app.db import DbSession
from app.schemas import ExpirySweep
from app.services.expiry import expire_quotes

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
