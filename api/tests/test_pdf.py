import pytest

from app.api.deps import get_current_user
from app.config import Settings
from app.main import app
from app.services.pdf import (
    LambdaPdfRenderer,
    LocalPdfRenderer,
    build_renderer,
    data_only_url_fetcher,
)
from app.services.storage import LocalStorage, get_storage
from tests.conftest import TEST_USER

SAMPLE_HTML = '<html><body style="font-family: DejaVu Sans"><h1>Quote</h1><p>body</p></body></html>'


def test_local_renderer_produces_a_valid_pdf_at_the_expected_key(tmp_path):
    storage = LocalStorage(tmp_path, "http://testserver")
    key = LocalPdfRenderer(storage).render_and_store("q-1", SAMPLE_HTML)

    assert key == "generated/q-1.pdf"
    pdf = storage.read(key)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_render_url_fetcher_blocks_network_allows_data():
    fetcher = data_only_url_fetcher()
    with pytest.raises(ValueError):
        fetcher("http://169.254.169.254/latest/meta-data/")
    assert fetcher("data:text/plain;base64,aGk=")


def test_factory_selects_renderer_by_local_pdf(tmp_path):
    storage = LocalStorage(tmp_path, "http://testserver")
    assert isinstance(build_renderer(Settings(local_pdf=True), storage), LocalPdfRenderer)
    assert isinstance(build_renderer(Settings(local_pdf=False), storage), LambdaPdfRenderer)


def test_local_render_round_trips_through_the_documents_route(client, tmp_path):
    storage = LocalStorage(tmp_path, "http://testserver")
    key = LocalPdfRenderer(storage).render_and_store("q-2", SAMPLE_HTML)
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    try:
        response = client.get(f"/api/documents/{key}")
        assert response.status_code == 200
        assert response.content[:4] == b"%PDF"
    finally:
        app.dependency_overrides.pop(get_storage, None)
        app.dependency_overrides.pop(get_current_user, None)
