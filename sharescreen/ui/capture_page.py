"""Página inicial: botões de captura/gravação e itens recentes."""
import os

from gi.repository import GdkPixbuf, Gtk

from .. import utils
from ..hotkeys import accel_label
from ..icons import Icon
from .widgets import PrefGroup, label

SCREEN_TILES = [
    ("region", "Região", "region", (0.04, 0.52, 1.0)),
    ("fullscreen", "Tela inteira", "fullscreen", (0.18, 0.72, 0.36)),
    ("window", "Janela ativa", "window", (0.62, 0.32, 0.87)),
    ("monitor", "Monitor atual", "monitor", (0.98, 0.55, 0.0)),
    ("last_region", "Última região", "last_region", (0.35, 0.34, 0.84)),
]
RECORD_TILES = [
    ("record", "Gravar vídeo", "record", (0.93, 0.22, 0.2)),
    ("record_gif", "Gravar GIF", "gif", (0.9, 0.2, 0.45)),
]


class CapturePage(Gtk.ScrolledWindow):
    def __init__(self, app, window):
        super().__init__()
        self.app = app
        self.window = window
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.hotkey_labels = {}

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_halign(Gtk.Align.CENTER)
        outer.set_size_request(760, -1)
        for side in ("top", "bottom", "start", "end"):
            getattr(outer, f"set_margin_{side}")(22)
        self.add(outer)

        outer.pack_start(label("Captura de tela", "section-title"), False, False, 0)
        outer.pack_start(self._tiles(SCREEN_TILES), False, False, 0)

        outer.pack_start(label("Gravação de tela", "section-title"), False, False, 6)
        self.rec_banner = self._recording_banner()
        outer.pack_start(self.rec_banner, False, False, 0)
        outer.pack_start(self._tiles(RECORD_TILES + [("open_folder", "Abrir pasta", "folder",
                                                      (0.45, 0.47, 0.52))]), False, False, 0)

        group = PrefGroup("Opções rápidas")
        group.set_margin_top(10)
        cfg = app.config
        group.spin(cfg, "capture_delay", "Atraso antes de capturar", 0, 30, 1,
                   "Útil para abrir menus antes da captura", suffix="s")
        group.switch(cfg, "ac_open_editor", "Abrir o editor após capturar",
                     "Para adicionar setas, textos, desfoque e recortar")
        group.switch(cfg, "capture_cursor", "Incluir o cursor do mouse nas capturas")
        outer.pack_start(group, False, False, 0)

        head = Gtk.Box()
        head.pack_start(label("Recentes", "section-title"), False, False, 0)
        more = Gtk.Button(label="Ver histórico")
        more.set_relief(Gtk.ReliefStyle.NONE)
        more.connect("clicked", lambda *_: window.show_page("history"))
        head.pack_end(more, False, False, 0)
        outer.pack_start(head, False, False, 0)

        self.recent = Gtk.FlowBox()
        self.recent.set_selection_mode(Gtk.SelectionMode.NONE)
        self.recent.set_max_children_per_line(4)
        self.recent.set_min_children_per_line(2)
        self.recent.set_column_spacing(10)
        self.recent.set_row_spacing(10)
        self.recent.set_homogeneous(True)
        self.recent_empty = label("Suas capturas aparecerão aqui.", "dim-label", xalign=0.5)
        self.recent_empty.set_margin_top(12)
        self.recent_empty.set_no_show_all(True)
        outer.pack_start(self.recent, False, False, 0)
        outer.pack_start(self.recent_empty, False, False, 0)

        app.config.connect(self._on_config)
        app.history.connect(self.refresh_recent)
        app.recorder.connect("changed", lambda *_: self._update_recording())
        self.refresh_hotkeys()
        self.refresh_recent()

    def _tiles(self, tiles):
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_homogeneous(True)
        flow.set_min_children_per_line(3)
        flow.set_max_children_per_line(5)
        flow.set_column_spacing(10)
        flow.set_row_spacing(10)
        for action, title, icon, color in tiles:
            btn = Gtk.Button()
            btn.get_style_context().add_class("tile")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.set_margin_top(6)
            box.set_margin_bottom(4)
            box.pack_start(Icon(icon, 40, badge=color), False, False, 2)
            box.pack_start(label(title, "tile-title", xalign=0.5), False, False, 0)
            hk = label("", "dim-label tile-hotkey", xalign=0.5)
            self.hotkey_labels[action] = hk
            box.pack_start(hk, False, False, 0)
            btn.add(box)
            btn.connect("clicked", self._on_tile, action)
            flow.add(btn)
        return flow

    def _on_tile(self, _btn, action):
        if action == "open_folder":
            utils.open_folder(self.app.config["screenshots_dir"])
        else:
            self.app.trigger(action, from_window=True)

    def _recording_banner(self):
        rev = Gtk.Revealer()
        box = Gtk.Box(spacing=10)
        box.get_style_context().add_class("rec-banner")
        box.pack_start(Icon("record", 18, rgba=(1, 0.3, 0.3, 1)), False, False, 0)
        self.rec_label = label("Gravando…", "rec-banner-label")
        box.pack_start(self.rec_label, True, True, 0)
        self.rec_pause = Gtk.Button(label="Pausar")
        self.rec_pause.connect("clicked", lambda *_: self.app.recorder.toggle_pause())
        stop = Gtk.Button(label="Parar e salvar")
        stop.get_style_context().add_class("destructive-action")
        stop.connect("clicked", lambda *_: self.app.recorder.stop())
        box.pack_end(stop, False, False, 0)
        box.pack_end(self.rec_pause, False, False, 0)
        rev.add(box)
        return rev

    def _update_recording(self):
        rec = self.app.recorder
        self.rec_banner.set_reveal_child(rec.state in ("recording", "paused", "finishing"))
        texts = {"recording": "Gravando…", "paused": "Gravação pausada",
                 "finishing": "Finalizando a gravação…"}
        self.rec_label.set_text(texts.get(rec.state, ""))
        self.rec_pause.set_label("Continuar" if rec.state == "paused" else "Pausar")
        self.rec_pause.set_visible(rec.state in ("recording", "paused") and not rec.gst)

    def _on_config(self, key, _value):
        if key == "hotkeys":
            self.refresh_hotkeys()

    def refresh_hotkeys(self):
        hk = self.app.config["hotkeys"]
        for action, lbl in self.hotkey_labels.items():
            lbl.set_text(accel_label(hk.get(action, "")) or " ")

    def refresh_recent(self):
        for child in self.recent.get_children():
            child.destroy()
        items = self.app.history.items[:8]
        self.recent_empty.set_visible(not items)
        for entry in items:
            self.recent.add(RecentThumb(self.app, entry))
        self.recent.show_all()


class RecentThumb(Gtk.Button):
    W, H = 170, 106

    def __init__(self, app, entry):
        super().__init__()
        self.app = app
        self.entry = entry
        self.get_style_context().add_class("recent-thumb")
        self.set_tooltip_text(entry["path"])
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.image = Gtk.Image.new_from_icon_name(
            "video-x-generic-symbolic" if entry["kind"] == "video" else "image-x-generic-symbolic",
            Gtk.IconSize.DIALOG)
        self.image.set_size_request(self.W, self.H)
        box.pack_start(self.image, False, False, 0)
        box.pack_start(label(os.path.basename(entry["path"]), "recent-name", ellipsize=True),
                       False, False, 0)
        self.add(box)
        self.connect("clicked", lambda *_: app.open_entry(entry))
        app.thumbs.request(entry, self._set, (self.W * 2, self.H * 2))

    def _set(self, pixbuf):
        if pixbuf:
            self.image.set_from_pixbuf(cover(pixbuf, self.W, self.H))


def cover(pixbuf, w, h):
    """Redimensiona para caber inteiro em w×h, mantendo a proporção."""
    pw, ph = pixbuf.get_width(), pixbuf.get_height()
    scale = min(w / pw, h / ph)
    return pixbuf.scale_simple(max(1, int(pw * scale)), max(1, int(ph * scale)),
                               GdkPixbuf.InterpType.BILINEAR)
