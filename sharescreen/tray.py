"""Ícone na bandeja: XApp (Mint/Cinnamon/MATE/Xfce), AppIndicator ou GtkStatusIcon."""
import gi
from gi.repository import Gtk

from . import APP_NAME, paths

try:
    gi.require_version("XApp", "1.0")
    from gi.repository import XApp
except (ValueError, ImportError):
    XApp = None

AppIndicator = None
for _ns in ("AyatanaAppIndicator3", "AppIndicator3"):
    try:
        gi.require_version(_ns, "0.1")
        AppIndicator = __import__("gi.repository." + _ns, fromlist=[_ns])
        break
    except (ValueError, ImportError):
        continue


class Tray:
    def __init__(self, on_activate, build_menu):
        self.on_activate = on_activate
        self.build_menu = build_menu
        self.icon_normal = paths.resource("sharescreen-tray.svg")
        self.icon_rec = paths.resource("sharescreen-recording.svg")
        self.menu = build_menu()
        self.backend = None
        self._icon = None
        if XApp and XApp.StatusIcon.any_monitors():
            self._setup_xapp()
        elif AppIndicator:
            self._setup_indicator()
        elif XApp:
            self._setup_xapp()
        else:
            self._setup_gtk()

    def _setup_xapp(self):
        icon = XApp.StatusIcon()
        icon.set_name("sharescreen")
        icon.set_icon_name(self.icon_normal)
        icon.set_tooltip_text(APP_NAME)
        icon.set_secondary_menu(self.menu)
        icon.connect("activate", lambda *_: self.on_activate())
        icon.set_visible(True)
        self._icon = icon
        self.backend = "xapp"

    def _setup_indicator(self):
        ind = AppIndicator.Indicator.new("sharescreen", self.icon_normal,
                                         AppIndicator.IndicatorCategory.APPLICATION_STATUS)
        ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        ind.set_title(APP_NAME)
        ind.set_menu(self.menu)
        self._icon = ind
        self.backend = "appindicator"

    def _setup_gtk(self):
        icon = Gtk.StatusIcon.new_from_file(self.icon_normal)
        icon.set_tooltip_text(APP_NAME)
        icon.connect("activate", lambda *_: self.on_activate())
        icon.connect("popup-menu", lambda _i, button, t: self.menu.popup(
            None, None, None, None, button, t))
        self._icon = icon
        self.backend = "gtk"

    def rebuild(self):
        self.menu = self.build_menu()
        if self.backend == "xapp":
            self._icon.set_secondary_menu(self.menu)
        elif self.backend == "appindicator":
            self._icon.set_menu(self.menu)

    def set_recording(self, recording, tooltip=None):
        path = self.icon_rec if recording else self.icon_normal
        tip = tooltip or (f"{APP_NAME} — gravando" if recording else APP_NAME)
        if self.backend == "xapp":
            self._icon.set_icon_name(path)
            self._icon.set_tooltip_text(tip)
        elif self.backend == "appindicator":
            self._icon.set_icon_full(path, tip)
        elif self.backend == "gtk":
            self._icon.set_from_file(path)
            self._icon.set_tooltip_text(tip)

    def set_tooltip(self, text):
        if self.backend in ("xapp", "gtk"):
            self._icon.set_tooltip_text(text)

    def hide(self):
        if self.backend == "xapp":
            self._icon.set_visible(False)
        elif self.backend == "appindicator":
            self._icon.set_status(AppIndicator.IndicatorStatus.PASSIVE)
        elif self.backend == "gtk":
            self._icon.set_visible(False)
