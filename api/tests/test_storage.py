import boto3
import httpx
import pytest
from moto.server import ThreadedMotoServer

from app.api.deps import get_current_user
from app.config import Settings
from app.main import app
from app.services.storage import LocalStorage, S3Storage, build_storage, get_storage
from tests.conftest import TEST_USER


def test_local_storage_round_trips(tmp_path):
    storage = LocalStorage(tmp_path, "http://localhost:8000")
    storage.put("generated/q.pdf", b"%PDF-1.7 hello")
    assert storage.read("generated/q.pdf") == b"%PDF-1.7 hello"


def test_local_storage_url_points_at_the_documents_route(tmp_path):
    storage = LocalStorage(tmp_path, "http://localhost:8000/")
    assert storage.url_for("generated/q.pdf") == (
        "http://localhost:8000/api/documents/generated/q.pdf"
    )


@pytest.mark.parametrize("key", ["../escape.pdf", "generated/../../etc/passwd"])
def test_local_storage_rejects_path_traversal(tmp_path, key):
    storage = LocalStorage(tmp_path, "http://localhost:8000")
    with pytest.raises(ValueError):
        storage.put(key, b"x")


def test_factory_selects_backend_by_bucket(tmp_path):
    assert isinstance(
        build_storage(Settings(documents_bucket="", local_documents_dir=str(tmp_path))),
        LocalStorage,
    )
    assert isinstance(build_storage(Settings(documents_bucket="a-bucket")), S3Storage)


def test_documents_route_round_trips_a_local_file(client, tmp_path):
    storage = LocalStorage(tmp_path, "http://testserver")
    storage.put("generated/q.pdf", b"%PDF-1.7 body")
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    try:
        response = client.get("/api/documents/generated/q.pdf")
        assert response.status_code == 200
        assert response.content == b"%PDF-1.7 body"
        assert response.headers["content-type"] == "application/pdf"
        assert client.get("/api/documents/does-not-exist.pdf").status_code == 404
    finally:
        app.dependency_overrides.pop(get_storage, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def moto_s3(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    server = ThreadedMotoServer(port=0)
    server.start()
    host, port = server.get_host_and_port()
    endpoint = f"http://{host}:{port}"
    boto3.client("s3", region_name="us-east-1", endpoint_url=endpoint).create_bucket(Bucket="docs")
    yield endpoint
    server.stop()


def test_s3_storage_stored_key_round_trips_to_a_working_url(moto_s3):
    storage = S3Storage("docs", "us-east-1", expires_in=900, endpoint_url=moto_s3)
    storage.put("generated/q.pdf", b"%PDF-1.7 s3")

    url = storage.url_for("generated/q.pdf")
    assert "X-Amz-Expires=900" in url

    response = httpx.get(url)
    assert response.status_code == 200
    assert response.content == b"%PDF-1.7 s3"
