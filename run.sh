#!/usr/bin/env bash
# Modo dev: compila schemas localmente e roda sem instalar.
set -euo pipefail
cd "$(dirname "$0")"
if command -v glib-compile-schemas >/dev/null 2>&1; then
  glib-compile-schemas data/ >/dev/null
fi
export GSETTINGS_SCHEMA_DIR="$PWD/data"
export PYTHONPATH="$PWD:${PYTHONPATH:-}"
exec python3 main.py "$@"
