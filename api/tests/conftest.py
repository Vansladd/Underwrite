import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from hypothesis import settings
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_ch_client, get_current_user, get_extractor, get_renderer
from app.config import get_settings
from app.db import get_db
from app.domain.enums import DataVolume, RequestedLimit, Sector
from app.main import app
from app.models import User
from app.schemas import ExtractedApplication
from tests.fakes import FakeChClient, FakeExtractor, FakeRenderer

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"

# A stand-in operator so the gated routes are reachable without threading a login through
# every request. The auth flow itself is exercised through `anon_api` in test_auth.py.
TEST_USER = User(
    id=uuid.UUID("00000000-0000-4000-8000-0000000000aa"),
    username="tester",
    password_hash="unused",
    display_name="Test Operator",
)

CANNED_EXTRACTION = ExtractedApplication(
    company_name="Example Ltd",
    company_number="00000006",
    sector=Sector.SAAS,
    annual_revenue_gbp=750_000.0,
    years_trading=3.0,
    prior_claims_count=0,
    data_records_held=DataVolume.HUNDRED_K_TO_1M,
    requested_limit_gbp=RequestedLimit.GBP_1M,
    extraction_confidence=0.94,
)


def alembic_config(url: str) -> Config:
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", url)
    return config


# The per-example deadline only ever fires on a loaded CI runner, never on a regression.
settings.register_profile("underwrite", deadline=None, max_examples=200)
settings.load_profile("underwrite")


def pytest_addoption(parser):
    parser.addoption(
        "--regen-goldens",
        action="store_true",
        help="rewrite the rating golden file from the current engine",
    )


class BrokenSession:
    async def execute(self, *args, **kwargs):
        raise ConnectionRefusedError("database unavailable")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_without_db() -> Iterator[TestClient]:
    async def broken_db():
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


def derive_test_database_url() -> str:
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


async def create_test_database_if_missing() -> None:
    url = make_url(get_settings().database_url)
    target = f"{url.database}_test"
    admin = create_async_engine(
        url.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with admin.connect() as connection:
            exists = await connection.scalar(
                text("select 1 from pg_database where datname = :name"), {"name": target}
            )
            if not exists:
                await connection.execute(text(f'create database "{target}"'))
    except (OSError, SQLAlchemyError) as error:
        raise RuntimeError(
            f"could not reach the 'postgres' maintenance database to create {target!r}. "
            f"The suite needs a role that can connect to it and CREATEDB; point DATABASE_URL "
            f"at a local Postgres, or create {target!r} by hand."
        ) from error
    finally:
        await admin.dispose()


@pytest.fixture(scope="session")
async def engine():
    await create_test_database_if_missing()
    test_engine = create_async_engine(derive_test_database_url(), poolclass=NullPool)
    async with test_engine.begin() as connection:
        await connection.execute(text("drop schema public cascade"))
        await connection.execute(text("create schema public"))
    # Migrations, not create_all. env.py calls asyncio.run, so it needs its own thread.
    await asyncio.to_thread(command.upgrade, alembic_config(derive_test_database_url()), "head")
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def db(engine) -> AsyncIterator:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        # Explicit: the default "conditional_savepoint" holds only while its conditions do.
        factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with factory() as session:
            yield session
        # An IntegrityError already unwound this, and a second rollback warns.
        if transaction.is_active:
            await transaction.rollback()


@pytest.fixture
def fake_extractor() -> FakeExtractor:
    return FakeExtractor(result=CANNED_EXTRACTION)


@pytest.fixture
def fake_ch_client() -> FakeChClient:
    return FakeChClient()


@pytest.fixture
def fake_renderer() -> FakeRenderer:
    return FakeRenderer()


def _install_overrides(db, fake_extractor, fake_ch_client, fake_renderer, *, authed: bool) -> None:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_extractor] = lambda: fake_extractor
    app.dependency_overrides[get_ch_client] = lambda: fake_ch_client
    app.dependency_overrides[get_renderer] = lambda: fake_renderer
    if authed:
        app.dependency_overrides[get_current_user] = lambda: TEST_USER


def _clear_overrides() -> None:
    # pop, not clear: clear() would drop an override another fixture installed.
    for dependency in (get_db, get_extractor, get_ch_client, get_renderer, get_current_user):
        app.dependency_overrides.pop(dependency, None)


@pytest.fixture
async def api(db, fake_extractor, fake_ch_client, fake_renderer) -> AsyncIterator[AsyncClient]:
    """In-loop, on the test transaction, and authed as TEST_USER via a dependency override.

    The ASGI transport never runs lifespan, so the pipeline clients are injected here as fakes.
    """
    _install_overrides(db, fake_extractor, fake_ch_client, fake_renderer, authed=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://underwrite.test") as client:
        yield client
    _clear_overrides()


@pytest.fixture
async def anon_api(db, fake_extractor, fake_ch_client, fake_renderer) -> AsyncIterator[AsyncClient]:
    """Like `api` but with no auth override — exercises the real session/login flow and the gate."""
    _install_overrides(db, fake_extractor, fake_ch_client, fake_renderer, authed=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://underwrite.test") as client:
        yield client
    _clear_overrides()
