import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import submissions
from app.config import DEFAULT_OPS_PASSWORD, get_settings
from app.db import DbSession, build_engine, build_sessionmaker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.ops_password == DEFAULT_OPS_PASSWORD:
        logging.getLogger("uvicorn.error").warning(
            "OPS_PASSWORD is still the shipped default; ops routes are effectively open"
        )
    engine = build_engine(settings)
    app.state.engine = engine
    app.state.sessionmaker = build_sessionmaker(engine)
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(
    title="Underwrite",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
)
app.include_router(submissions.router)


@app.get("/health")
async def health(db: DbSession) -> JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "error"})
    return JSONResponse(content={"status": "ok", "database": "ok"})
