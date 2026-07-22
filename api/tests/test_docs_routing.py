import pytest


@pytest.mark.parametrize("path", ["/api/docs", "/api/redoc", "/api/openapi.json"])
def test_docs_served_under_api_prefix(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_not_served_at_root(client, path):
    assert client.get(path).status_code == 404
