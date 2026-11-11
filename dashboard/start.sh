#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ] || [ ! -f frontend/dist/index.html ]; then
    sh setup.sh
fi
.venv/bin/python backend/import_predictions.py
printf '\nOpen http://127.0.0.1:%s in your browser. Press Ctrl+C here to stop.\n\n' "${PORT:-8000}"
exec .venv/bin/python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port "${PORT:-8000}"
