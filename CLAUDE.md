# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

REST API backend for exploring RCS (Rich Communication Services). Currently just the scaffold: FastAPI + SQLAlchemy 2.0 async + Alembic + PostgreSQL (asyncpg) + OIDC token validation. No models or migrations exist yet (`alembic/versions/` is empty). The README and config comments are in French.

## Commands

Run everything from the repo root: `.env` and `config/` are resolved relative to the CWD.

```bash
pip install -r requirements.txt          # deps (dev + test tools included)
cp .env.example .env                     # set POSTGRES_PASSWORD

uvicorn app.main:app --reload            # dev server, docs at /docs
docker compose up --build                # API + postgres:16, runs `alembic upgrade head` on start

pytest                                   # all tests (no DB, no network)
pytest tests/test_auth.py::test_me_with_valid_token   # single test
ruff check .                             # lint (E, F, I, UP, B; line length 100)
ruff format .

alembic revision --autogenerate -m "..." # or scripts/new_migration.sh "<msg>"
alembic upgrade head                     # or scripts/migrate.sh
scripts/init.sh                          # create the DB if missing, then migrate
scripts/drop.sh                          # drop the DB (asks for confirmation)
```

## Architecture

**App factory.** `app/main.py:create_app()` builds the app, adds CORS only when `CORS_ORIGINS` is non-empty, and mounts every router under `settings.API_V1_PREFIX` (`/api/v1`). The lifespan disposes the engine on shutdown. Tests call `create_app()` for a fresh instance.

**Adding a domain.** Create a package under `app/<domain>/` with `schemas.py`, `service.py`, `router.py`, then `include_router` it in `create_app()`. Put models in `app/models/<name>.py` and import them and list them in `__all__` in `app/models/__init__.py`. `alembic/env.py` imports `app.models`, so a model that isn't registered there won't show up in autogenerate. Models subclass `app.core.database.Base` (plain SQLAlchemy `DeclarativeBase`, not SQLModel). Inject sessions with `Depends(get_db)`.

**Settings (`app/core/config.py`).** Precedence: init > env vars > `.env` > `config/<APP_ENV>.yaml`. `APP_ENV` (default `development`) is read from `os.environ` or by parsing `.env` *before* `Settings` is built, so it can choose which YAML file to load. Public, versioned values (CORS, Postgres host/db, OIDC issuer/audience) go in `config/*.yaml`; secrets go in `.env`. Field names are case-sensitive and uppercase. `DATABASE_URL` is either assembled from `POSTGRES_*` (password URL-encoded) or taken as an override and normalized for asyncpg (`postgres://` becomes `postgresql+asyncpg://`; `sslmode`/`channel_binding` become `ssl=true|false`). In docker compose, `POSTGRES_HOST=db` is forced on the api service.

**Import-time side effects.** `settings = get_settings()` and the async `engine` are created when the module is imported. `OIDC_ISSUER` and `OIDC_AUDIENCE` are required fields, so importing anything from `app.*` fails unless they are set. That is why `tests/conftest.py` sets env vars before any `app` import.

**Auth (`app/core/auth.py`).** The API is an OIDC resource server only: it never issues tokens, and the front end handles login (Auth Code + PKCE). `get_current_user` validates the Bearer token: RS256 signature against the JWKS (discovered from `{OIDC_ISSUER}/.well-known/openid-configuration`), plus `iss`, `aud`, required `exp`/`iat`/`sub`, with 30s leeway. It returns an `AuthenticatedUser(sub, email, roles, claims)`. Errors split into 401 for an invalid or missing token (it uses `HTTPBearer(auto_error=False)` so a missing header gives 401, not 403) and 503 when the IdP or JWKS is unreachable or malformed. `JWKSCache` refetches after a TTL or on an unknown `kid` (rate-limited). All IdP-specific logic is meant to stay in this one file. Roles come from the claim named by `OIDC_ROLES_CLAIM`; nested claims (e.g. Keycloak `realm_access.roles`) require changing `_extract_roles`. `GET /api/v1/me` is the reference protected route; `/api/v1/health` is public.

## Testing

Tests never hit a real IdP or database. Fixtures in `tests/conftest.py`:
- `client`: `TestClient(create_app())`
- `mock_jwks`: monkeypatches `jwks_cache.get_signing_key` to return a session-scoped test RSA public key
- `make_token(iss=, aud=, exp_delta=, **claims)`: signs a valid RS256 token by default; override fields to produce invalid ones

To skip auth entirely, set `app.dependency_overrides[get_current_user]` (see `test_me_with_dependency_override`). There is no DB test fixture yet.

## Notes

- The Docker image (Python 3.12, ruff targets py312) copies only `app/`, `config/`, `alembic/` and `alembic.ini`. `tests/` and `scripts/` are not in the image.
- `.claude/skills/fastapi` and `.claude/skills/sqlmodel` are [library-skills](https://library-skills.io) symlinks into `.venv/lib/python3.14/site-packages/...`. They only resolve once dependencies are installed into `.venv`; repair them with `uvx library-skills --claude --yes` rather than editing them by hand. SQLModel is not a project dependency.
