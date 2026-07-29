import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import auth, documents, internal, submissions
from app.config import get_settings, startup_warnings
from app.db import DbSession, build_engine, build_sessionmaker
from app.middleware import LimitBodySize
from app.services.companies_house import CompaniesHouseClient
from app.services.extraction import AnthropicExtractor
from app.services.pdf import build_renderer
from app.services.storage import get_storage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log = logging.getLogger("uvicorn.error")
    for warning in startup_warnings(settings):
        log.warning(warning)
    engine = build_engine(settings)
    app.state.engine = engine
    app.state.sessionmaker = build_sessionmaker(engine)
    # One httpx/Anthropic connection pool per process, not per request.
    app.state.extractor = AnthropicExtractor(settings)
    app.state.ch_client = CompaniesHouseClient(settings)
    # LocalPdfRenderer (dev) or LambdaPdfRenderer (prod), built once — holds a boto3 client in prod.
    app.state.renderer = build_renderer(settings, get_storage())
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
# Added last so it wraps outermost: an oversized body is refused before a cookie is decrypted.
app.add_middleware(LimitBodySize)
app.include_router(auth.router)
app.include_router(submissions.router)
app.include_router(documents.router)
app.include_router(internal.router)


@app.get("/health")
async def health(db: DbSession) -> JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "error"})
    return JSONResponse(content={"status": "ok", "database": "ok"})
