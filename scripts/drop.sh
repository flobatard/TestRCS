#!/usr/bin/env bash
set -euo pipefail

read -r -p "Are you sure you want to drop the database? [y/N] " confirm
if [[ "${confirm,,}" != "y" ]]; then
    echo "Aborted."
    exit 1
fi

echo "==> Dropping database..."
python scripts/drop_db.py

echo "==> Done."
