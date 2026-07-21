from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app


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
