#!/usr/bin/env bash
# Modo dev: compila schemas localmente e roda sem instalar.
set -euo pipefail
cd "$(dirname "$0")"
if command -v glib-compile-schemas >/dev/null 2>&1; then
  glib-compile-schemas data/ >/dev/null
fi
# Ícone no modo dev: instala em ~/.local/share/icons (best-effort, silencioso).
if [ -f assets/icon.svg ]; then
  ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
  mkdir -p "$ICON_DIR" 2>/dev/null || true
  cp -f assets/icon.svg "$ICON_DIR/fingerprint-manager.svg" 2>/dev/null || true
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
  fi
fi
export GSETTINGS_SCHEMA_DIR="$PWD/data"
export PYTHONPATH="$PWD:${PYTHONPATH:-}"
exec python3 main.py "$@"
