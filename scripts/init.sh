#!/usr/bin/env bash
set -euo pipefail

echo "==> Creating database if not exists..."
python scripts/init_db.py

echo "==> Running Alembic migrations..."
alembic upgrade head

echo "==> Done."
