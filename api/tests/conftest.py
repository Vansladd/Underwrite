from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from hypothesis import settings
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import Base

# The rating properties call a pure function a few thousand times; the per-example
# deadline only ever fires on a loaded CI runner, never on a real regression.
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
    app.dependency_overrides.clear()


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
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def db(engine) -> AsyncIterator:
    """A session on a transaction that is always rolled back, so tests never see each other."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        # Explicit because the default is "conditional_savepoint" — it does the right thing
        # here, but only while the conditions hold. Pinning it keeps a test that commits
        # (any test exercising a real route) from committing this transaction and leaking
        # its rows into every test after it.
        factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with factory() as session:
            yield session
        # A test that provoked an IntegrityError has already had the session unwind this
        # transaction; rolling it back again warns, and warnings are errors here.
        if transaction.is_active:
            await transaction.rollback()
