import datetime
import os
import shutil
import subprocess

from gi.repository import Gdk, Gio, GLib, Gtk


def is_wayland():
    return (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
            or bool(os.environ.get("WAYLAND_DISPLAY")))


def which(cmd):
    return shutil.which(cmd)


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def human_duration(seconds):
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def human_date(iso):
    try:
        dt = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    today = datetime.date.today()
    if dt.date() == today:
        return "Hoje, " + dt.strftime("%H:%M")
    if dt.date() == today - datetime.timedelta(days=1):
        return "Ontem, " + dt.strftime("%H:%M")
    return dt.strftime("%d/%m/%Y %H:%M")


def safe_strftime(pattern, when=None):
    when = when or datetime.datetime.now()
    try:
        text = when.strftime(pattern)
    except ValueError:
        text = when.strftime("%Y-%m-%d_%H-%M-%S")
    for ch in '/\\:*?"<>|':
        text = text.replace(ch, "-")
    return text.strip() or when.strftime("%Y-%m-%d_%H-%M-%S")


def unique_path(folder, base, ext):
    path = os.path.join(folder, f"{base}.{ext}")
    n = 1
    while os.path.exists(path):
        path = os.path.join(folder, f"{base}_{n}.{ext}")
        n += 1
    return path


def build_output_path(config, kind, ext):
    root = config["videos_dir"] if kind in ("video", "gif") else config["screenshots_dir"]
    root = os.path.expanduser(root)
    if config["use_subfolders"] and config["subfolder_pattern"].strip():
        root = os.path.join(root, safe_strftime(config["subfolder_pattern"]))
    os.makedirs(root, exist_ok=True)
    return unique_path(root, safe_strftime(config["filename_pattern"]), ext)


def save_pixbuf(pixbuf, path, fmt, quality=90):
    fmt = {"jpg": "jpeg"}.get(fmt, fmt)
    keys, values = [], []
    if fmt == "jpeg":
        quality = str(max(10, min(100, int(quality))))
        keys, values = ["quality"], [quality]
        if pixbuf.get_has_alpha():
            pixbuf = flatten_pixbuf(pixbuf)
    elif fmt == "webp":
        keys, values = ["quality"], [str(max(10, min(100, int(quality))))]
    elif fmt == "png":
        keys, values = ["compression"], ["6"]
    pixbuf.savev(path, fmt, keys, values)


def flatten_pixbuf(pixbuf):
    """Remove o canal alfa compondo sobre branco (necessário para JPEG)."""
    import cairo
    w, h = pixbuf.get_width(), pixbuf.get_height()
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
    ctx = cairo.Context(surf)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
    ctx.paint()
    surf.flush()
    return Gdk.pixbuf_get_from_surface(surf, 0, 0, w, h)


def open_file(path):
    uri = Gio.File.new_for_path(path).get_uri()
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except GLib.Error:
        if which("xdg-open"):
            subprocess.Popen(["xdg-open", path])


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    open_file(path)


def show_in_folder(path):
    """Abre o gerenciador de arquivos com o arquivo selecionado."""
    uri = Gio.File.new_for_path(path).get_uri()
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
                      "org.freedesktop.FileManager1", "ShowItems",
                      GLib.Variant("(ass)", ([uri], "")), None,
                      Gio.DBusCallFlags.NONE, 2000, None)
    except GLib.Error:
        open_folder(os.path.dirname(path))


_SOUND_FILES = {
    "camera-shutter": "/usr/share/sounds/freedesktop/stereo/camera-shutter.oga",
    "complete": "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "message": "/usr/share/sounds/freedesktop/stereo/message.oga",
    "bell": "/usr/share/sounds/freedesktop/stereo/bell.oga",
}


def play_sound(name):
    try:
        if which("canberra-gtk-play"):
            subprocess.Popen(["canberra-gtk-play", "-i", name],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif which("paplay") and os.path.exists(_SOUND_FILES.get(name, "")):
            subprocess.Popen(["paplay", _SOUND_FILES[name]],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def copy_image(pixbuf):
    cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    cb.set_image(pixbuf)
    cb.store()


def copy_text(text):
    cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    cb.set_text(text, -1)
    cb.store()


class _FileClipboard:
    """Coloca um arquivo na área de transferência (como o "Copiar" do gerenciador de arquivos).

    Oferece text/uri-list e x-special/gnome-copied-files (colar em chats, navegadores e
    pastas), o conteúdo bruto no tipo MIME do arquivo (ex.: image/gif) e o caminho como texto.
    """

    def __init__(self):
        self.widget = Gtk.Invisible()
        self.widget.realize()
        self.widget.connect("selection-get", self._on_get)
        self.path = None
        self.targets = []

    def set(self, path, mime=None):
        self.path = path
        names = ["x-special/gnome-copied-files", "text/uri-list"]
        if mime:
            names.append(mime)
        names += ["UTF8_STRING", "text/plain;charset=utf-8", "text/plain", "STRING"]
        self.targets = names
        sel = Gdk.SELECTION_CLIPBOARD
        Gtk.selection_clear_targets(self.widget, sel)
        for i, name in enumerate(names):
            Gtk.selection_add_target(self.widget, sel, Gdk.Atom.intern(name, False), i)
        Gtk.selection_owner_set(self.widget, sel, Gtk.get_current_event_time())

    def _on_get(self, _widget, data, info, _time):
        if not self.path or info >= len(self.targets):
            return
        name = self.targets[info]
        uri = Gio.File.new_for_path(self.path).get_uri()
        target = Gdk.Atom.intern(name, False)
        if name == "x-special/gnome-copied-files":
            data.set(target, 8, f"copy\n{uri}".encode())
        elif name == "text/uri-list":
            data.set(target, 8, f"{uri}\r\n".encode())
        elif "/" in name and not name.startswith("text/"):
            try:
                with open(self.path, "rb") as f:
                    data.set(target, 8, f.read())
            except OSError:
                pass
        else:
            data.set_text(self.path, -1)


_file_clipboard = None


def copy_file(path, mime=None):
    global _file_clipboard
    if _file_clipboard is None:
        _file_clipboard = _FileClipboard()
    _file_clipboard.set(path, mime)


def trash(path):
    """Move para a lixeira. Retorna True se deu certo."""
    try:
        return Gio.File.new_for_path(path).trash(None)
    except GLib.Error:
        return False


def run_async(argv, callback=None, stderr_path=None, stdin_pipe=False):
    """Executa um processo sem bloquear. callback(ok, status) quando terminar."""
    launcher = Gio.SubprocessLauncher.new(
        Gio.SubprocessFlags.STDIN_PIPE if stdin_pipe else Gio.SubprocessFlags.NONE)
    if stderr_path:
        launcher.set_stderr_file_path(stderr_path)
        launcher.set_stdout_file_path(os.devnull)
    else:
        launcher.set_flags((Gio.SubprocessFlags.STDIN_PIPE if stdin_pipe else Gio.SubprocessFlags.NONE)
                           | Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE)
    proc = launcher.spawnv(argv)

    def done(p, res):
        try:
            p.wait_finish(res)
        except GLib.Error:
            pass
        status = p.get_exit_status() if p.get_if_exited() else -1
        if callback:
            callback(status == 0, status)

    proc.wait_async(None, done)
    return proc


def tail_file(path, lines=6):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = f.read().strip().splitlines()
        return "\n".join(data[-lines:])
    except OSError:
        return ""
