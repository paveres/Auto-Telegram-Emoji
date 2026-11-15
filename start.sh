#!/bin/sh
set -eu
cd "$(dirname "$0")"
test -x .venv/bin/python || { echo 'Сначала: python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt'; exit 1; }
test -f .env || .venv/bin/python scripts/setup.py
exec .venv/bin/python -m auto_telegram_emoji
