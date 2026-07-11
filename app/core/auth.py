"""OIDC JWT validation (resource-server side).

The OIDC flow happens entirely in the front-end client; the API only receives
a Bearer access token and validates it (signature via JWKS, issuer, audience,
expiration). Everything IdP-specific lives in this module so that switching
providers only touches this file.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

# auto_error=False: a missing header must yield a 401 (not FastAPI's 403).
bearer_scheme = HTTPBearer(auto_error=False, bearerFormat="JWT")


@dataclass(frozen=True)
class AuthenticatedUser:
    sub: str
    email: str | None
    roles: frozenset[str]
    claims: dict[str, Any]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


class JWKSCache:
    """Fetches and caches the issuer's signing keys without blocking the loop.

    The JWKS URL is resolved once via OIDC discovery on the issuer. Keys are
    refreshed after `ttl` or when an unknown `kid` shows up (rotation), the
    latter rate-limited so a flood of forged tokens cannot hammer the IdP.
    """

    def __init__(self, ttl_seconds: int = 3600, rotation_min_age_seconds: int = 60) -> None:
        self._ttl = ttl_seconds
        self._rotation_min_age = rotation_min_age_seconds
        self._jwks_url: str | None = None
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get_signing_key(self, token: str) -> jwt.PyJWK:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.InvalidTokenError as exc:
            raise _unauthorized("Invalid token") from exc
        if not kid:
            raise _unauthorized("Invalid token")

        if not self._keys or time.monotonic() - self._fetched_at > self._ttl:
            await self._refresh(min_age=0)
        key = self._keys.get(kid)
        if key is None:
            await self._refresh(min_age=self._rotation_min_age)
            key = self._keys.get(kid)
        if key is None:
            raise _unauthorized("Unknown signing key")
        return key

    async def _refresh(self, min_age: int) -> None:
        async with self._lock:
            if self._keys and time.monotonic() - self._fetched_at < min_age:
                return  # refreshed by a concurrent request, or rotation rate-limited
            async with httpx.AsyncClient(timeout=10) as client:
                if self._jwks_url is None:
                    discovery = settings.OIDC_ISSUER.rstrip("/") + (
                        "/.well-known/openid-configuration"
                    )
                    resp = await client.get(discovery)
                    resp.raise_for_status()
                    self._jwks_url = resp.json()["jwks_uri"]
                resp = await client.get(self._jwks_url)
                resp.raise_for_status()
                jwks = resp.json().get("keys", [])
            keys: dict[str, jwt.PyJWK] = {}
            for data in jwks:
                try:
                    key = jwt.PyJWK(data)
                except jwt.exceptions.PyJWTError:
                    continue  # one bad entry must not take down the whole key set
                if key.key_id:
                    keys[key.key_id] = key
            self._keys = keys
            self._fetched_at = time.monotonic()


jwks_cache = JWKSCache()


def _extract_roles(claims: dict[str, Any]) -> frozenset[str]:
    """Read the application roles from the provider-specific claim.

    The claim name is configured via ``OIDC_ROLES_CLAIM``. Its value may be a
    list of role names or a mapping keyed by role (e.g. Zitadel's project-roles
    claim); both shapes reduce to the set of role keys.
    """
    return frozenset(claims.get(settings.OIDC_ROLES_CLAIM) or {})


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """FastAPI dependency guarding protected routes."""
    if credentials is None:
        raise _unauthorized("Not authenticated")
    token = credentials.credentials
    try:
        key = await jwks_cache.get_signing_key(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=settings.OIDC_AUDIENCE,
            issuer=settings.OIDC_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
            leeway=30,  # tolerance for clock drift
        )
    except jwt.InvalidTokenError as exc:
        # Never log or echo the token itself.
        raise _unauthorized("Invalid token") from exc
    except (httpx.HTTPError, KeyError, ValueError, jwt.exceptions.PyJWTError) as exc:
        # Network failure, or a malformed discovery/JWKS document (non-JSON
        # body, missing jwks_uri, unparsable keys): the IdP is unusable.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    return AuthenticatedUser(
        sub=claims["sub"],
        email=claims.get("email"),
        roles=_extract_roles(claims),
        claims=claims,
    )
