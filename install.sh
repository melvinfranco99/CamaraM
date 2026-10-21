#!/usr/bin/env bash
# Instalador de CamaraM.
#   ./install.sh            -> instala para el usuario actual (~/.local, no necesita sudo)
#   sudo ./install.sh --system -> instala para todo el sistema (/usr/local)
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--system" ]]; then
    PREFIX="${PREFIX:-/usr/local}"
    DATA="$PREFIX/share"
    BIN="$PREFIX/bin"
else
    DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
    BIN="$HOME/.local/bin"
fi
APPDIR="$DATA/camaram"

echo "==> Comprobando dependencias"
missing=()
command -v python3 >/dev/null || missing+=("python3")
python3 -c "from PyQt6.QtMultimedia import QCamera" 2>/dev/null || missing+=("PyQt6 con QtMultimedia")
command -v ffmpeg >/dev/null || missing+=("ffmpeg")
if ((${#missing[@]})); then
    echo "Faltan dependencias: ${missing[*]}"
    if command -v pacman >/dev/null; then
        echo "  Instálalas con: sudo pacman -S --needed python-pyqt6 qt6-multimedia qt6-multimedia-ffmpeg ffmpeg"
    elif command -v apt >/dev/null; then
        echo "  Instálalas con: sudo apt install python3-pyqt6 python3-pyqt6.qtmultimedia ffmpeg"
    elif command -v dnf >/dev/null; then
        echo "  Instálalas con: sudo dnf install python3-pyqt6 qt6-qtmultimedia ffmpeg"
    fi
    exit 1
fi

echo "==> Instalando en $APPDIR"
rm -rf "$APPDIR"
install -d "$APPDIR/camaram" "$BIN" "$DATA/applications" "$DATA/icons/hicolor/scalable/apps"
install -m644 "$SRC"/camaram/*.py "$SRC/camaram/camaram.svg" "$APPDIR/camaram/"
install -m644 "$SRC/camaram/camaram.svg" "$DATA/icons/hicolor/scalable/apps/camaram.svg"

cat > "$BIN/camaram" <<LAUNCHER
#!/bin/sh
export PYTHONPATH="$APPDIR\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m camaram "\$@"
LAUNCHER
chmod 755 "$BIN/camaram"

sed "s|^Exec=.*|Exec=$BIN/camaram|" "$SRC/data/camaram.desktop" > "$DATA/applications/camaram.desktop"
chmod 644 "$DATA/applications/camaram.desktop"

command -v update-desktop-database >/dev/null && update-desktop-database -q "$DATA/applications" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -qtf "$DATA/icons/hicolor" 2>/dev/null || true

echo "==> CamaraM instalada."
echo "    Ábrela desde el menú de aplicaciones o ejecutando: camaram"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "    (Aviso: $BIN no está en tu PATH)";; esac
