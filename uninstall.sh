#!/usr/bin/env bash
# Remove o ShareScreen instalado pelo install.sh.
set -euo pipefail

PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
APP_DIR="$PREFIX/sharescreen/app"
BIN="$HOME/.local/bin/sharescreen"

if [ -x "$BIN" ]; then "$BIN" --quit >/dev/null 2>&1 || true; sleep 1; fi

# devolve ao sistema os atalhos de captura que o ShareScreen tenha liberado
if [ -f "$CONFIG/sharescreen/config.json" ] && [ -d "$APP_DIR" ]; then
  PYTHONPATH="$APP_DIR" python3 - "$CONFIG/sharescreen/config.json" <<'EOF' || true
import json, sys
import gi
gi.require_version("Gtk", "3.0")
from sharescreen import desktop
cfg = json.load(open(sys.argv[1]))
backup = cfg.get("released_system_keys") or []
if backup:
    desktop.restore(backup)
    cfg["released_system_keys"] = []
    json.dump(cfg, open(sys.argv[1], "w"), indent=2)
    print("Atalhos do sistema restaurados.")
EOF
fi

rm -rf "$PREFIX/sharescreen/app"
rm -f "$BIN" "$PREFIX/applications/sharescreen.desktop" \
      "$PREFIX/icons/hicolor/scalable/apps/sharescreen.svg" \
      "$CONFIG/autostart/sharescreen.desktop"
gtk-update-icon-cache -q -t -f "$PREFIX/icons/hicolor" 2>/dev/null || true
update-desktop-database -q "$PREFIX/applications" 2>/dev/null || true
echo "ShareScreen removido."

read -r -p "Apagar também configurações, histórico e miniaturas? (suas capturas NÃO são apagadas) [s/N] " ans
if [[ "$ans" =~ ^[SsYy] ]]; then
  rm -rf "$CONFIG/sharescreen" "$PREFIX/sharescreen" "${XDG_CACHE_HOME:-$HOME/.cache}/sharescreen"
  echo "Configurações removidas."
fi
