"""
Drop the PostgreSQL database if it exists.
Reads connection info from app.core.config (DATABASE_URL).
"""

import asyncio
import sys
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, ".")
from app.core.config import get_settings


async def drop_database_if_exists() -> None:
    settings = get_settings()

    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(url)

    db_name = parsed.path.lstrip("/")
    user = parsed.username
    password = parsed.password
    host = parsed.hostname
    port = parsed.port or 5432

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
        if not exists:
            print(f"Database '{db_name}' does not exist — nothing to do.")
            return

        # Terminate active connections before dropping
        await conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1 AND pid <> pg_backend_pid()
            """,
            db_name,
        )
        await conn.execute(f'DROP DATABASE "{db_name}"')
        print(f"Database '{db_name}' dropped.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(drop_database_if_exists())
