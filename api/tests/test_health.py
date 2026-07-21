def test_health_reports_ok_when_database_reachable(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_degraded_when_database_unreachable(client_without_db):
    response = client_without_db.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "error"}
