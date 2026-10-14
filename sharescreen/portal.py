"""xdg-desktop-portal: captura e gravação em sessões Wayland."""
import random

from gi.repository import Gio, GLib

BUS = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"


class _Portal:
    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.sender = self.bus.get_unique_name()[1:].replace(".", "_")

    def _token(self):
        return f"sharescreen{random.randint(0, 1 << 30)}"

    def request(self, iface, method, args_fmt, args, options, callback):
        """Chama um método que devolve um Request e espera o sinal Response."""
        token = self._token()
        options = dict(options)
        options["handle_token"] = GLib.Variant("s", token)
        handle = f"/org/freedesktop/portal/desktop/request/{self.sender}/{token}"
        sub = [0]

        def on_response(_conn, _sender, _path, _iface, _signal, params):
            self.bus.signal_unsubscribe(sub[0])
            code, results = params.unpack()
            callback(code, results)

        sub[0] = self.bus.signal_subscribe(BUS, "org.freedesktop.portal.Request", "Response",
                                           handle, None, Gio.DBusSignalFlags.NO_MATCH_RULE,
                                           on_response)

        def on_called(conn, res):
            try:
                conn.call_finish(res)
            except GLib.Error as e:
                self.bus.signal_unsubscribe(sub[0])
                callback(2, {"error": e.message})

        self.bus.call(BUS, PATH, iface, method,
                      GLib.Variant(args_fmt, tuple(args) + (options,)),
                      GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, -1, None, on_called)


def screenshot(callback, interactive=False):
    """callback(caminho_ou_None)."""
    try:
        portal = _Portal()
    except GLib.Error:
        callback(None)
        return

    def done(code, results):
        uri = results.get("uri") if code == 0 else None
        callback(Gio.File.new_for_uri(uri).get_path() if uri else None)

    portal.request("org.freedesktop.portal.Screenshot", "Screenshot", "(sa{sv})", [""],
                   {"interactive": GLib.Variant("b", interactive)}, done)


class ScreenCast:
    """Abre uma sessão de screencast e entrega (fd, node_id) do PipeWire."""

    def __init__(self, cursor=True):
        self.portal = _Portal()
        self.cursor = cursor
        self.session = None

    def start(self, on_ready, on_error):
        sc = "org.freedesktop.portal.ScreenCast"

        def created(code, results):
            if code != 0:
                return on_error("Sessão de gravação recusada.")
            self.session = results["session_handle"]
            opts = {"types": GLib.Variant("u", self._source_types()), "multiple": GLib.Variant("b", False),
                    "cursor_mode": GLib.Variant("u", 2 if self.cursor else 1)}
            self.portal.request(sc, "SelectSources", "(oa{sv})", [self.session], opts, selected)

        def selected(code, _results):
            if code != 0:
                return on_error("Seleção de tela cancelada.")
            self.portal.request(sc, "Start", "(osa{sv})", [self.session, ""], {}, started)

        def started(code, results):
            if code != 0 or not results.get("streams"):
                return on_error("Gravação cancelada.")
            node_id = results["streams"][0][0]
            try:
                ret, fds = self.portal.bus.call_with_unix_fd_list_sync(
                    BUS, PATH, sc, "OpenPipeWireRemote",
                    GLib.Variant("(oa{sv})", (self.session, {})),
                    GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1, None, None)
                fd = fds.get(ret.unpack()[0])
            except GLib.Error as e:
                return on_error(e.message)
            on_ready(fd, node_id)

        self.portal.request(sc, "CreateSession", "(a{sv})", [],
                            {"session_handle_token": GLib.Variant("s", self.portal._token())},
                            created)

    def _source_types(self):
        """Monitor e janela, limitados ao que o portal oferece."""
        try:
            ret = self.portal.bus.call_sync(
                BUS, PATH, "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", ("org.freedesktop.portal.ScreenCast", "AvailableSourceTypes")),
                GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, 3000, None)
            available = ret.unpack()[0]
        except GLib.Error:
            available = 1
        return (1 | 2) & available or 1

    def close(self):
        if not self.session:
            return
        try:
            self.portal.bus.call_sync(BUS, self.session, "org.freedesktop.portal.Session",
                                      "Close", None, None, Gio.DBusCallFlags.NONE, -1, None)
        except GLib.Error:
            pass
        self.session = None
