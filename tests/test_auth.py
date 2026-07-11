import pytest
from fastapi.testclient import TestClient

from app.core import auth as auth_module
from app.core.auth import AuthenticatedUser, get_current_user
from app.main import create_app


def test_me_without_token_returns_401(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_with_garbage_token_returns_401(client, mock_jwks):
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401


def test_me_with_valid_token(client, mock_jwks, make_token):
    token = make_token(email="user@example.org")
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["sub"] == "user-123"
    assert body["email"] == "user@example.org"


def test_me_with_wrong_issuer_returns_401(client, mock_jwks, make_token):
    token = make_token(iss="https://evil.example")
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_with_wrong_audience_returns_401(client, mock_jwks, make_token):
    token = make_token(aud="another-api")
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_with_expired_token_returns_401(client, mock_jwks, make_token):
    token = make_token(exp_delta=-120)  # beyond the 30s leeway
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_with_dependency_override():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        sub="override-sub", email=None, roles=frozenset(), claims={}
    )
    response = TestClient(app).get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["sub"] == "override-sub"


@pytest.mark.parametrize("error", [KeyError("jwks_uri"), ValueError("not json")])
def test_me_returns_503_when_jwks_unavailable(client, monkeypatch, make_token, error):
    async def broken_jwks(token: str):
        raise error

    monkeypatch.setattr(auth_module.jwks_cache, "get_signing_key", broken_jwks)
    response = client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {make_token()}"}
    )
    assert response.status_code == 503


def test_health_stays_public(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
