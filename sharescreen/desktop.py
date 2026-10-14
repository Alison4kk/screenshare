"""Integração com o ambiente: iniciar com o sistema e atalhos do sistema que conflitam."""
import os
import shutil
import sys

from gi.repository import Gdk, Gio, GLib, Gtk

from . import APP_NAME, paths

# Atalhos de captura dos ambientes mais comuns que costumam ocupar a tecla Print.
SYSTEM_BINDINGS = [
    ("org.cinnamon.desktop.keybindings.media-keys",
     ["screenshot", "screenshot-clip", "window-screenshot", "window-screenshot-clip",
      "area-screenshot", "area-screenshot-clip"]),
    ("org.gnome.settings-daemon.plugins.media-keys",
     ["screenshot", "screenshot-clip", "window-screenshot", "window-screenshot-clip",
      "area-screenshot", "area-screenshot-clip"]),
    ("org.gnome.shell.keybindings",
     ["show-screenshot-ui", "screenshot", "screenshot-window"]),
    ("org.mate.Marco.global-keybindings",
     ["run-command-screenshot", "run-command-window-screenshot"]),
]

SYSTEM_LABELS = {
    "org.cinnamon.desktop.keybindings.media-keys": "Cinnamon",
    "org.gnome.settings-daemon.plugins.media-keys": "GNOME",
    "org.gnome.shell.keybindings": "GNOME Shell",
    "org.mate.Marco.global-keybindings": "MATE",
}


def _settings(schema):
    source = Gio.SettingsSchemaSource.get_default()
    if not source:
        return None, None
    found = source.lookup(schema, True)
    if not found:
        return None, None
    return Gio.Settings.new(schema), found


def normalize(accel):
    if not accel or accel == "disabled":
        return None
    keyval, mods = Gtk.accelerator_parse(accel)
    if not keyval:
        return None
    if keyval == Gdk.KEY_Sys_Req:
        keyval = Gdk.KEY_Print
    if mods & Gdk.ModifierType.MOD4_MASK:
        mods = (mods & ~Gdk.ModifierType.MOD4_MASK) | Gdk.ModifierType.SUPER_MASK
    keep = (Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK
            | Gdk.ModifierType.MOD1_MASK | Gdk.ModifierType.SUPER_MASK)
    return keyval, int(mods & keep)


def _values(settings, key):
    v = settings.get_value(key)
    if v.get_type_string() == "as":
        return "as", list(v.unpack())
    if v.get_type_string() == "s":
        return "s", [v.unpack()]
    return None, []


def find_conflicts(accels):
    """Lista atalhos do sistema que usam alguma das combinações em `accels`."""
    wanted = {normalize(a) for a in accels if a}
    wanted.discard(None)
    found = []
    for schema, keys in SYSTEM_BINDINGS:
        settings, schema_obj = _settings(schema)
        if not settings:
            continue
        for key in keys:
            if not schema_obj.has_key(key):
                continue
            vtype, vals = _values(settings, key)
            hits = [v for v in vals if normalize(v) in wanted]
            if hits:
                found.append({"schema": schema, "key": key, "type": vtype,
                              "original": vals, "hits": hits})
    return found


def release(conflicts):
    """Remove dos atalhos do sistema as combinações conflitantes. Retorna o backup."""
    backup = []
    for c in conflicts:
        settings, _ = _settings(c["schema"])
        if not settings:
            continue
        if c["type"] == "as":
            remaining = [v for v in c["original"] if v not in c["hits"]]
            settings.set_value(c["key"], GLib.Variant("as", remaining))
        else:
            settings.set_value(c["key"], GLib.Variant("s", "disabled"))
        backup.append({"schema": c["schema"], "key": c["key"], "type": c["type"],
                       "original": c["original"]})
    Gio.Settings.sync()
    return backup


def restore(backup):
    for b in backup:
        settings, schema_obj = _settings(b["schema"])
        if not settings or not schema_obj.has_key(b["key"]):
            continue
        if b["type"] == "as":
            settings.set_value(b["key"], GLib.Variant("as", b["original"]))
        else:
            settings.set_value(b["key"], GLib.Variant("s", b["original"][0]))
    Gio.Settings.sync()


KEY_LABELS = {
    "screenshot": "captura de tela",
    "screenshot-clip": "captura para a área de transferência",
    "window-screenshot": "captura de janela",
    "window-screenshot-clip": "captura de janela para a área de transferência",
    "area-screenshot": "captura de área",
    "area-screenshot-clip": "captura de área para a área de transferência",
    "show-screenshot-ui": "ferramenta de captura",
    "screenshot-window": "captura de janela",
    "run-command-screenshot": "captura de tela",
    "run-command-window-screenshot": "captura de janela",
}


def describe(conflicts):
    lines = []
    for c in conflicts:
        sysname = SYSTEM_LABELS.get(c["schema"], c["schema"])
        keys = ", ".join(Gtk.accelerator_get_label(*Gtk.accelerator_parse(h)) for h in c["hits"])
        lines.append(f"{keys} → {KEY_LABELS.get(c['key'], c['key'])} do {sysname}")
    return lines


# ---------------------------------------------------------------- autostart
AUTOSTART_FILE = os.path.join(GLib.get_user_config_dir(), "autostart", "sharescreen.desktop")


def _quote(arg):
    """Aspas conforme a especificação Desktop Entry (também válidas no shell)."""
    if arg and all(c.isalnum() or c in "/._-+" for c in arg):
        return arg
    escaped = "".join("\\" + c if c in '"`$\\' else c for c in arg)
    return f'"{escaped}"'


def launcher_command():
    exe = shutil.which("sharescreen")
    if exe:
        return _quote(exe)
    run = os.path.join(os.path.dirname(paths.PKG_DIR), "run.py")
    if os.path.exists(run):
        return f"{_quote(sys.executable)} {_quote(run)}"
    return f"{_quote(sys.executable)} -m sharescreen"


def set_autostart(enabled):
    if not enabled:
        try:
            os.remove(AUTOSTART_FILE)
        except OSError:
            pass
        return
    os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
    with open(AUTOSTART_FILE, "w", encoding="utf-8") as f:
        f.write(f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Comment=Captura de tela e gravação
Exec={launcher_command()} --background
Icon=sharescreen
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
""")


def autostart_enabled():
    return os.path.exists(AUTOSTART_FILE)
