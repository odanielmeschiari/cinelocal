#!/usr/bin/env bash
# Runs CineLocal straight from the project folder (without installing to the menu).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip >/dev/null
    .venv/bin/pip install -r requirements.txt
fi
exec .venv/bin/python main.py "$@"
