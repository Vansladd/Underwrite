from app.models import User
from app.services.auth import hash_password, verify_password


def test_a_malformed_stored_hash_fails_closed_rather_than_raising():
    # A corrupt / non-argon2 hash must read as "not authenticated", never a 500.
    assert verify_password("not-an-argon2-hash", "whatever") is False


async def make_operator(db, username="jane", password="s3cret-pw", display="Jane Underwriter"):
    user = User(username=username, password_hash=hash_password(password), display_name=display)
    db.add(user)
    await db.flush()
    return user


async def test_login_starts_a_session_and_me_returns_the_operator(anon_api, db):
    await make_operator(db, "jane", "s3cret-pw", "Jane Underwriter")

    login = await anon_api.post(
        "/api/auth/login", json={"username": "jane", "password": "s3cret-pw"}
    )

    assert login.status_code == 200
    assert login.json()["display_name"] == "Jane Underwriter"

    me = await anon_api.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "jane"


async def test_a_wrong_password_is_rejected(anon_api, db):
    await make_operator(db, "jane", "s3cret-pw")

    response = await anon_api.post("/api/auth/login", json={"username": "jane", "password": "nope"})

    assert response.status_code == 401
    assert (await anon_api.get("/api/auth/me")).status_code == 401


async def test_an_unknown_user_is_rejected(anon_api):
    response = await anon_api.post(
        "/api/auth/login", json={"username": "ghost", "password": "whatever"}
    )

    assert response.status_code == 401


async def test_logout_clears_the_session(anon_api, db):
    await make_operator(db, "jane", "s3cret-pw")
    await anon_api.post("/api/auth/login", json={"username": "jane", "password": "s3cret-pw"})
    assert (await anon_api.get("/api/auth/me")).status_code == 200

    logout = await anon_api.post("/api/auth/logout")

    assert logout.status_code == 204
    assert (await anon_api.get("/api/auth/me")).status_code == 401


async def test_me_requires_a_session(anon_api):
    assert (await anon_api.get("/api/auth/me")).status_code == 401
