#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export DATA_DIR="${DATA_DIR:-$PWD/var/demo}"
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py seed --demo
exec .venv/bin/python manage.py runserver 0.0.0.0:8000 --noreload
