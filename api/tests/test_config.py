import pytest
from alembic.config import Config
from pydantic import ValidationError

from app.config import (
    DEFAULT_OPERATOR_PASSWORD,
    DEFAULT_SECRET_KEY,
    DEFAULT_SWEEPER_TOKEN,
    Settings,
    alembic_url,
    startup_warnings,
)


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
    # The field defaults, not Settings() — which reads a real key from .env when one is present.
    assert Settings.model_fields["anthropic_api_key"].default == ""
    assert Settings.model_fields["companies_house_api_key"].default == ""


# --- startup warnings: a shipped default must not survive onto a TLS deployment ---


def secure(**overrides) -> Settings:
    hardened = {
        "session_secure": True,
        "secret_key": "a-real-secret",
        "seed_operator_password": "a-real-password",
        "sweeper_token": "a-real-token",
        "companies_house_api_key": "a-real-key",
    }
    return Settings(**(hardened | overrides))


def test_a_hardened_prod_config_warns_about_nothing():
    assert startup_warnings(secure()) == []


def test_the_default_sweeper_token_warns_on_a_secure_deployment():
    (warning,) = startup_warnings(secure(sweeper_token=DEFAULT_SWEEPER_TOKEN))

    assert "SWEEPER_TOKEN" in warning


def test_the_default_sweeper_token_is_fine_locally():
    # http://localhost is the shipped default's whole purpose; only a TLS box is a mistake.
    assert startup_warnings(secure(session_secure=False, sweeper_token=DEFAULT_SWEEPER_TOKEN)) == []


def test_an_unset_sweeper_token_does_not_warn():
    # Empty is the closed state — /api/internal 503s. Nothing to warn about.
    assert startup_warnings(secure(sweeper_token="")) == []


def test_the_other_shipped_defaults_still_warn():
    warnings = startup_warnings(
        secure(
            secret_key=DEFAULT_SECRET_KEY,
            seed_operator_password=DEFAULT_OPERATOR_PASSWORD,
            companies_house_api_key="",
        )
    )

    assert len(warnings) == 3


def test_a_percent_escaped_password_survives_alembic_config():
    """A strong password with `@` must be URL-escaped, and %40 then collides with configparser
    interpolation — so the migration fails where the connection would have worked."""
    settings = Settings(database_url="postgresql+asyncpg://underwrite:p%40ss@db:5432/underwrite")
    config = Config()

    config.set_main_option("sqlalchemy.url", alembic_url(settings))

    assert config.get_main_option("sqlalchemy.url") == settings.database_url


def test_rejects_a_dsn_whose_password_carries_an_unescaped_at():
    # The exact URL that broke the UW-063 deploy: it parses, connects to the wrong host, and
    # surfaces as a DNS error inside a container rather than a config error at startup.
    with pytest.raises(ValidationError, match="unescaped"):
        Settings(database_url="postgresql+asyncpg://underwrite:LILAC@12EAFC@db:5432/underwrite")


def test_accepts_a_dsn_whose_password_is_properly_escaped():
    dsn = "postgresql+asyncpg://underwrite:LILAC%4012EAFC@db:5432/underwrite"

    assert Settings(database_url=dsn).database_url == dsn
