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
# Atalho dev: sem .desktop instalado o GNOME não associa a janela ao ícone
# (mostra o genérico). Instala um apontando para este run.sh.
if [ -f data/org.example.fingerprint-manager.desktop ]; then
  APP_DIR="$HOME/.local/share/applications"
  mkdir -p "$APP_DIR" 2>/dev/null || true
  sed "s|^Exec=.*|Exec=$PWD/run.sh|" \
    data/org.example.fingerprint-manager.desktop \
    > "$APP_DIR/org.example.fingerprint-manager.desktop" 2>/dev/null || true
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
  fi
fi
export GSETTINGS_SCHEMA_DIR="$PWD/data"
export PYTHONPATH="$PWD:${PYTHONPATH:-}"
# Prefere a venv do uv (uv sync); cai para o python do sistema.
if [ -x "$PWD/.venv/bin/python" ]; then
  exec "$PWD/.venv/bin/python" main.py "$@"
fi
exec python3 main.py "$@"
