#!/bin/sh
# The build container may lack DNS. Download trusted wheels through the host's normal TLS-verified pip route.
set -eu
cd "$(dirname "$0")/.."
KERAN_BUILD_DIR=$(mktemp -d /tmp/keran-image-XXXXXX)
trap 'rm -rf "$KERAN_BUILD_DIR"' EXIT
mkdir "$KERAN_BUILD_DIR/wheels"
.venv/bin/python -m pip download --only-binary=:all: -r requirements.txt -d "$KERAN_BUILD_DIR/wheels"
.venv/bin/python - "$KERAN_BUILD_DIR/Dockerfile" <<'PY'
import sys
from pathlib import Path
source=Path('Dockerfile').read_text()
source=source.replace('RUN pip install --no-cache-dir -r requirements.txt','COPY --from=wheelhouse / /wheels/\nRUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels')
Path(sys.argv[1]).write_text(source)
PY
docker build --build-context "wheelhouse=$KERAN_BUILD_DIR/wheels" -f "$KERAN_BUILD_DIR/Dockerfile" -t keran-platform:review .
