#!/usr/bin/env bash
# Gera dist/sharescreen_<versão>_all.deb (instalável com duplo clique no Linux Mint/Ubuntu/Debian).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); from sharescreen import VERSION; print(VERSION)")"
BUILD="$(mktemp -d)"
PKG="$BUILD/sharescreen_${VERSION}_all"
trap 'rm -rf "$BUILD"' EXIT

mkdir -p "$PKG/DEBIAN" "$PKG/usr/lib/sharescreen" "$PKG/usr/bin" \
         "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/scalable/apps" \
         "$PKG/usr/share/doc/sharescreen"

cp -r "$ROOT/sharescreen" "$ROOT/run.py" "$PKG/usr/lib/sharescreen/"
find "$PKG/usr/lib/sharescreen" -name '__pycache__' -type d -prune -exec rm -rf {} +

cat > "$PKG/usr/bin/sharescreen" <<'EOF'
#!/bin/sh
exec python3 /usr/lib/sharescreen/run.py "$@"
EOF
chmod 755 "$PKG/usr/bin/sharescreen"

sed "s|@BIN@|sharescreen|g" "$ROOT/packaging/sharescreen.desktop.in" \
  > "$PKG/usr/share/applications/sharescreen.desktop"
install -m 644 "$ROOT/sharescreen/data/sharescreen.svg" \
  "$PKG/usr/share/icons/hicolor/scalable/apps/sharescreen.svg"
install -m 644 "$ROOT/README.md" "$PKG/usr/share/doc/sharescreen/README.md"
install -m 644 "$ROOT/LICENSE" "$PKG/usr/share/doc/sharescreen/copyright"

SIZE="$(du -sk "$PKG/usr" | cut -f1)"
cat > "$PKG/DEBIAN/control" <<EOF
Package: sharescreen
Version: $VERSION
Section: graphics
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3 (>= 3.8), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, ffmpeg
Recommends: gir1.2-xapp-1.0 | gir1.2-ayatanaappindicator3-0.1, gir1.2-notify-0.7, pulseaudio-utils, gnome-session-canberra
Suggests: gstreamer1.0-pipewire, gir1.2-gstreamer-1.0, gstreamer1.0-plugins-ugly
Maintainer: ShareScreen <sharescreen@localhost>
Description: Captura de tela e gravação de vídeo/GIF, estilo ShareX
 Captura região, janela, monitor ou tela inteira, grava vídeo (MP4/WebM/MKV)
 e GIF com áudio, editor de imagens com setas, texto, numeração, desfoque e
 recorte, histórico com miniaturas, atalhos globais e ícone na bandeja.
EOF

find "$PKG" -type d -exec chmod 755 {} +
find "$PKG/usr/lib" "$PKG/usr/share" -type f -exec chmod 644 {} +
chmod 755 "$PKG/usr/lib/sharescreen/run.py"

mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$PKG" "$ROOT/dist/sharescreen_${VERSION}_all.deb" >/dev/null
echo "Pacote gerado: dist/sharescreen_${VERSION}_all.deb"
