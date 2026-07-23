from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ASYNC_DRIVER_PREFIX = "postgresql+asyncpg://"
DEFAULT_SECRET_KEY = "dev-insecure-change-me"
DEFAULT_OPERATOR_PASSWORD = "underwrite-demo"


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


@lru_cache
def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]
