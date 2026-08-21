#!/usr/bin/env bash
# Monta o pacote e o instalador .deb do Dito para Linux (64-bit).
#
#   bash packaging/linux/construir.sh
#
set -euo pipefail

export PATH="/opt/flutter/bin:$PATH"

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"

echo "== Verificando versao"
VERSAO=$(grep -m 1 '^version:' pubspec.yaml | awk '{print $2}' | cut -d'+' -f1)
echo "Dito $VERSAO (Linux x64 Nativo)"

echo "== Portao: analyze e test"
flutter analyze lib test
flutter test

echo "== Compilando binarios Linux"
flutter build linux --release

BUNDLE="$RAIZ/build/linux/x64/release/bundle"
OUT_DIR="$RAIZ/build/linux/installer"
mkdir -p "$OUT_DIR"

echo "== Gerando pacote .tar.gz"
TAR_FILE="$OUT_DIR/dito-$VERSAO-linux-x64.tar.gz"
rm -f "$TAR_FILE"
tar -czf "$TAR_FILE" -C "$BUNDLE" .

echo "== Gerando pacote Debian (.deb)"
DEB_ROOT="/tmp/dito-deb-$VERSAO"
rm -rf "$DEB_ROOT"
mkdir -p "$DEB_ROOT/opt/dito" "$DEB_ROOT/usr/bin" "$DEB_ROOT/usr/share/applications" "$DEB_ROOT/usr/share/icons/hicolor/scalable/apps" "$DEB_ROOT/DEBIAN"

cp -r "$BUNDLE"/* "$DEB_ROOT/opt/dito/"

cat <<EOF > "$DEB_ROOT/usr/bin/dito"
#!/usr/bin/env bash
exec /opt/dito/dito_app "\$@"
EOF
chmod +x "$DEB_ROOT/usr/bin/dito"

cat <<EOF > "$DEB_ROOT/usr/share/applications/dito.desktop"
[Desktop Entry]
Name=Dito
Comment=Ditado e transcricao por voz offline de alta precisao
Exec=/opt/dito/dito_app
Icon=dito
Terminal=false
Type=Application
StartupWMClass=dito_app
Categories=Utility;AudioVideo;
EOF

mkdir -p "$DEB_ROOT/usr/share/pixmaps"
if [ -d "$RAIZ/assets/icons" ]; then
  cp "$RAIZ/assets/icons/"*.svg "$DEB_ROOT/usr/share/icons/hicolor/scalable/apps/" 2>/dev/null || true
  cp "$RAIZ/assets/icons/icon.svg" "$DEB_ROOT/usr/share/pixmaps/dito.svg" 2>/dev/null || true
fi

cat <<EOF > "$DEB_ROOT/DEBIAN/control"
Package: dito
Version: $VERSAO
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Defalt <contato@defaltm.com>
Description: Ditado por voz offline e transcricao com Whisper C++ nativo
EOF

DEB_FILE="$OUT_DIR/dito_${VERSAO}_amd64.deb"
dpkg-deb --build "$DEB_ROOT" "$DEB_FILE"
rm -rf "$DEB_ROOT"

mkdir -p "$RAIZ/dist"
cp "$DEB_FILE" "$RAIZ/dist/"

echo "== Calculando SHA-256"
cd "$OUT_DIR"
sha256sum "dito-$VERSAO-linux-x64.tar.gz" "dito_${VERSAO}_amd64.deb" > SHA256SUMS.txt

echo "== Concluido com sucesso em $OUT_DIR"
ls -lh "$OUT_DIR"
