"""Auth flow tests through the real API app (register -> login -> me)."""


async def test_register_login_me_flow(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "user@test.com", "password": "supersecret1"},
    )
    assert resp.status_code == 201, resp.text

    resp = await client.post(
        "/api/v1/auth/login", json={"email": "user@test.com", "password": "supersecret1"}
    )
    assert resp.status_code == 200
    tokens = resp.json()
    assert tokens["access_token"] and tokens["refresh_token"]

    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "user@test.com"


async def test_login_wrong_password_rejected(client):
    await client.post(
        "/api/v1/auth/register", json={"email": "u2@test.com", "password": "supersecret1"}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "u2@test.com", "password": "wrong-password"}
    )
    assert resp.status_code == 401


async def test_protected_route_requires_token(client):
    resp = await client.get("/api/v1/documents")
    assert resp.status_code == 401


async def test_refresh_token_cannot_be_used_as_access(client):
    await client.post(
        "/api/v1/auth/register", json={"email": "u3@test.com", "password": "supersecret1"}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "u3@test.com", "password": "supersecret1"}
    )
    refresh = resp.json()["refresh_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert resp.status_code == 401
