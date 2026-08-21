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

# Optional CUDA backend: shipped as its own download (packaging/linux/construir.sh consumers
# fetch it on demand, see GpuPackManager), never inside the base install — it alone dwarfs the
# rest of the bundle.
GPU_MODULE="$BUNDLE/lib/libggml-cuda.so"
if [ -f "$GPU_MODULE" ]; then
  echo "== Empacotando modulo de GPU separado"
  GPU_TAR="$OUT_DIR/dito-gpu-cuda-linux-x64.tar.gz"
  rm -f "$GPU_TAR"
  tar -czf "$GPU_TAR" -C "$BUNDLE/lib" "libggml-cuda.so"
fi

echo "== Gerando pacote .tar.gz"
TAR_FILE="$OUT_DIR/dito-$VERSAO-linux-x64.tar.gz"
rm -f "$TAR_FILE"
tar -czf "$TAR_FILE" -C "$BUNDLE" --exclude="lib/libggml-cuda.so" .

echo "== Gerando pacote Debian (.deb)"
DEB_ROOT="/tmp/dito-deb-$VERSAO"
rm -rf "$DEB_ROOT"
mkdir -p "$DEB_ROOT/opt/dito" "$DEB_ROOT/usr/bin" "$DEB_ROOT/usr/share/applications" "$DEB_ROOT/usr/share/icons/hicolor/scalable/apps" "$DEB_ROOT/DEBIAN"

cp -r "$BUNDLE"/* "$DEB_ROOT/opt/dito/"
rm -f "$DEB_ROOT/opt/dito/lib/libggml-cuda.so"

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
Depends: libgtk-3-0, libx11-6, xdotool, libayatana-appindicator3-1 | libappindicator3-1, curl, libnotify-bin, pulseaudio-utils, sound-theme-freedesktop
Maintainer: Defalt <contato@defaltm.com>
Description: Ditado por voz offline e transcricao com Whisper C++ nativo
EOF

# Baixa o backend de GPU durante o proprio "apt install" (nao no primeiro uso do app) — so
# quando ha uma NVIDIA compativel; nunca falha a instalacao se o download der errado.
cat <<'EOF' > "$DEB_ROOT/DEBIAN/postinst"
#!/usr/bin/env bash
set -e
if [ -e /proc/driver/nvidia/version ]; then
  echo "Dito: GPU NVIDIA detectada, baixando aceleracao (~130MB)..."
  TMP="$(mktemp -d)"
  if curl -fsSL -o "$TMP/gpu.tar.gz" \
       "https://pub-f37d3271bc70461b99c358c10a592ee6.r2.dev/dito/dito-gpu-cuda-linux-x64.tar.gz" \
     && tar -xzf "$TMP/gpu.tar.gz" -C /opt/dito/lib; then
    echo "Dito: aceleracao de GPU pronta."
  else
    echo "Dito: nao consegui baixar a aceleracao de GPU agora — segue em CPU, o app tenta de novo sozinho."
  fi
  rm -rf "$TMP"
fi
exit 0
EOF
chmod +x "$DEB_ROOT/DEBIAN/postinst"

DEB_FILE="$OUT_DIR/dito_${VERSAO}_amd64.deb"
dpkg-deb --build "$DEB_ROOT" "$DEB_FILE"
rm -rf "$DEB_ROOT"

mkdir -p "$RAIZ/dist"
cp "$DEB_FILE" "$RAIZ/dist/"

echo "== Calculando SHA-256"
cd "$OUT_DIR"
SOMAR="dito-$VERSAO-linux-x64.tar.gz dito_${VERSAO}_amd64.deb"
[ -f "dito-gpu-cuda-linux-x64.tar.gz" ] && SOMAR="$SOMAR dito-gpu-cuda-linux-x64.tar.gz"
sha256sum $SOMAR > SHA256SUMS.txt

echo "== Concluido com sucesso em $OUT_DIR"
ls -lh "$OUT_DIR"

if [ -f "$OUT_DIR/dito-gpu-cuda-linux-x64.tar.gz" ]; then
  echo ""
  echo "Pacote de GPU acima de 25MB: nao vai pro Cloudflare Pages (apt-repo.sh), sobe pro R2 a mao:"
  echo "  npx wrangler r2 object put defaltm-releases/dito/dito-gpu-cuda-linux-x64.tar.gz \\"
  echo "    --file=$OUT_DIR/dito-gpu-cuda-linux-x64.tar.gz --content-type=application/gzip --remote"
fi
