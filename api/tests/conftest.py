from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from hypothesis import settings

from app.db import get_db
from app.main import app

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
