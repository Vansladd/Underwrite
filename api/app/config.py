from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ASYNC_DRIVER_PREFIX = "postgresql+asyncpg://"
DEFAULT_SECRET_KEY = "dev-insecure-change-me"
DEFAULT_OPERATOR_PASSWORD = "underwrite-demo"
DEFAULT_SWEEPER_TOKEN = "local-sweeper-token"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = f"{ASYNC_DRIVER_PREFIX}underwrite:underwrite@db:5432/underwrite"

    anthropic_api_key: str = ""
    companies_house_api_key: str = ""

    # Sonnet 5, not Opus: extraction is schema-constrained and high-volume. See D-021.
    extraction_model: str = "claude-sonnet-5"
    extraction_max_tokens: int = 4096

    companies_house_base_url: str = "https://api.company-information.service.gov.uk"

    # Signs the session cookie (itsdangerous). Rotating it revokes every live session.
    secret_key: str = DEFAULT_SECRET_KEY
    # Secure cookie: off for http://localhost dev, on (=1) behind TLS in prod.
    session_secure: bool = False

    # The seeded operator. Local default is public; prod .env sets a strong secret. See D-026.
    seed_operator_username: str = "demo"
    seed_operator_password: str = DEFAULT_OPERATOR_PASSWORD

    # Shared with the expiry-sweeper Lambda; empty disables /api/internal entirely. See D-031.
    sweeper_token: str = ""

    quote_base_url: str = "http://localhost:8000"
    local_pdf: bool = True

    # Empty bucket selects LocalStorage; a name selects S3Storage. See UW-050.
    documents_bucket: str = ""
    aws_region: str = "eu-west-2"
    local_documents_dir: str = "var/documents"
    presign_expiry_seconds: int = 900
    pdf_lambda_function: str = "underwrite-pdf-render"

    @field_validator("database_url")
    @classmethod
    def require_async_driver(cls, value: str) -> str:
        if not value.startswith(ASYNC_DRIVER_PREFIX):
            raise ValueError(
                f"DATABASE_URL must use the asyncpg driver ({ASYNC_DRIVER_PREFIX}...); "
                f"a sync DSN fails later at query time rather than here. Got: {value!r}"
            )
        return value

    @field_validator("database_url")
    @classmethod
    def reject_an_unescaped_password(cls, value: str) -> str:
        # A second @ in the authority means the password carries an unescaped one. The URL still
        # parses, so the failure surfaces as a DNS error five frames into asyncpg, in a container.
        authority = value.split("://", 1)[-1].split("/", 1)[0]
        if authority.count("@") > 1:
            raise ValueError(
                "DATABASE_URL has more than one '@' before the host, so the password contains an "
                "unescaped one and the host is not what you think. Percent-encode it (@ = %40)."
            )
        return value


def alembic_url(settings: Settings) -> str:
    """Alembic keeps this in a configparser, where a lone `%` is interpolation syntax — so a
    password carrying a percent-escape (%40 for @) fails the migration, not the connection."""
    return settings.database_url.replace("%", "%%")


def startup_warnings(settings: Settings) -> list[str]:
    """Every shipped default that must not survive onto a TLS deployment, plus a missing CH key."""
    warnings = []
    if settings.secret_key == DEFAULT_SECRET_KEY:
        warnings.append(
            "SECRET_KEY is the shipped default; sessions are forgeable — set it in prod"
        )
    if settings.session_secure and settings.seed_operator_password == DEFAULT_OPERATOR_PASSWORD:
        warnings.append(
            "SEED_OPERATOR_PASSWORD is still the public default on a secure (prod) deployment — "
            "set a strong secret before exposing the URL"
        )
    if settings.session_secure and settings.sweeper_token == DEFAULT_SWEEPER_TOKEN:
        warnings.append(
            "SWEEPER_TOKEN is the shipped default from .env.example on a secure (prod) deployment "
            "— anyone who can read the repo can expire every live quote. Set a strong secret"
        )
    if not settings.companies_house_api_key:
        # Not fatal: `make demo` and `make seed` run the pipeline with canned providers (D-024).
        warnings.append(
            "COMPANIES_HOUSE_API_KEY is unset — every lookup will fail and every submission will "
            "refer with CH_UNAVAILABLE. Set it, or ignore this if you are running the canned demo"
        )
    return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]
