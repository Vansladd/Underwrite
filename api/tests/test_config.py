import pytest
from pydantic import ValidationError

from app.config import Settings


def test_accepts_asyncpg_dsn():
    settings = Settings(database_url="postgresql+asyncpg://u:p@db:5432/underwrite")

    assert settings.database_url.startswith("postgresql+asyncpg://")


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://u:p@db:5432/underwrite",
        "postgresql+psycopg://u:p@db:5432/underwrite",
        "sqlite+aiosqlite:///./test.db",
    ],
)
def test_rejects_non_asyncpg_dsn(dsn):
    with pytest.raises(ValidationError, match="asyncpg"):
        Settings(database_url=dsn)


def test_external_api_keys_default_to_empty():
    settings = Settings()

    assert settings.anthropic_api_key == ""
    assert settings.companies_house_api_key == ""
