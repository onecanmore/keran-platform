#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py seed
DATA_DIR="$PWD/var/demo" .venv/bin/python manage.py migrate --noinput
DATA_DIR="$PWD/var/demo" .venv/bin/python manage.py seed --demo
.venv/bin/python manage.py check
