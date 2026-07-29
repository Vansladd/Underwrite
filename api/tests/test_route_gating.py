from app.api.deps import get_current_user, require_sweeper_token
from app.main import app
from tests.factories import make_submission

# Everything not listed here must carry a gate. A new route fails until it is classified.
PUBLIC = {
    ("GET", "/health"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/openapi.json"),
    ("GET", "/api/docs"),
    ("GET", "/api/docs/oauth2-redirect"),
    ("GET", "/api/redoc"),
}

# Machine callers: no session, no human, a shared token instead. See DECISIONS D-031.
GATES = (get_current_user, require_sweeper_token)


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


def gates_on(route):
    # The docs routes are plain Starlette Routes and carry no dependant at all.
    dependant = getattr(route, "dependant", None)
    return [] if dependant is None else [d.call for d in dependant.dependencies]


def test_every_route_is_deliberately_public_or_gated():
    ungated = {
        (method, path)
        for method, path, route in routes()
        if (method, path) not in PUBLIC and not any(call in GATES for call in gates_on(route))
    }

    assert not ungated, f"classify these in PUBLIC or gate them: {sorted(ungated)}"


def test_the_machine_gate_stays_confined_to_the_internal_prefix():
    # A token is not a session: an operator route must never be reachable with a shared secret.
    misgated = {
        (method, path)
        for method, path, route in routes()
        if not path.startswith("/api/internal") and require_sweeper_token in gates_on(route)
    }

    assert not misgated, f"these carry the sweeper token outside /api/internal: {sorted(misgated)}"


def test_the_public_list_has_no_stale_entries():
    live = {(method, path) for method, path, _ in routes()}

    assert live >= PUBLIC, f"PUBLIC names routes that no longer exist: {sorted(PUBLIC - live)}"


# --- the money paths are closed to the unauthenticated (UW-019 cost boundary) ---


async def test_creating_a_submission_requires_auth(anon_api):
    # The exposure worth closing: an unauthenticated POST burning Anthropic credit.
    response = await anon_api.post(
        "/api/submissions", json={"input_mode": "paste", "raw_input": "quote us"}
    )

    assert response.status_code == 401


async def test_uploading_a_pdf_requires_auth(anon_api):
    files = {"file": ("submission.pdf", b"%PDF-1.7", "application/pdf")}

    assert (await anon_api.post("/api/submissions/pdf", files=files)).status_code == 401


async def test_the_queue_requires_auth(anon_api):
    assert (await anon_api.get("/api/submissions")).status_code == 401


async def test_reading_a_submission_requires_auth(anon_api, db):
    submission = await make_submission(db)

    assert (await anon_api.get(f"/api/submissions/{submission.id}")).status_code == 401


async def test_a_document_requires_auth(anon_api):
    assert (await anon_api.get("/api/documents/whatever.pdf")).status_code == 401


async def test_an_authenticated_operator_reaches_the_queue(api, db):
    await make_submission(db)

    response = await api.get("/api/submissions")

    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_health_stays_open_for_the_container_probe(anon_api):
    assert (await anon_api.get("/health")).status_code == 200
