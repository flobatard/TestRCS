"""
Create the PostgreSQL database if it does not already exist.
Reads connection info from app.core.config (DATABASE_URL).
"""

import asyncio
import sys
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, ".")
from app.core.config import get_settings


async def create_database_if_not_exists() -> None:
    settings = get_settings()

    # DATABASE_URL uses asyncpg driver: postgresql+asyncpg://user:pass@host:port/dbname
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(url)

    db_name = parsed.path.lstrip("/")
    user = parsed.username
    password = parsed.password
    host = parsed.hostname
    port = parsed.port or 5432

    # Connect to the default 'postgres' maintenance database
    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database="postgres",
    )

    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )
        if exists:
            print(f"Database '{db_name}' already exists — skipping creation.")
        else:
            # CREATE DATABASE cannot run inside a transaction block
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            print(f"Database '{db_name}' created.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_database_if_not_exists())
