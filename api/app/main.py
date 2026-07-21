from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import submissions
from app.config import get_settings
from app.db import DbSession, build_engine, build_sessionmaker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = build_engine(get_settings())
    app.state.engine = engine
    app.state.sessionmaker = build_sessionmaker(engine)
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(title="Underwrite", version="0.1.0", lifespan=lifespan)
app.include_router(submissions.router)


@app.get("/health")
async def health(db: DbSession) -> JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "error"})
    return JSONResponse(content={"status": "ok", "database": "ok"})
