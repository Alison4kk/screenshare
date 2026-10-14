"""Editor de imagem para anotar capturas."""
import copy
import math
import os

import cairo
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango, PangoCairo

from . import utils
from .capture import pixbuf_to_surface
from .icons import Icon

TOOLS = [
    ("select", "Selecionar / mover", "V"),
    ("arrow", "Seta", "A"),
    ("rect", "Retângulo", "R"),
    ("ellipse", "Elipse", "E"),
    ("line", "Linha", "L"),
    ("pen", "Caneta", "P"),
    ("highlight", "Marca-texto", "H"),
    ("text", "Texto", "T"),
    ("number", "Numeração", "N"),
    ("blur", "Desfocar", "B"),
    ("pixelate", "Pixelizar", "X"),
    ("crop", "Recortar", "C"),
]
TOOL_KEYS = {key.lower(): name for name, _label, key in TOOLS}
PALETTE = ["#ff3b30", "#ff9500", "#ffcc00", "#34c759", "#0a84ff", "#af52de", "#ffffff", "#1c1c1e"]
TWO_POINT = {"arrow", "rect", "ellipse", "line", "highlight", "blur", "pixelate", "crop"}
MARGIN = 24


# ------------------------------------------------------------- utilidades
def hex_rgb(value):
    value = value.lstrip("#")
    try:
        return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return 1.0, 0.23, 0.19


def rgba_hex(rgba):
    return "#%02x%02x%02x" % (int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255))


def is_light(rgb):
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b > 0.6


def norm_rect(p0, p1):
    x0, y0 = p0
    x1, y1 = p1
    return min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)


def font_size(width):
    return 10 + width * 3


def number_radius(width):
    return 10 + width * 2


_measure_ctx = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))


def text_layout(ctx, text, size):
    layout = PangoCairo.create_layout(ctx)
    desc = Pango.FontDescription.from_string("Sans Bold")
    desc.set_absolute_size(size * Pango.SCALE)
    layout.set_font_description(desc)
    layout.set_text(text, -1)
    return layout


def text_size(text, size):
    return text_layout(_measure_ctx, text, size).get_pixel_size()


# --------------------------------------------------------- desenho/efeitos
def apply_effect(ctx, source, rect, kind, strength):
    sw_total, sh_total = source.get_width(), source.get_height()
    x, y, w, h = (int(round(v)) for v in rect)
    x2, y2 = min(sw_total, x + w), min(sh_total, y + h)
    x, y = max(0, x), max(0, y)
    w, h = x2 - x, y2 - y
    if w < 2 or h < 2:
        return
    block = max(4, strength * 3) if kind == "pixelate" else max(3, strength * 2)
    sw, sh = max(1, w // block), max(1, h // block)
    small = cairo.ImageSurface(cairo.FORMAT_ARGB32, sw, sh)
    sc = cairo.Context(small)
    sc.scale(sw / w, sh / h)
    sc.set_source_surface(source, -x, -y)
    sc.get_source().set_filter(cairo.FILTER_GOOD)
    sc.paint()
    ctx.save()
    ctx.rectangle(x, y, w, h)
    ctx.clip()
    ctx.translate(x, y)
    ctx.scale(w / sw, h / sh)
    ctx.set_source_surface(small, 0, 0)
    pattern = ctx.get_source()
    pattern.set_extend(cairo.EXTEND_PAD)
    pattern.set_filter(cairo.FILTER_NEAREST if kind == "pixelate" else cairo.FILTER_BILINEAR)
    ctx.paint()
    ctx.restore()


def draw_arrow(ctx, x0, y0, x1, y1, width):
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1:
        return
    ang = math.atan2(y1 - y0, x1 - x0)
    head = max(12, width * 3.6)
    half = head * 0.58
    bx, by = x1 - head * math.cos(ang), y1 - head * math.sin(ang)
    ctx.set_line_width(width)
    ctx.move_to(x0, y0)
    ctx.line_to(x1 - head * 0.6 * math.cos(ang), y1 - head * 0.6 * math.sin(ang))
    ctx.stroke()
    ctx.move_to(x1, y1)
    ctx.line_to(bx + half * math.sin(ang), by - half * math.cos(ang))
    ctx.line_to(bx - half * math.sin(ang), by + half * math.cos(ang))
    ctx.close_path()
    ctx.fill()


def draw_annotation(ctx, source, a):
    tool = a["tool"]
    rgb = hex_rgb(a["color"])
    width = a["width"]
    pts = a["pts"]
    ctx.save()
    ctx.new_path()
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_source_rgb(*rgb)
    if tool in TWO_POINT:
        (x0, y0), (x1, y1) = pts[0], pts[-1]
        x, y, w, h = norm_rect(pts[0], pts[-1])
    if tool == "rect":
        ctx.set_line_width(width)
        ctx.rectangle(x, y, w, h)
        ctx.stroke()
    elif tool == "ellipse":
        if w >= 1 and h >= 1:
            ctx.save()
            ctx.translate(x + w / 2, y + h / 2)
            ctx.scale(w / 2, h / 2)
            ctx.arc(0, 0, 1, 0, 2 * math.pi)
            ctx.restore()
            ctx.set_line_width(width)
            ctx.stroke()
    elif tool == "line":
        ctx.set_line_width(width)
        ctx.move_to(x0, y0)
        ctx.line_to(x1, y1)
        ctx.stroke()
    elif tool == "arrow":
        draw_arrow(ctx, x0, y0, x1, y1, width)
    elif tool == "pen":
        ctx.set_line_width(width)
        if len(pts) == 1:
            ctx.arc(pts[0][0], pts[0][1], width / 2, 0, 2 * math.pi)
            ctx.fill()
        else:
            ctx.move_to(*pts[0])
            for i in range(1, len(pts) - 1):
                mx = (pts[i][0] + pts[i + 1][0]) / 2
                my = (pts[i][1] + pts[i + 1][1]) / 2
                ctx.curve_to(pts[i][0], pts[i][1], pts[i][0], pts[i][1], mx, my)
            ctx.line_to(*pts[-1])
            ctx.stroke()
    elif tool == "highlight":
        # multiplicar dá o efeito de marca-texto em fundos claros; a camada
        # translúcida por cima garante que apareça também em fundos escuros
        ctx.set_operator(cairo.OPERATOR_MULTIPLY)
        ctx.rectangle(x, y, w, h)
        ctx.fill()
        ctx.set_operator(cairo.OPERATOR_OVER)
        ctx.set_source_rgba(*rgb, 0.22)
        ctx.rectangle(x, y, w, h)
        ctx.fill()
    elif tool == "text":
        size = font_size(width)
        layout = text_layout(ctx, a.get("text", ""), size)
        ctx.move_to(*pts[0])
        PangoCairo.layout_path(ctx, layout)
        outline = (0.08, 0.08, 0.08, 0.9) if is_light(rgb) else (1, 1, 1, 0.95)
        ctx.set_source_rgba(*outline)
        ctx.set_line_width(max(2.5, size / 7))
        ctx.stroke()
        ctx.move_to(*pts[0])
        ctx.set_source_rgb(*rgb)
        PangoCairo.show_layout(ctx, layout)
        ctx.new_path()
    elif tool == "number":
        cx, cy = pts[0]
        r = number_radius(width)
        ctx.arc(cx, cy, r, 0, 2 * math.pi)
        ctx.fill_preserve()
        ctx.set_source_rgba(*((0, 0, 0, 0.5) if is_light(rgb) else (1, 1, 1, 0.9)))
        ctx.set_line_width(max(1.5, r / 9))
        ctx.stroke()
        layout = text_layout(ctx, str(a.get("num", 1)), r * 1.15)
        tw, th = layout.get_pixel_size()
        ctx.move_to(cx - tw / 2, cy - th / 2)
        ctx.set_source_rgb(*((0.1, 0.1, 0.1) if is_light(rgb) else (1, 1, 1)))
        PangoCairo.show_layout(ctx, layout)
        ctx.new_path()
    elif tool in ("blur", "pixelate"):
        apply_effect(ctx, source, (x, y, w, h), tool, width)
    ctx.restore()


def bbox(a):
    tool, pts, width = a["tool"], a["pts"], a["width"]
    if tool == "text":
        tw, th = text_size(a.get("text", ""), font_size(width))
        return pts[0][0], pts[0][1], tw, th
    if tool == "number":
        r = number_radius(width)
        return pts[0][0] - r, pts[0][1] - r, 2 * r, 2 * r
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    pad = width / 2 + (width * 3.6 if tool == "arrow" else 0) / 2
    return min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad


# ------------------------------------------------------------------ janela
class ImageEditor(Gtk.ApplicationWindow):
    """Editor. Modo captura: `on_done(pixbuf)` ao concluir. Modo arquivo: salva em `path`."""

    def __init__(self, app, pixbuf, path=None, entry=None, on_done=None, on_cancel=None):
        super().__init__(application=app)
        self.app = app
        self.cfg = app.config
        self.path = path
        self.entry = entry
        self.on_done = on_done
        self.on_cancel = on_cancel
        self.capture_mode = on_done is not None
        self.base = pixbuf_to_surface(pixbuf)
        self.has_alpha = pixbuf.get_has_alpha()
        self.img_w, self.img_h = pixbuf.get_width(), pixbuf.get_height()

        self.annos = []
        self.crop = None
        self.undo_stack, self.redo_stack = [], []
        self.cache = None
        self.drag = None
        self.sel = None
        self.moving = None
        self.zoom = None  # None = ajustar à janela
        self.dirty = False
        self.tool = "arrow"
        self.prev_tool = "arrow"
        self.color = self.cfg["editor_color"]
        self.hl_color = "#ffd60a"  # o marca-texto tem cor própria
        self.width = int(self.cfg["editor_width"])
        self._text_popover = None
        self._closing = False

        self._build()
        self._update_title()
        self._update_history_buttons()
        display = Gdk.Display.get_default()
        _s, px, py = display.get_default_seat().get_pointer().get_position()
        area = display.get_monitor_at_point(px, py).get_workarea()
        sw = min(max(self.img_w + 2 * MARGIN + 20, 860), int(area.width * 0.9))
        sh = min(max(self.img_h + 2 * MARGIN + 150, 600), int(area.height * 0.9))
        self.set_default_size(sw, sh)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", self._on_delete)
        self.connect("key-press-event", self._on_key)
        self.show_all()
        self.present()

    @classmethod
    def open_file(cls, app, entry):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(entry["path"])
        except GLib.Error as e:
            app.show_error("Não foi possível abrir a imagem", e.message)
            return None
        return cls(app, pixbuf, path=entry["path"], entry=entry)

    # ----------------------------------------------------------------- UI
    def _build(self):
        header = Gtk.HeaderBar(show_close_button=True)
        self.set_titlebar(header)
        self.header = header

        self.undo_btn = self._icon_button("edit-undo-symbolic", "Desfazer (Ctrl+Z)", self.do_undo)
        self.redo_btn = self._icon_button("edit-redo-symbolic", "Refazer (Ctrl+Y)", self.do_redo)
        hist = Gtk.Box(spacing=0)
        hist.get_style_context().add_class("linked")
        hist.pack_start(self.undo_btn, False, False, 0)
        hist.pack_start(self.redo_btn, False, False, 0)
        header.pack_start(hist)

        if self.capture_mode:
            done = Gtk.Button(label="Concluir")
            done.set_tooltip_text("Salvar/copiar conforme as configurações (Ctrl+Enter)")
            done.get_style_context().add_class("suggested-action")
            done.connect("clicked", lambda *_: self.finish())
            header.pack_end(done)
            cancel = Gtk.Button(label="Descartar")
            cancel.connect("clicked", lambda *_: self.discard())
            header.pack_end(cancel)
        else:
            save = Gtk.Button(label="Salvar")
            save.set_tooltip_text("Salvar por cima do arquivo (Ctrl+S)")
            save.get_style_context().add_class("suggested-action")
            save.connect("clicked", lambda *_: self.save())
            header.pack_end(save)
            header.pack_end(self._icon_button("document-save-as-symbolic", "Salvar como… (Ctrl+Shift+S)",
                                              self.save_as))
        header.pack_end(self._icon_button("edit-copy-symbolic", "Copiar imagem (Ctrl+C)", self.copy))

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        bar = Gtk.Box(spacing=4)
        bar.get_style_context().add_class("editor-toolbar")
        bar.set_border_width(6)
        root.pack_start(bar, False, False, 0)

        self.tool_buttons = {}
        group = None
        for name, label, key in TOOLS:
            btn = Gtk.RadioButton.new_from_widget(group)
            group = group or btn
            btn.set_mode(False)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.add(Icon(name, 18))
            btn.set_tooltip_text(f"{label} ({key})")
            btn.get_style_context().add_class("tool-button")
            btn.connect("toggled", self._on_tool_toggled, name)
            bar.pack_start(btn, False, False, 0)
            self.tool_buttons[name] = btn
            if name in ("select", "highlight", "number", "pixelate"):
                bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        self.swatches = []
        for col in PALETTE:
            sw = Gtk.Button()
            sw.set_relief(Gtk.ReliefStyle.NONE)
            sw.get_style_context().add_class("swatch-button")
            da = Gtk.DrawingArea()
            da.set_size_request(18, 18)
            da.connect("draw", self._draw_swatch, col)
            sw.add(da)
            sw.set_tooltip_text(col)
            sw.connect("clicked", lambda _b, c=col: self.set_color(c))
            bar.pack_start(sw, False, False, 0)
            self.swatches.append(da)
        self.color_btn = Gtk.ColorButton()
        self.color_btn.set_tooltip_text("Outra cor")
        rgba = Gdk.RGBA()
        rgba.parse(self.color)
        self.color_btn.set_rgba(rgba)
        self.color_btn.connect("color-set", lambda b: self.set_color(rgba_hex(b.get_rgba())))
        bar.pack_start(self.color_btn, False, False, 2)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)
        lbl = Gtk.Label(label="Espessura")
        lbl.get_style_context().add_class("dim-label")
        bar.pack_start(lbl, False, False, 2)
        self.width_spin = Gtk.SpinButton.new_with_range(1, 30, 1)
        self.width_spin.set_value(self.width)
        self.width_spin.set_tooltip_text("Espessura / tamanho / intensidade")
        self.width_spin.connect("value-changed", lambda s: self.set_width(int(s.get_value())))
        bar.pack_start(self.width_spin, False, False, 0)

        zoom_box = Gtk.Box()
        zoom_box.get_style_context().add_class("linked")
        zoom_box.pack_start(self._icon_button("zoom-out-symbolic", "Diminuir zoom (Ctrl+-)",
                                              lambda: self.zoom_by(1 / 1.25)), False, False, 0)
        self.zoom_label = Gtk.Button(label="Ajustar")
        self.zoom_label.set_tooltip_text("Alternar entre ajustar à janela e 100% (Ctrl+0)")
        self.zoom_label.connect("clicked", lambda *_: self.toggle_fit())
        zoom_box.pack_start(self.zoom_label, False, False, 0)
        zoom_box.pack_start(self._icon_button("zoom-in-symbolic", "Aumentar zoom (Ctrl++)",
                                              lambda: self.zoom_by(1.25)), False, False, 0)
        bar.pack_end(zoom_box, False, False, 0)

        self.scroller = Gtk.ScrolledWindow()
        self.scroller.get_style_context().add_class("editor-canvas")
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_can_focus(True)
        self.canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                               | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK
                               | Gdk.EventMask.SMOOTH_SCROLL_MASK)
        self.canvas.connect("draw", self._on_draw)
        self.canvas.connect("button-press-event", self._on_press)
        self.canvas.connect("button-release-event", self._on_release)
        self.canvas.connect("motion-notify-event", self._on_motion)
        self.canvas.connect("scroll-event", self._on_scroll)
        self.canvas.connect("size-allocate", lambda *_: GLib.idle_add(self._update_zoom_label))
        self.scroller.add(self.canvas)
        root.pack_start(self.scroller, True, True, 0)

        status = Gtk.Box(spacing=12)
        status.set_border_width(4)
        status.get_style_context().add_class("editor-status")
        self.status_size = Gtk.Label(xalign=0)
        self.status_hint = Gtk.Label(xalign=1)
        self.status_hint.get_style_context().add_class("dim-label")
        self.status_hint.set_ellipsize(Pango.EllipsizeMode.START)
        status.pack_start(self.status_size, False, False, 6)
        status.pack_end(self.status_hint, True, True, 6)
        root.pack_start(status, False, False, 0)

        self.tool_buttons[self.tool].set_active(True)
        self._update_status()

    def _icon_button(self, icon, tip, cb):
        btn = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
        btn.set_tooltip_text(tip)
        btn.connect("clicked", lambda *_: cb())
        return btn

    def _draw_swatch(self, widget, ctx, col):
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        r = min(w, h) / 2 - 1
        ctx.arc(w / 2, h / 2, r, 0, 2 * math.pi)
        ctx.set_source_rgb(*hex_rgb(col))
        ctx.fill_preserve()
        ctx.set_line_width(1)
        ctx.set_source_rgba(0.5, 0.5, 0.5, 0.6)
        ctx.stroke()
        if col.lower() == self._current_color().lower():
            ctx.arc(w / 2, h / 2, r * 0.38, 0, 2 * math.pi)
            ctx.set_source_rgb(*((0, 0, 0) if is_light(hex_rgb(col)) else (1, 1, 1)))
            ctx.fill()

    def _update_title(self):
        name = os.path.basename(self.path) if self.path else "Nova captura"
        self.header.set_title(("• " if self.dirty and not self.capture_mode else "") + name)
        self.header.set_subtitle("Editor de imagem")

    def _update_history_buttons(self):
        self.undo_btn.set_sensitive(bool(self.undo_stack))
        self.redo_btn.set_sensitive(bool(self.redo_stack))

    def _update_status(self):
        _x, _y, w, h = self._view_rect()
        self.status_size.set_text(f"{w} × {h} px")
        hints = {
            "select": "Clique para selecionar, arraste para mover, Delete apaga",
            "text": "Clique onde o texto deve começar",
            "number": "Clique para inserir o próximo número",
            "crop": "Arraste para definir a área de recorte",
            "pen": "Arraste para desenhar à mão livre",
        }
        default = "Arraste para desenhar  •  Shift mantém proporção/ângulo"
        self.status_hint.set_text(hints.get(self.tool, default))

    def _update_zoom_label(self):
        z, _ox, _oy = self._view_params()
        self.zoom_label.set_label(("Ajustar · " if self.zoom is None else "") + f"{round(z * 100)}%")
        return False

    # ------------------------------------------------------------- estado
    def _snapshot(self):
        return copy.deepcopy(self.annos), self.crop

    def push_undo(self):
        self.undo_stack.append(self._snapshot())
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self._mark_dirty()

    def _mark_dirty(self):
        self.dirty = True
        self.cache = None
        self._update_title()
        self._update_history_buttons()

    def do_undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self._snapshot())
        self.annos, self.crop = self.undo_stack.pop()
        self._after_restore()

    def do_redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self._snapshot())
        self.annos, self.crop = self.redo_stack.pop()
        self._after_restore()

    def _after_restore(self):
        self.sel = None
        self._mark_dirty()
        self._apply_zoom()
        self._update_status()

    def _current_color(self):
        return self.hl_color if self.tool == "highlight" else self.color

    def set_color(self, col, apply_selected=True):
        if self.tool == "highlight":
            self.hl_color = col
        else:
            self.color = col
            self.cfg.set("editor_color", col)
        rgba = Gdk.RGBA()
        rgba.parse(col)
        self.color_btn.set_rgba(rgba)
        for da in self.swatches:
            da.queue_draw()
        if self.sel is not None and apply_selected:
            self.push_undo()
            self.annos[self.sel]["color"] = col
            self.canvas.queue_draw()

    def set_width(self, width):
        if width == self.width:
            return
        self.width = width
        self.cfg.set("editor_width", width)
        if self.sel is not None:
            self.push_undo()
            self.annos[self.sel]["width"] = width
            self.canvas.queue_draw()

    def set_tool(self, name):
        self.tool_buttons[name].set_active(True)

    def _on_tool_toggled(self, btn, name):
        if not btn.get_active():
            return
        if name != "crop":
            self.prev_tool = name
        was_hl = self.tool == "highlight"
        self.tool = name
        if was_hl != (name == "highlight"):
            self.set_color(self._current_color(), apply_selected=False)
        if name != "select":
            self.sel = None
        self.drag = None
        self._update_status()
        self.canvas.queue_draw()
        win = self.canvas.get_window()
        if win:
            cursor_name = "default" if name == "select" else ("text" if name == "text" else "crosshair")
            win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), cursor_name))

    # --------------------------------------------------------------- zoom
    def _view_rect(self):
        return self.crop or (0, 0, self.img_w, self.img_h)

    def _view_params(self):
        _x, _y, vw, vh = self._view_rect()
        aw = self.canvas.get_allocated_width()
        ah = self.canvas.get_allocated_height()
        if self.zoom is None:
            z = min((aw - 2 * MARGIN) / max(1, vw), (ah - 2 * MARGIN) / max(1, vh), 1.0)
            z = max(z, 0.02)
        else:
            z = self.zoom
        ox = max(MARGIN, (aw - vw * z) / 2)
        oy = max(MARGIN, (ah - vh * z) / 2)
        return z, ox, oy

    def _apply_zoom(self):
        if self.zoom is None:
            self.canvas.set_size_request(-1, -1)
        else:
            _x, _y, vw, vh = self._view_rect()
            self.canvas.set_size_request(int(vw * self.zoom + 2 * MARGIN), int(vh * self.zoom + 2 * MARGIN))
        self.canvas.queue_resize()
        self.canvas.queue_draw()
        self._update_zoom_label()

    def zoom_by(self, factor):
        z, _ox, _oy = self._view_params()
        self.zoom = max(0.05, min(8.0, z * factor))
        self._apply_zoom()

    def toggle_fit(self):
        self.zoom = 1.0 if self.zoom is None else None
        self._apply_zoom()

    def _to_image(self, wx, wy):
        z, ox, oy = self._view_params()
        vx, vy, _vw, _vh = self._view_rect()
        return (wx - ox) / z + vx, (wy - oy) / z + vy

    # ----------------------------------------------------------- renderização
    def _committed(self):
        if self.cache is None:
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.img_w, self.img_h)
            ctx = cairo.Context(surf)
            ctx.set_source_surface(self.base, 0, 0)
            ctx.paint()
            for a in self.annos:
                draw_annotation(ctx, surf, a)
            surf.flush()
            self.cache = surf
        return self.cache

    def _on_draw(self, _w, ctx):
        z, ox, oy = self._view_params()
        vx, vy, vw, vh = self._view_rect()
        # sombra/borda da "folha"
        ctx.rectangle(ox - 1, oy - 1, vw * z + 2, vh * z + 2)
        ctx.set_source_rgba(0, 0, 0, 0.35)
        ctx.fill()
        if self.has_alpha:
            self._draw_checker(ctx, ox, oy, vw * z, vh * z)

        ctx.save()
        ctx.translate(ox, oy)
        ctx.scale(z, z)
        ctx.translate(-vx, -vy)
        ctx.rectangle(vx, vy, vw, vh)
        ctx.clip()
        src = self._committed()
        ctx.set_source_surface(src, 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_NEAREST if z >= 2 else cairo.FILTER_GOOD)
        ctx.paint()
        if self.drag and self.drag["tool"] != "crop":
            draw_annotation(ctx, src, self.drag)
        if self.sel is not None and self.sel < len(self.annos):
            bx, by, bw, bh = bbox(self.annos[self.sel])
            ctx.set_line_width(1.5 / z)
            ctx.set_dash([5 / z, 4 / z])
            ctx.set_source_rgb(0.24, 0.62, 1.0)
            ctx.rectangle(bx - 4 / z, by - 4 / z, bw + 8 / z, bh + 8 / z)
            ctx.stroke()
        ctx.restore()

        if self.drag and self.drag["tool"] == "crop":
            cx, cy, cw, ch = norm_rect(*self.drag["pts"])
            sx, sy = ox + (cx - vx) * z, oy + (cy - vy) * z
            ctx.save()
            ctx.rectangle(ox, oy, vw * z, vh * z)
            ctx.rectangle(sx, sy, cw * z, ch * z)
            ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            ctx.set_source_rgba(0, 0, 0, 0.55)
            ctx.fill()
            ctx.set_source_rgb(1, 1, 1)
            ctx.set_line_width(1.5)
            ctx.set_dash([6, 4])
            ctx.rectangle(sx, sy, cw * z, ch * z)
            ctx.stroke()
            ctx.restore()

    def _draw_checker(self, ctx, x, y, w, h):
        ctx.save()
        ctx.rectangle(x, y, w, h)
        ctx.clip()
        size = 10
        ctx.set_source_rgb(0.85, 0.85, 0.85)
        ctx.paint()
        ctx.set_source_rgb(0.7, 0.7, 0.7)
        for i in range(int(w // size) + 1):
            for j in range(int(h // size) + 1):
                if (i + j) % 2:
                    ctx.rectangle(x + i * size, y + j * size, size, size)
        ctx.fill()
        ctx.restore()

    # ---------------------------------------------------------- interação
    def _constrain(self, p0, p1, shift):
        if not shift:
            return p1
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        if self.tool in ("line", "arrow"):
            ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
            length = math.hypot(dx, dy)
            return [p0[0] + length * math.cos(ang), p0[1] + length * math.sin(ang)]
        side = max(abs(dx), abs(dy))
        return [p0[0] + math.copysign(side, dx or 1), p0[1] + math.copysign(side, dy or 1)]

    def _hit(self, x, y):
        z, _ox, _oy = self._view_params()
        tol = 6 / z
        for i in range(len(self.annos) - 1, -1, -1):
            bx, by, bw, bh = bbox(self.annos[i])
            if bx - tol <= x <= bx + bw + tol and by - tol <= y <= by + bh + tol:
                return i
        return None

    def _on_press(self, _w, event):
        self.canvas.grab_focus()
        if event.button != 1:
            return False
        x, y = self._to_image(event.x, event.y)
        p = [x, y]
        tool = self.tool
        if tool == "select":
            self.sel = self._hit(x, y)
            self.moving = {"last": p, "moved": False} if self.sel is not None else None
            self.canvas.queue_draw()
            return True
        if tool == "text":
            self._ask_text(event.x, event.y, p)
            return True
        if tool == "number":
            num = 1 + sum(1 for a in self.annos if a["tool"] == "number")
            self.push_undo()
            self.annos.append({"tool": "number", "pts": [p], "color": self._current_color(),
                               "width": self.width, "num": num})
            self.canvas.queue_draw()
            return True
        self.drag = {"tool": tool, "pts": [p, list(p)] if tool in TWO_POINT else [p],
                     "color": self._current_color(), "width": self.width}
        self.canvas.queue_draw()
        return True

    def _on_motion(self, _w, event):
        x, y = self._to_image(event.x, event.y)
        if self.moving and self.sel is not None and event.state & Gdk.ModifierType.BUTTON1_MASK:
            lx, ly = self.moving["last"]
            dx, dy = x - lx, y - ly
            if not self.moving["moved"]:
                self.push_undo()
                self.moving["moved"] = True
            for pt in self.annos[self.sel]["pts"]:
                pt[0] += dx
                pt[1] += dy
            self.moving["last"] = [x, y]
            self.cache = None
            self.canvas.queue_draw()
            return True
        if not self.drag:
            return False
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        if self.drag["tool"] == "pen":
            last = self.drag["pts"][-1]
            if math.hypot(x - last[0], y - last[1]) >= 1.5:
                self.drag["pts"].append([x, y])
        else:
            self.drag["pts"][1] = self._constrain(self.drag["pts"][0], [x, y],
                                                  shift and self.drag["tool"] != "crop")
        self.canvas.queue_draw()
        return True

    def _on_release(self, _w, event):
        if event.button != 1:
            return False
        if self.moving:
            self.moving = None
            return True
        drag, self.drag = self.drag, None
        if not drag:
            return True
        if drag["tool"] == "crop":
            x, y, w, h = norm_rect(*drag["pts"])
            vx, vy, vw, vh = self._view_rect()
            x1, y1 = max(vx, int(x)), max(vy, int(y))
            x2, y2 = min(vx + vw, int(math.ceil(x + w))), min(vy + vh, int(math.ceil(y + h)))
            if x2 - x1 >= 4 and y2 - y1 >= 4:
                self.push_undo()
                self.crop = (x1, y1, x2 - x1, y2 - y1)
                self._apply_zoom()
            self.set_tool(self.prev_tool)
            self._update_status()
            return True
        if drag["tool"] in TWO_POINT:
            (x0, y0), (x1, y1) = drag["pts"]
            if math.hypot(x1 - x0, y1 - y0) < 3:
                self.canvas.queue_draw()
                return True
        self.push_undo()
        self.annos.append(drag)
        self.canvas.queue_draw()
        return True

    def _on_scroll(self, _w, event):
        if not event.state & Gdk.ModifierType.CONTROL_MASK:
            return False
        ok, _dx, dy = event.get_scroll_deltas()
        if event.direction == Gdk.ScrollDirection.UP or (ok and dy < 0):
            self.zoom_by(1.1)
        elif event.direction == Gdk.ScrollDirection.DOWN or (ok and dy > 0):
            self.zoom_by(1 / 1.1)
        return True

    def _ask_text(self, wx, wy, p):
        pop = Gtk.Popover.new(self.canvas)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(wx), int(wy), 1, 1
        pop.set_pointing_to(rect)
        box = Gtk.Box(spacing=6)
        box.set_border_width(8)
        entry = Gtk.Entry()
        entry.set_placeholder_text("Digite o texto e Enter")
        entry.set_width_chars(28)
        ok = Gtk.Button(label="Inserir")
        ok.get_style_context().add_class("suggested-action")
        box.pack_start(entry, True, True, 0)
        box.pack_start(ok, False, False, 0)
        pop.add(box)

        def commit(*_):
            text = entry.get_text().strip()
            pop.popdown()
            if text:
                self.push_undo()
                self.annos.append({"tool": "text", "pts": [p], "color": self._current_color(),
                                   "width": self.width, "text": text})
                self.canvas.queue_draw()

        entry.connect("activate", commit)
        ok.connect("clicked", commit)
        pop.connect("closed", lambda *_: setattr(self, "_text_popover", None))
        self._text_popover = pop
        pop.show_all()
        pop.popup()
        entry.grab_focus()

    def _on_key(self, _w, event):
        if self._text_popover:
            return False
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        shift = event.state & Gdk.ModifierType.SHIFT_MASK
        key = Gdk.keyval_to_lower(event.keyval)
        if ctrl:
            if key == Gdk.KEY_z and not shift:
                self.do_undo()
            elif key == Gdk.KEY_y or (key == Gdk.KEY_z and shift):
                self.do_redo()
            elif key == Gdk.KEY_c:
                self.copy()
            elif key == Gdk.KEY_w:
                self.close()
            elif key == Gdk.KEY_s:
                if self.capture_mode:
                    self.finish()
                elif shift:
                    self.save_as()
                else:
                    self.save()
            elif key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.capture_mode:
                self.finish()
            elif key in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
                self.zoom_by(1.25)
            elif key in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
                self.zoom_by(1 / 1.25)
            elif key == Gdk.KEY_0:
                self.zoom = None
                self._apply_zoom()
            elif key == Gdk.KEY_1:
                self.zoom = 1.0
                self._apply_zoom()
            else:
                return False
            return True
        if key in (Gdk.KEY_Delete, Gdk.KEY_BackSpace) and self.sel is not None:
            self.push_undo()
            del self.annos[self.sel]
            self.sel = None
            self.canvas.queue_draw()
            return True
        if key == Gdk.KEY_Escape:
            if self.drag:
                self.drag = None
            elif self.sel is not None:
                self.sel = None
            self.canvas.queue_draw()
            return True
        if not event.state & (Gdk.ModifierType.MOD1_MASK | Gdk.ModifierType.SUPER_MASK):
            name = TOOL_KEYS.get(Gdk.keyval_name(key) or "")
            if name:
                self.set_tool(name)
                return True
        return False

    # ------------------------------------------------------------ resultado
    def result_pixbuf(self):
        src = self._committed()
        x, y, w, h = self._view_rect()
        fmt = cairo.FORMAT_ARGB32 if self.has_alpha else cairo.FORMAT_RGB24
        out = cairo.ImageSurface(fmt, w, h)
        ctx = cairo.Context(out)
        ctx.set_source_surface(src, -x, -y)
        ctx.paint()
        out.flush()
        return Gdk.pixbuf_get_from_surface(out, 0, 0, w, h)

    def copy(self):
        utils.copy_image(self.result_pixbuf())
        self.status_hint.set_text("Imagem copiada para a área de transferência")

    def finish(self):
        pixbuf = self.result_pixbuf()
        self._closing = True
        self.destroy()
        self.on_done(pixbuf)

    def discard(self):
        self._closing = True
        self.destroy()
        if self.on_cancel:
            self.on_cancel()

    def save(self, path=None):
        path = path or self.path
        if not path:
            return self.save_as()
        ext = os.path.splitext(path)[1].lower().lstrip(".") or "png"
        fmt = {"jpg": "jpeg", "jpeg": "jpeg", "webp": "webp", "bmp": "bmp"}.get(ext, "png")
        pixbuf = self.result_pixbuf()
        try:
            utils.save_pixbuf(pixbuf, path, fmt, self.cfg["jpeg_quality"])
        except GLib.Error as e:
            self.app.show_error("Não foi possível salvar", e.message)
            return False
        if self.entry and path == self.entry["path"]:
            self.app.history.update(self.entry, width=pixbuf.get_width(), height=pixbuf.get_height())
        elif path != self.path:
            self.entry = self.app.history.add(path, "image", pixbuf.get_width(), pixbuf.get_height())
        self.path = path
        self.dirty = False
        self._update_title()
        self.status_hint.set_text("Salvo: " + os.path.basename(path))
        return True

    def save_as(self):
        dialog = Gtk.FileChooserDialog(title="Salvar imagem como", transient_for=self,
                                       action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Salvar", Gtk.ResponseType.ACCEPT)
        dialog.set_do_overwrite_confirmation(True)
        if self.path:
            dialog.set_current_folder(os.path.dirname(self.path))
            base = os.path.splitext(os.path.basename(self.path))[0]
            dialog.set_current_name(base + "_editado.png")
        else:
            dialog.set_current_folder(os.path.expanduser(self.cfg["screenshots_dir"]))
            dialog.set_current_name(utils.safe_strftime(self.cfg["filename_pattern"]) + ".png")
        for name, pattern in (("PNG", "*.png"), ("JPEG", "*.jpg"), ("WebP", "*.webp")):
            f = Gtk.FileFilter()
            f.set_name(name)
            f.add_pattern(pattern)
            dialog.add_filter(f)
        ok = dialog.run() == Gtk.ResponseType.ACCEPT
        path = dialog.get_filename()
        dialog.destroy()
        if ok and path:
            if not os.path.splitext(path)[1]:
                path += ".png"
            return self.save(path)
        return False

    def _on_delete(self, *_):
        if self._closing:
            return False
        if self.capture_mode:
            if self.annos and not self._confirm("Descartar esta captura?",
                                                "As anotações e a captura serão perdidas.",
                                                "Descartar"):
                return True
            if self.on_cancel:
                self.on_cancel()
            return False
        if not self.dirty:
            return False
        dialog = Gtk.MessageDialog(transient_for=self, modal=True,
                                   message_type=Gtk.MessageType.QUESTION,
                                   text="Salvar as alterações?")
        dialog.format_secondary_text("Se não salvar, as alterações serão perdidas.")
        dialog.add_buttons("Descartar", Gtk.ResponseType.NO, "Cancelar", Gtk.ResponseType.CANCEL,
                           "Salvar", Gtk.ResponseType.YES)
        dialog.set_default_response(Gtk.ResponseType.YES)
        resp = dialog.run()
        dialog.destroy()
        if resp == Gtk.ResponseType.YES:
            return not self.save()
        return resp != Gtk.ResponseType.NO

    def _confirm(self, title, text, action):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True,
                                   message_type=Gtk.MessageType.QUESTION, text=title)
        dialog.format_secondary_text(text)
        dialog.add_buttons("Voltar", Gtk.ResponseType.CANCEL, action, Gtk.ResponseType.OK)
        resp = dialog.run()
        dialog.destroy()
        return resp == Gtk.ResponseType.OK
