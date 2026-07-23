import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import auth, documents, submissions
from app.config import DEFAULT_OPERATOR_PASSWORD, DEFAULT_SECRET_KEY, get_settings
from app.db import DbSession, build_engine, build_sessionmaker
from app.services.companies_house import CompaniesHouseClient
from app.services.extraction import AnthropicExtractor


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log = logging.getLogger("uvicorn.error")
    if settings.secret_key == DEFAULT_SECRET_KEY:
        log.warning("SECRET_KEY is the shipped default; sessions are forgeable — set it in prod")
    if settings.session_secure and settings.seed_operator_password == DEFAULT_OPERATOR_PASSWORD:
        log.warning(
            "SEED_OPERATOR_PASSWORD is still the public default on a secure (prod) deployment — "
            "set a strong secret before exposing the URL"
        )
    engine = build_engine(settings)
    app.state.engine = engine
    app.state.sessionmaker = build_sessionmaker(engine)
    # One httpx/Anthropic connection pool per process, not per request.
    app.state.extractor = AnthropicExtractor(settings)
    app.state.ch_client = CompaniesHouseClient(settings)
    try:
        yield
    finally:
        await app.state.extractor.aclose()
        await app.state.ch_client.aclose()
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
_settings = get_settings()
app.add_middleware(
    SessionMiddleware,
    secret_key=_settings.secret_key,
    session_cookie="uw_session",
    https_only=_settings.session_secure,
    same_site="lax",
)
app.include_router(auth.router)
app.include_router(submissions.router)
app.include_router(documents.router)


@app.get("/health")
async def health(db: DbSession) -> JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "error"})
    return JSONResponse(content={"status": "ok", "database": "ok"})
