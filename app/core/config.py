import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

from pydantic import model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# Dossier des configs publiques par environnement (versionnées dans le repo).
_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def _resolve_app_env() -> str:
    """Détermine l'environnement avant l'instanciation des Settings.

    Priorité à la variable d'environnement (CI/CD, docker compose), puis au .env,
    sinon "development" par défaut.
    """
    env = os.environ.get("APP_ENV")
    if env:
        return env
    dotenv = Path(".env")
    if dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("APP_ENV=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip("\"'") or "development"
    return "development"


def _normalize_async_url(url: str) -> str:
    """Force le driver asyncpg et traduit les options libpq qu'il ne comprend pas.

    asyncpg ignore `sslmode` et `channel_binding` (options de libpq) : on les
    convertit en `ssl=true/false`, ce qui permet de coller telle quelle l'URL
    fournie par un Postgres managé (Neon, etc.).
    """
    scheme, _, rest = url.partition("://")
    if scheme in ("postgres", "postgresql"):
        url = f"postgresql+asyncpg://{rest}"

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if sslmode == "disable":
        query.setdefault("ssl", "false")
    elif sslmode:
        query.setdefault("ssl", "true")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class Settings(BaseSettings):
    """Application settings.

    Ordre de priorité décroissant : init > variables d'env > .env >
    config/<APP_ENV>.yaml. Les secrets et overrides locaux vivent dans .env,
    la config publique versionnée dans config/.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Ajoute la config publique YAML (par environnement) en dernière priorité."""
        yaml_file = _CONFIG_DIR / f"{_resolve_app_env()}.yaml"
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        ]
        if yaml_file.is_file():
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=yaml_file))
        return tuple(sources)

    # Application
    APP_ENV: str = "development"
    PROJECT_NAME: str = "TestRCS"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # CORS — origines autorisées du front (vide = middleware désactivé)
    CORS_ORIGINS: list[str] = []

    # Base de données PostgreSQL — par composants (dev local / docker compose).
    POSTGRES_USER: str = "app"
    POSTGRES_PASSWORD: str = ""  # SECRET (.env)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "app"
    # Optionnel : "require" pour un Postgres managé/TLS.
    POSTGRES_SSLMODE: str = ""

    # Override optionnel : URL complète (un Postgres managé en fournit une toute
    # faite). Si renseignée, elle prend le pas sur les variables POSTGRES_*.
    DATABASE_URL: str = ""

    @model_validator(mode="after")
    def _assemble_database_url(self) -> "Settings":
        if self.DATABASE_URL:
            self.DATABASE_URL = _normalize_async_url(self.DATABASE_URL)
        else:
            url = (
                f"postgresql+asyncpg://{quote_plus(self.POSTGRES_USER)}:"
                f"{quote_plus(self.POSTGRES_PASSWORD)}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
            if self.POSTGRES_SSLMODE and self.POSTGRES_SSLMODE != "disable":
                url += "?ssl=true"
            self.DATABASE_URL = url
        return self

    # OIDC — le flow de login est géré par le front ; l'API ne fait que valider
    # les tokens (JWKS découvert automatiquement depuis l'issuer).
    OIDC_ISSUER: str
    OIDC_AUDIENCE: str
    # Claim portant les rôles applicatifs : dépend du fournisseur OIDC.
    # Ex. "roles", "urn:zitadel:iam:org:project:roles" (Zitadel),
    # "realm_access.roles" (Keycloak, imbriqué — adapter _extract_roles).
    OIDC_ROLES_CLAIM: str = "roles"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
