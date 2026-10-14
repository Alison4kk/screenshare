"""Notificações com botões de ação (libnotify, com fallback para Gio)."""
import gi

from . import APP_NAME, paths

try:
    gi.require_version("Notify", "0.7")
    from gi.repository import Notify
except (ValueError, ImportError):
    Notify = None


class Notifier:
    def __init__(self, app):
        self.app = app
        self._active = []
        self._ok = bool(Notify) and Notify.init(APP_NAME)
        self._caps = Notify.get_server_caps() if self._ok else []

    def show(self, title, body="", icon=None, actions=(), on_click=None, urgent=False):
        """actions: lista de (id, rótulo, callback)."""
        icon = icon or paths.resource("sharescreen.svg")
        if not self._ok:
            self._fallback(title, body)
            return
        n = Notify.Notification.new(title, body, icon)
        n.set_hint("desktop-entry", _variant_s("sharescreen"))
        if urgent:
            n.set_urgency(Notify.Urgency.CRITICAL)
        if "actions" in self._caps:
            if on_click:
                n.add_action("default", "Abrir", lambda *_: on_click())
            for action_id, label, cb in actions:
                n.add_action(action_id, label, _wrap(cb))
        n.connect("closed", self._on_closed)
        self._active.append(n)
        if len(self._active) > 20:
            self._active.pop(0)
        try:
            n.show()
        except Exception:  # noqa: BLE001 — servidor de notificação indisponível
            self._fallback(title, body)

    def _on_closed(self, n):
        if n in self._active:
            self._active.remove(n)

    def _fallback(self, title, body):
        from gi.repository import Gio
        notification = Gio.Notification.new(title)
        if body:
            notification.set_body(body)
        self.app.send_notification(None, notification)


def _wrap(cb):
    return lambda *_args: cb()


def _variant_s(value):
    from gi.repository import GLib
    return GLib.Variant("s", value)
