#!/usr/bin/env bash
# Instala o ShareScreen para o usuário atual (sem precisar de root, exceto para dependências).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$PREFIX/sharescreen/app"
BIN_DIR="$HOME/.local/bin"
BIN="$BIN_DIR/sharescreen"
APPS_DIR="$PREFIX/applications"
ICON_DIR="$PREFIX/icons/hicolor/scalable/apps"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }

bold "==> Verificando dependências"
missing=()
python3 - <<'EOF' 2>/dev/null || missing+=(python3-gi python3-gi-cairo gir1.2-gtk-3.0)
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
import cairo
gi.require_foreign("cairo")
from gi.repository import Gtk
EOF
command -v ffmpeg >/dev/null || missing+=(ffmpeg)
command -v pactl >/dev/null || missing+=(pulseaudio-utils)
python3 -c 'import gi; gi.require_version("Notify", "0.7"); from gi.repository import Notify' 2>/dev/null \
  || missing+=(gir1.2-notify-0.7)
if ! python3 -c 'import gi; gi.require_version("XApp", "1.0"); from gi.repository import XApp' 2>/dev/null \
  && ! python3 -c 'import gi; gi.require_version("AyatanaAppIndicator3", "0.1"); from gi.repository import AyatanaAppIndicator3' 2>/dev/null; then
  missing+=(gir1.2-ayatanaappindicator3-0.1)
fi

if [ ${#missing[@]} -gt 0 ]; then
  echo "Pacotes faltando: ${missing[*]}"
  if command -v apt-get >/dev/null; then
    read -r -p "Instalar agora com apt (pede sua senha)? [S/n] " ans
    if [[ -z "$ans" || "$ans" =~ ^[SsYy] ]]; then
      sudo apt-get install -y "${missing[@]}"
    else
      echo "Instale depois com: sudo apt install ${missing[*]}"
    fi
  else
    echo "Instale os equivalentes desses pacotes pelo gerenciador da sua distribuição."
  fi
else
  echo "Tudo certo."
fi

bold "==> Copiando arquivos"
# encerra uma instância em execução para atualizar sem conflitos
if [ -x "$BIN" ]; then "$BIN" --quit >/dev/null 2>&1 || true; sleep 1; fi
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR" "$BIN_DIR" "$APPS_DIR" "$ICON_DIR"
cp -r "$SRC/sharescreen" "$SRC/run.py" "$APP_DIR/"
find "$APP_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} +

cat > "$BIN" <<EOF
#!/bin/sh
exec python3 "$APP_DIR/run.py" "\$@"
EOF
chmod +x "$BIN"

install -m 644 "$SRC/sharescreen/data/sharescreen.svg" "$ICON_DIR/sharescreen.svg"
sed "s|@BIN@|$BIN|g" "$SRC/packaging/sharescreen.desktop.in" > "$APPS_DIR/sharescreen.desktop"
chmod 644 "$APPS_DIR/sharescreen.desktop"

gtk-update-icon-cache -q -t -f "$PREFIX/icons/hicolor" 2>/dev/null || true
update-desktop-database -q "$APPS_DIR" 2>/dev/null || true

bold "==> Pronto!"
echo "O ShareScreen está no menu de aplicativos (categoria Gráficos)."
echo "Também pode iniciar pelo terminal com: $BIN"
read -r -p "Abrir o ShareScreen agora? [S/n] " ans
if [[ -z "$ans" || "$ans" =~ ^[SsYy] ]]; then
  nohup "$BIN" >/dev/null 2>&1 &
fi
