#!/bin/sh
# One-command refresh of the future-forecast snapshot (see scripts/refresh_snapshot.py). Runs no git commands.
cd "$(dirname "$0")/.." || exit 1
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" scripts/refresh_snapshot.py "$@"
