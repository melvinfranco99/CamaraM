#!/usr/bin/env bash
# Desinstala CamaraM (usa --system si la instalaste con sudo ./install.sh --system).
# Tus fotos y vídeos no se borran.
set -euo pipefail
if [[ "${1:-}" == "--system" ]]; then
    PREFIX="${PREFIX:-/usr/local}"; DATA="$PREFIX/share"; BIN="$PREFIX/bin"
else
    DATA="${XDG_DATA_HOME:-$HOME/.local/share}"; BIN="$HOME/.local/bin"
fi
rm -rf "$DATA/camaram"
rm -f "$BIN/camaram" "$DATA/applications/camaram.desktop" "$DATA/icons/hicolor/scalable/apps/camaram.svg"
command -v update-desktop-database >/dev/null && update-desktop-database -q "$DATA/applications" || true
echo "CamaraM desinstalada."
