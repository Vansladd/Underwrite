from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ASYNC_DRIVER_PREFIX = "postgresql+asyncpg://"
DEFAULT_OPS_PASSWORD = "changeme"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = f"{ASYNC_DRIVER_PREFIX}underwrite:underwrite@db:5432/underwrite"

    anthropic_api_key: str = ""
    companies_house_api_key: str = ""

    ops_password: str = DEFAULT_OPS_PASSWORD
    quote_base_url: str = "http://localhost:8000"
    local_pdf: bool = True

    # Empty bucket selects LocalStorage; a name selects S3Storage. See UW-050.
    documents_bucket: str = ""
    aws_region: str = "eu-west-2"
    local_documents_dir: str = "var/documents"
    presign_expiry_seconds: int = 900

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
