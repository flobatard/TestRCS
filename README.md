# FastAPI + Alembic Template

Template de backend pour démarrer un projet **API REST**. Il fournit un socle
prêt à l'emploi : app factory, configuration multi-environnements, base de
données async et validation de tokens OIDC — sans aucune logique métier. À
cloner puis à adapter (renommer `PROJECT_NAME`, ajouter vos domaines).

Stack : **FastAPI** + **SQLAlchemy 2.0 (async)** + **Alembic** + **PostgreSQL
(asyncpg)** + **OIDC** (validation JWT côté resource-server).

## Architecture

```
app/
├── main.py            # FastAPI app factory + lifespan + CORS
├── core/              # cross-cutting concerns
│   ├── config.py      # settings (env > .env > config/<APP_ENV>.yaml)
│   ├── database.py    # async engine, session, declarative Base
│   └── auth.py        # validation JWT OIDC (JWKS) + get_current_user
├── models/            # un module par modèle, tous ré-exportés dans __init__.py
├── health/            # healthcheck (public)
└── auth/              # route de démo protégée GET /me
config/                # config publique par environnement (development.yaml, production.yaml)
alembic/               # migrations (env.py async)
tests/                 # pytest (sans réseau ni fournisseur OIDC réel)
```

Chaque nouveau domaine est un nouveau package sous `app/` avec ses `schemas.py`,
`service.py` et `router.py` ; ses modèles vont dans `app/models/<name>.py` et
sont importés (et listés dans `__all__`) dans `app/models/__init__.py` pour que
l'autogenerate d'Alembic les voie.

## Configuration

Les settings sont résolus par priorité décroissante : variables
d'environnement > `.env` > `config/<APP_ENV>.yaml` (`APP_ENV` vaut
`development` par défaut). Les valeurs publiques et versionnées (CORS, hôtes,
issuer/audience OIDC) vivent dans `config/` ; les secrets et overrides locaux
(`POSTGRES_PASSWORD`, éventuellement un `DATABASE_URL` complet) vivent dans
`.env`. L'URL de base de données est assemblée à partir des composants
`POSTGRES_*` avec encodage du mot de passe ; une URL de Postgres managé (avec
`sslmode=...`) peut être collée telle quelle dans `DATABASE_URL`, elle est
normalisée pour asyncpg.

## Authentification

Le flow de login OIDC (Authorization Code + PKCE) est censé être géré par le
client front. **Cette API n'émet jamais de tokens** : elle valide le token
d'accès à chaque requête — signature RS256 via le JWKS (découvert depuis
l'issuer), plus les vérifications `issuer`, `audience` et expiration. Deux
réglages suffisent : `OIDC_ISSUER` et `OIDC_AUDIENCE`.

Tout ce qui est spécifique au fournisseur d'identité est isolé dans
[app/core/auth.py](app/core/auth.py), pour qu'un changement de fournisseur ne
touche que ce fichier. Le claim portant les rôles applicatifs dépend du
fournisseur : il se configure via `OIDC_ROLES_CLAIM` (ex. `roles`, ou
`urn:zitadel:iam:org:project:roles` pour Zitadel).

Les routes protégées utilisent la dépendance `get_current_user` ;
`GET /api/v1/me` sert d'exemple de référence. `/api/v1/health` reste publique.

## Setup (dev local)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # secrets ; mettez vos URLs OIDC dans config/development.yaml
```

## Run

### Docker (nominal)

```bash
cp .env.example .env          # définir POSTGRES_PASSWORD (et APP_ENV=production en prod)
docker compose up --build
```

Les migrations s'appliquent automatiquement au démarrage (`alembic upgrade
head`), puis l'API écoute sur le port 8000. Un éventuel reverse proxy devant
l'API est hors périmètre de ce repo.

### Bare (dev)

```bash
uvicorn app.main:app --reload
```

Docs sur http://localhost:8000/docs · health sur http://localhost:8000/api/v1/health

## Migrations de base de données

```bash
alembic revision --autogenerate -m "..."   # créer une migration depuis les modèles
alembic upgrade head                        # appliquer les migrations
alembic downgrade -1                        # revenir une révision en arrière
```

Exécution manuelle dans Docker : `docker compose run --rm api alembic upgrade head`.

## Tests

```bash
pytest
```

Les tests d'auth signent des tokens avec une clé RSA générée et stubbent le
cache JWKS — aucun réseau ni fournisseur OIDC réel requis.
