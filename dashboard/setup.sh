#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-lock.txt
(cd frontend && npm ci --no-audit --no-fund && npm run build)
.venv/bin/python backend/import_predictions.py
printf '\nSetup complete. Run: sh dashboard/start.sh from the project root.\n'
