import pytest
from httpx import BasicAuth

from app.api.deps import OPS_USERNAME, require_ops
from app.config import DEFAULT_OPS_PASSWORD
from app.main import app
from tests.factories import make_submission

# Everything not listed here must carry require_ops. A new route fails until it is classified.
PUBLIC = {
    ("GET", "/health"),
    ("POST", "/api/submissions"),
    ("GET", "/api/submissions/{submission_id}"),
    ("GET", "/api/openapi.json"),
    ("GET", "/api/docs"),
    ("GET", "/api/docs/oauth2-redirect"),
    ("GET", "/api/redoc"),
}


def walk(routes):
    # FastAPI 0.139 keeps an _IncludedRouter, so app.routes alone sees no mounted route.
    for route in routes:
        nested = getattr(route, "routes", None)
        if nested is None:
            included = getattr(route, "original_router", None)
            nested = getattr(included, "routes", None)
        if nested is None:
            yield route
        else:
            yield from walk(nested)


def routes():
    for route in walk(app.routes):
        for method in getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}:
            yield method, route.path, route


def test_every_route_is_deliberately_public_or_gated():
    ungated = {
        (method, path)
        for method, path, route in routes()
        if (method, path) not in PUBLIC
        and not any(d.call is require_ops for d in route.dependant.dependencies)
    }

    assert not ungated, f"classify these in PUBLIC or gate them: {sorted(ungated)}"


def test_the_public_list_has_no_stale_entries():
    live = {(method, path) for method, path, _ in routes()}

    assert live >= PUBLIC, f"PUBLIC names routes that no longer exist: {sorted(PUBLIC - live)}"


async def test_the_queue_is_closed_without_credentials(api):
    response = await api.get("/api/submissions")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


async def test_the_queue_opens_with_the_right_credentials(api, db, ops_auth):
    await make_submission(db)

    response = await api.get("/api/submissions", auth=ops_auth)

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.parametrize(
    ("username", "password"),
    [
        (OPS_USERNAME, "wrong"),
        ("someone", DEFAULT_OPS_PASSWORD),
        ("someone", "wrong"),
        (OPS_USERNAME, ""),
        ("", DEFAULT_OPS_PASSWORD),
    ],
)
async def test_both_halves_of_the_credential_are_checked(api, username, password):
    response = await api.get("/api/submissions", auth=BasicAuth(username, password))

    assert response.status_code == 401


async def test_a_non_ascii_password_is_rejected_not_a_server_error(api):
    # compare_digest raises TypeError on non-ASCII str, which would surface as a 500.
    response = await api.get("/api/submissions", auth=BasicAuth(OPS_USERNAME, "pässwörd"))

    assert response.status_code == 401


async def test_an_applicant_still_reads_their_own_submission(api, db):
    submission = await make_submission(db)

    response = await api.get(f"/api/submissions/{submission.id}")

    # The UUID is the capability: applicants have no account until #31b. See DECISIONS D-012.
    assert response.status_code == 200


async def test_an_applicant_still_submits_without_credentials(api):
    response = await api.post(
        "/api/submissions", json={"input_mode": "paste", "raw_input": "quote us"}
    )

    assert response.status_code == 201


async def test_health_stays_open_for_the_container_probe(api):
    assert (await api.get("/health")).status_code == 200
