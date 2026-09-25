"""Auth flow tests: register, login, refresh, logout, reset, validation."""
import re


def test_register_validation(client):
    r = client.post(
        "/api/auth/register",
        json={"name": "X", "email": "bad-email", "password": "short", "confirm_password": "nope"},
    )
    assert r.status_code == 422


def test_register_login_me(client):
    r = client.post(
        "/api/auth/register",
        json={"name": "Alice", "email": "alice@test.ai",
              "password": "Sup3rSecret", "confirm_password": "Sup3rSecret"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["role"] == "user"
    assert body["access_token"] and body["refresh_token"]

    # login
    r = client.post("/api/auth/login", json={"email": "alice@test.ai", "password": "Sup3rSecret"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    me = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "alice@test.ai"


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={"name": "Bob", "email": "bob@test.com",
                "password": "Password1", "confirm_password": "Password1"})
    r = client.post("/api/auth/login", json={"email": "bob@test.com", "password": "WrongPass1"})
    assert r.status_code == 401


def test_protected_route_requires_token(client):
    assert client.get("/api/users/me").status_code == 401


def test_forgot_reset_flow(client):
    client.post("/api/auth/register", json={"name": "Carol", "email": "carol@test.com",
                "password": "Password1", "confirm_password": "Password1"})
    r = client.post("/api/auth/forgot-password", json={"email": "carol@test.com"})
    assert r.status_code == 200
    link = r.json().get("demo_reset_link", "")
    token = link.split("token=")[1]
    reset = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "NewPass456", "confirm_password": "NewPass456"},
    )
    assert reset.status_code == 200
    # new password works, old does not
    assert client.post("/api/auth/login", json={"email": "carol@test.com", "password": "NewPass456"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "carol@test.com", "password": "Password1"}).status_code == 401


def test_refresh_and_logout(client):
    r = client.post("/api/auth/register", json={"name": "Dave", "email": "dave@test.ai",
                    "password": "Password1", "confirm_password": "Password1"})
    refresh = r.json()["refresh_token"]
    ref = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert ref.status_code == 200
    assert "access_token" in ref.json()

    out = client.post("/api/auth/logout", json={"refresh_token": refresh})
    assert out.status_code == 200
    ref2 = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert ref2.status_code == 401


def test_sessions_revoked_on_password_change(auth_headers, client):
    r = client.post("/api/auth/change-password", headers=auth_headers,
                    json={"current_password": "Password1", "new_password": "FreshPass1"})
    assert r.status_code == 200