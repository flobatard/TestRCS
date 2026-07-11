import os

# Settings has required fields evaluated at import time — set test values
# before anything imports app.*
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("OIDC_ISSUER", "https://issuer.test")
os.environ.setdefault("OIDC_AUDIENCE", "test-api")

import json  # noqa: E402
import time  # noqa: E402
from typing import Any  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core import auth as auth_module  # noqa: E402
from app.main import create_app  # noqa: E402

TEST_KID = "test-key"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(scope="session")
def rsa_private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def public_jwk(rsa_private_key: rsa.RSAPrivateKey) -> jwt.PyJWK:
    data = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(rsa_private_key.public_key()))
    data.update({"kid": TEST_KID, "alg": "RS256", "use": "sig"})
    return jwt.PyJWK(data)


@pytest.fixture
def mock_jwks(monkeypatch: pytest.MonkeyPatch, public_jwk: jwt.PyJWK) -> None:
    """Bypass the network: the JWKS cache always returns the test public key."""

    async def get_signing_key(token: str) -> jwt.PyJWK:
        return public_jwk

    monkeypatch.setattr(auth_module.jwks_cache, "get_signing_key", get_signing_key)


@pytest.fixture
def make_token(rsa_private_key: rsa.RSAPrivateKey):
    """Sign RS256 tokens with the test key; iss/aud/exp default to valid values."""

    def _make(
        *,
        iss: str | None = None,
        aud: str | None = None,
        exp_delta: int = 300,
        **extra: Any,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": iss if iss is not None else os.environ["OIDC_ISSUER"],
            "aud": aud if aud is not None else os.environ["OIDC_AUDIENCE"],
            "sub": "user-123",
            "iat": now,
            "exp": now + exp_delta,
            **extra,
        }
        return jwt.encode(
            claims, rsa_private_key, algorithm="RS256", headers={"kid": TEST_KID}
        )

    return _make
