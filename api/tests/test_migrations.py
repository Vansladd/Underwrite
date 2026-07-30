"""Synchronous by design: env.py calls asyncio.run, which raises inside a running loop."""

import asyncio
import contextlib
import importlib.util
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from tests.conftest import alembic_config, derive_test_database_url

# One database per run, so nothing can be connected to it when we drop it. A single fixed name is
# what made this module flaky: any leftover session — a Ctrl-C'd run, an overlapping `make test`,
# a stray psql — failed the drop with ObjectInUse and took all four tests down. See D-035.
SCRATCH_PREFIX = "underwrite_migrations_test"
HEAD = "0005"

TABLES = "select table_name from information_schema.tables where table_schema = 'public'"
TRIGGERS = """
select t.tgname from pg_trigger t
join pg_class c on c.oid = t.tgrelid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and not t.tgisinternal
"""
FUNCTIONS = "select proname from pg_proc where proname = 'refuse_audit_mutation'"
ENUM_TYPES = """
select t.typname from pg_type t
join pg_namespace n on n.oid = t.typnamespace
where n.nspname = 'public' and t.typtype = 'e'
"""


def scratch_name() -> str:
    return f"{SCRATCH_PREFIX}_{uuid4().hex[:12]}"


DATABASE = scratch_name()


def url_for(database: str) -> str:
    return (
        make_url(derive_test_database_url())
        .set(database=database)
        .render_as_string(hide_password=False)
    )


def names(url: str, query: str) -> set[str]:
    async def run() -> set[str]:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return {row[0] for row in await connection.execute(text(query))}
        finally:
            await engine.dispose()

    return asyncio.run(run())


def scratch_only(name: str) -> str:
    """Never drop a database this module did not create — everything else is somebody's data."""
    if not name.startswith(f"{SCRATCH_PREFIX}_"):
        raise RuntimeError(f"refusing to drop {name!r}, which is not a scratch database")
    return name


def admin(*statements: str) -> None:
    async def run() -> None:
        engine = create_async_engine(
            url_for("postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
        )
        try:
            async with engine.connect() as connection:
                for statement in statements:
                    await connection.execute(text(statement))
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.fixture(scope="module")
def scratch() -> str:
    # Deliberately no sweep of older scratch databases: nothing here holds a connection between
    # tests, so "has no sessions" cannot tell an abandoned one from a live run's. `make clean`
    # drops the volume, which is what collects them. See D-035.
    admin(f'create database "{scratch_only(DATABASE)}"')
    yield url_for(DATABASE)
    # Plain drop, never `with (force)`: force SIGTERMs the other backend, and one that exits
    # uncleanly takes the whole postmaster into crash recovery with it. See D-035.
    admin(f'drop database if exists "{scratch_only(DATABASE)}"')


@pytest.fixture
def config(scratch):
    config = alembic_config(scratch)
    yield config
    # Rewound rather than recreated: create database copies template1 and is slow.
    command.downgrade(config, "base")


def test_upgrade_builds_the_whole_schema_from_empty(config, scratch):
    command.upgrade(config, "head")

    assert names(scratch, TABLES) == {
        "alembic_version",
        "submissions",
        "extractions",
        "enrichments",
        "ratings",
        "quotes",
        "audit_events",
        "users",
    }
    assert names(scratch, TRIGGERS) == {"audit_events_append_only", "audit_events_no_truncate"}
    assert names(scratch, FUNCTIONS) == {"refuse_audit_mutation"}
    assert names(scratch, ENUM_TYPES) == {
        "audit_actor",
        "audit_event_type",
        "company_status",
        "data_volume",
        "decision",
        "input_mode",
        "quote_status",
        "requested_limit",
        "sector",
        "submission_status",
    }


def test_downgrade_leaves_no_tables_and_no_enum_types(config, scratch):
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    # DROP TABLE leaves enum types behind, so this is the assertion that matters.
    assert names(scratch, TABLES) == {"alembic_version"}
    assert names(scratch, ENUM_TYPES) == set()
    # The function is schema-level and outlives its table, so it needs its own DROP.
    assert names(scratch, FUNCTIONS) == set()
    assert names(scratch, TRIGGERS) == set()


def test_upgrade_downgrade_upgrade_round_trips(config, scratch):
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    assert "submissions" in names(scratch, TABLES)
    assert names(scratch, "select version_num from alembic_version") == {HEAD}


def test_migrations_match_the_models(config):
    command.upgrade(config, "head")

    # Raises AutogenerateDiffsDetected naming the column if a model changed without one.
    command.check(config)


def test_a_squatted_leftover_does_not_block_a_new_run():
    """The original flake, as a whole run: a session on a leftover failed the drop for everyone.

    Its own name, not a fixed one — a shared `_occupied_probe` would collide between concurrent
    runs and recreate exactly the ObjectInUse this exists to rule out.
    """
    squatted = scratch_name()
    admin(f'create database "{scratch_only(squatted)}"')

    # Its own loop, left open: asyncio.run would close the loop and take the connection with it.
    loop = asyncio.new_event_loop()
    engine = create_async_engine(url_for(squatted), poolclass=NullPool)
    connection = loop.run_until_complete(engine.connect())
    try:
        # A whole run's setup and teardown, while the squatter holds its session throughout.
        fresh = scratch_name()
        admin(f'create database "{scratch_only(fresh)}"')
        admin(f'drop database if exists "{scratch_only(fresh)}"')
    finally:
        for shutdown in (connection.close(), engine.dispose()):
            with contextlib.suppress(Exception):
                loop.run_until_complete(shutdown)
        loop.close()
        admin(f'drop database if exists "{scratch_only(squatted)}"')


def test_each_run_picks_a_scratch_database_no_other_run_will_pick():
    """The fix itself. A shared name is what let one run's leftover session break the next one.

    Re-executing this module is what a second concurrent run does; the two must not collide.
    Nothing at module scope touches the database, so loading it again is free.
    """
    spec = importlib.util.spec_from_file_location("_probe_migrations", __file__)
    other = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(other)

    assert other.DATABASE != DATABASE
    assert other.DATABASE.startswith(f"{SCRATCH_PREFIX}_")


def test_it_refuses_to_drop_anything_that_is_not_a_scratch_database():
    for real in (
        make_url(get_settings().database_url).database,
        make_url(derive_test_database_url()).database,
        "postgres",
        SCRATCH_PREFIX,  # the old fixed name, which is a prefix and not one of ours
    ):
        with pytest.raises(RuntimeError, match="not a scratch database"):
            scratch_only(real)
