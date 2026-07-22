from __future__ import annotations

import abc
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends

from app.config import Settings, get_settings


class DocumentStorage(abc.ABC):
    @abc.abstractmethod
    def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None: ...

    @abc.abstractmethod
    def url_for(self, key: str) -> str: ...


class S3Storage(DocumentStorage):
    def __init__(
        self, bucket: str, region: str, expires_in: int = 900, endpoint_url: str | None = None
    ) -> None:
        import boto3
        from botocore.config import Config

        self._bucket = bucket
        self._expires_in = expires_in
        # s3v4: SigV2 presigned URLs omit X-Amz-Expires and are rejected by newer regions.
        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            config=Config(signature_version="s3v4"),
        )

    def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def url_for(self, key: str) -> str:
        # Pure local signing (R3): no API call, no s3:PresignObject, only s3:GetObject at redeem.
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=self._expires_in,
        )


class LocalStorage(DocumentStorage):
    def __init__(self, base_dir: str | Path, base_url: str) -> None:
        self._base = Path(base_dir).resolve()
        self._base_url = base_url.rstrip("/")

    def _resolve(self, key: str) -> Path:
        path = (self._base / key).resolve()
        if not path.is_relative_to(self._base):
            raise ValueError(f"key escapes the storage root: {key!r}")
        return path

    def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def url_for(self, key: str) -> str:
        return f"{self._base_url}/api/documents/{quote(key)}"


def build_storage(settings: Settings) -> DocumentStorage:
    if settings.documents_bucket:
        return S3Storage(
            settings.documents_bucket, settings.aws_region, settings.presign_expiry_seconds
        )
    return LocalStorage(settings.local_documents_dir, settings.quote_base_url)


@lru_cache
def get_storage() -> DocumentStorage:
    return build_storage(get_settings())


StorageDep = Annotated[DocumentStorage, Depends(get_storage)]
