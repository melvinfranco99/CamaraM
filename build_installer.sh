#!/usr/bin/env bash
# Genera dist/CamaraM-<versión>-installer.sh: un único archivo autoextraíble que instala CamaraM.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
VERSION=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' camaram/app.py)
OUT="dist/CamaraM-$VERSION-installer.sh"
mkdir -p dist
{
    cat <<'HEAD'
#!/usr/bin/env bash
# Instalador autoextraíble de CamaraM. Uso: bash CamaraM-installer.sh [--system]
set -euo pipefail
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
sed '1,/^__PAYLOAD__$/d' "$0" | base64 -d | tar -xz -C "$TMP"
bash "$TMP/CamaraM/install.sh" "$@"
exit 0
__PAYLOAD__
HEAD
    tar -cz --transform 's,^,CamaraM/,' --exclude='__pycache__' \
        camaram data install.sh uninstall.sh LICENSE README.md | base64
} > "$OUT"
chmod 755 "$OUT"
tar -cz --transform "s,^,CamaraM-$VERSION/," --exclude='__pycache__' \
    -f "dist/CamaraM-$VERSION.tar.gz" camaram data install.sh uninstall.sh LICENSE README.md
echo "Generado: $OUT y dist/CamaraM-$VERSION.tar.gz"
