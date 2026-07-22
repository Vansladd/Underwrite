from __future__ import annotations

import abc
import json

from app.config import Settings
from app.services.storage import DocumentStorage


def data_only_url_fetcher():
    # data: only, so injected quote HTML can't SSRF or read local files. Byte-identical to the
    # Lambda handler's (separate deployment units can't share code). See D-020.
    from weasyprint.urls import URLFetcher

    return URLFetcher(allowed_protocols=["data"])


class PdfRenderer(abc.ABC):
    @abc.abstractmethod
    def render_and_store(self, quote_id: str, html: str) -> str: ...


class LocalPdfRenderer(PdfRenderer):
    def __init__(self, storage: DocumentStorage) -> None:
        self._storage = storage

    def render_and_store(self, quote_id: str, html: str) -> str:
        import weasyprint

        pdf = weasyprint.HTML(string=html, url_fetcher=data_only_url_fetcher()).write_pdf()
        key = f"generated/{quote_id}.pdf"
        self._storage.put(key, pdf, "application/pdf")
        return key


class LambdaPdfRenderer(PdfRenderer):
    def __init__(self, function_name: str, region: str) -> None:
        import boto3

        self._function_name = function_name
        self._client = boto3.client("lambda", region_name=region)

    def render_and_store(self, quote_id: str, html: str) -> str:
        response = self._client.invoke(
            FunctionName=self._function_name,
            Payload=json.dumps({"quote_id": quote_id, "html": html}).encode(),
        )
        payload = json.load(response["Payload"])
        if response.get("FunctionError"):
            raise RuntimeError(f"pdf render lambda failed: {payload}")
        return payload["s3_key"]


def build_renderer(settings: Settings, storage: DocumentStorage) -> PdfRenderer:
    if settings.local_pdf:
        return LocalPdfRenderer(storage)
    return LambdaPdfRenderer(settings.pdf_lambda_function, settings.aws_region)
