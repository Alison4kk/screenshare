"""Sobreposição em tela cheia para selecionar uma região (estilo ShareX)."""
import cairo
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo

from .icons import rounded_rect

ACCENT = (0.24, 0.62, 1.0)
REC_ACCENT = (1.0, 0.27, 0.27)
MAG_PIXELS = 15  # pixels visíveis na lupa (ímpar)
MAG_ZOOM = 8


class RegionSelector(Gtk.Window):
    """Mostra a imagem congelada `shot` e devolve o retângulo escolhido em pixels.

    on_done(rect) é chamado com (x, y, w, h) ou None se cancelado.
    """

    def __init__(self, shot, on_done, recording=False, magnifier=True, crosshair=True,
                 detect_windows=True):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.shot = shot
        self.on_done = on_done
        self.recording = recording
        self.magnifier = magnifier
        self.crosshair = crosshair
        self.windows = shot.windows if detect_windows else []
        self.scale = shot.scale or 1.0
        self.accent = REC_ACCENT if recording else ACCENT

        self.start = None
        self.pressed = False
        self.dragging = False
        self.cur = shot.pointer
        self.hover = None
        self._finished = False

        self._build_surfaces()

        root = Gdk.get_default_root_window()
        self.set_app_paintable(True)
        self.move(0, 0)
        self.set_default_size(root.get_width(), root.get_height())
        self.resize(root.get_width(), root.get_height())
        self.set_keep_above(True)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("draw", self._on_draw)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("button-press-event", self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("key-press-event", self._on_key)
        self.connect("map-event", lambda *_: self._grab(0))
        self._update_hover()

    # --------------------------------------------------------------- setup
    def _build_surfaces(self):
        pb = self.shot.pixbuf
        w, h = pb.get_width(), pb.get_height()
        self.img = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
        ctx = cairo.Context(self.img)
        Gdk.cairo_set_source_pixbuf(ctx, pb, 0, 0)
        ctx.paint()
        self.dim = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
        ctx = cairo.Context(self.dim)
        ctx.set_source_surface(self.img, 0, 0)
        ctx.paint()
        ctx.set_source_rgba(0, 0, 0, 0.45)
        ctx.paint()
        self.pixels = pb.get_pixels()
        self.rowstride = pb.get_rowstride()
        self.nch = pb.get_n_channels()

    def _grab(self, attempt):
        if self._finished:
            return False
        win = self.get_window()
        if not win:
            return False
        display = Gdk.Display.get_default()
        cursor = Gdk.Cursor.new_from_name(display, "crosshair")
        win.set_cursor(cursor)
        status = display.get_default_seat().grab(win, Gdk.SeatCapabilities.ALL, True, cursor,
                                                 None, None, None)
        if status != Gdk.GrabStatus.SUCCESS and attempt < 30:
            GLib.timeout_add(50, self._grab, attempt + 1)
        self.present()
        return False

    # --------------------------------------------------------------- eventos
    def _pos(self, event):
        return int(event.x * self.scale), int(event.y * self.scale)

    def _on_motion(self, _w, event):
        self.cur = self._pos(event)
        if self.pressed and not self.dragging and self.start:
            if abs(self.cur[0] - self.start[0]) > 3 or abs(self.cur[1] - self.start[1]) > 3:
                self.dragging = True
        if not self.dragging:
            self._update_hover()
        self.queue_draw()
        return True

    def _on_press(self, _w, event):
        if event.button == 3:
            if self.dragging:  # botão direito durante o arraste: recomeça
                self.pressed = self.dragging = False
                self.start = None
                self.queue_draw()
            else:
                self._finish(None)
            return True
        if event.button == 1:
            self.cur = self._pos(event)
            self.start = self.cur
            self.pressed = True
        return True

    def _on_release(self, _w, event):
        if event.button != 1 or not self.pressed:
            return True
        self.cur = self._pos(event)
        self.pressed = False
        if self.dragging:
            rect = self._drag_rect()
            self.dragging = False
            if rect[2] >= 2 and rect[3] >= 2:
                self._finish(rect)
                return True
        self._update_hover()
        self._finish(self.hover)
        return True

    def _on_key(self, _w, event):
        key = event.keyval
        if key == Gdk.KEY_Escape:
            self._finish(None)
        elif key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self._finish(self.hover or self.shot.monitor_at(*self.cur))
        elif key in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down):
            step = 10 if event.state & Gdk.ModifierType.SHIFT_MASK else 1
            dx = {Gdk.KEY_Left: -step, Gdk.KEY_Right: step}.get(key, 0)
            dy = {Gdk.KEY_Up: -step, Gdk.KEY_Down: step}.get(key, 0)
            seat = Gdk.Display.get_default().get_default_seat()
            screen, x, y = seat.get_pointer().get_position()
            seat.get_pointer().warp(screen, x + dx, y + dy)
        return True

    def _finish(self, rect):
        if self._finished:
            return
        self._finished = True
        Gdk.Display.get_default().get_default_seat().ungrab()
        self.hide()
        self.destroy()
        # pequena espera para a sobreposição sumir de fato antes de continuar
        GLib.timeout_add(60, lambda: (self.on_done(rect), False)[1])

    # ------------------------------------------------------------- geometria
    def _drag_rect(self):
        (x0, y0), (x1, y1) = self.start, self.cur
        x, y = min(x0, x1), min(y0, y1)
        return x, y, abs(x1 - x0) + 1, abs(y1 - y0) + 1

    def _update_hover(self):
        x, y = self.cur
        self.hover = None
        for r in self.windows:
            if r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3]:
                mon = self.shot.monitor_at(x, y)
                self.hover = _intersect(r, (0, 0, self.shot.width, self.shot.height)) or mon
                return
        self.hover = self.shot.monitor_at(x, y)

    # ------------------------------------------------------------- desenho
    def _on_draw(self, _w, ctx):
        s = self.scale
        ctx.scale(1 / s, 1 / s)
        ctx.set_source_surface(self.dim, 0, 0)
        ctx.paint()

        sel = self._drag_rect() if self.dragging else self.hover
        if sel:
            x, y, w, h = sel
            ctx.save()
            ctx.rectangle(x, y, w, h)
            ctx.clip()
            ctx.set_source_surface(self.img, 0, 0)
            ctx.paint()
            ctx.restore()
            ctx.set_source_rgb(*self.accent)
            lw = 2 * s if self.dragging else 1.5 * s
            ctx.set_line_width(lw)
            if not self.dragging:
                ctx.set_dash([6 * s, 4 * s])
            ctx.rectangle(x + lw / 2, y + lw / 2, w - lw, h - lw)
            ctx.stroke()
            ctx.set_dash([])
            self._draw_size_label(ctx, sel)

        if self.crosshair:
            self._draw_crosshair(ctx)
        if not self.dragging:
            self._draw_hint(ctx)
        if self.magnifier:
            self._draw_magnifier(ctx)

    def _layout(self, ctx, text, size=10, bold=False):
        layout = PangoCairo.create_layout(ctx)
        desc = Pango.FontDescription.from_string(f"Sans {'Bold ' if bold else ''}{size}")
        desc.set_absolute_size(size * self.scale * Pango.SCALE * 1.333)
        layout.set_font_description(desc)
        layout.set_text(text, -1)
        return layout

    def _pill(self, ctx, x, y, layout, bg=(0.08, 0.08, 0.1, 0.85), fg=(1, 1, 1)):
        s = self.scale
        tw, th = layout.get_pixel_size()
        pad_x, pad_y = 8 * s, 4 * s
        rounded_rect(ctx, x, y, tw + 2 * pad_x, th + 2 * pad_y, 6 * s)
        ctx.set_source_rgba(*bg)
        ctx.fill()
        ctx.move_to(x + pad_x, y + pad_y)
        ctx.set_source_rgb(*fg)
        PangoCairo.show_layout(ctx, layout)
        return tw + 2 * pad_x, th + 2 * pad_y

    def _draw_size_label(self, ctx, sel):
        s = self.scale
        x, y, w, h = sel
        layout = self._layout(ctx, f"{w} × {h}", 9, True)
        tw, th = layout.get_pixel_size()
        bh = th + 8 * s
        ly = y - bh - 6 * s
        if ly < 0:
            ly = y + 6 * s
        lx = max(0, min(x, self.shot.width - tw - 16 * s))
        self._pill(ctx, lx, ly, layout, bg=(*self.accent, 0.95))

    def _draw_crosshair(self, ctx):
        x, y = self.cur
        ctx.save()
        ctx.set_line_width(1)
        ctx.set_source_rgba(1, 1, 1, 0.55)
        ctx.set_dash([4, 4])
        ctx.move_to(0, y + 0.5)
        ctx.line_to(self.shot.width, y + 0.5)
        ctx.move_to(x + 0.5, 0)
        ctx.line_to(x + 0.5, self.shot.height)
        ctx.stroke()
        ctx.restore()

    def _draw_hint(self, ctx):
        s = self.scale
        mx, my, mw, _mh = self.shot.monitor_at(*self.cur)
        if self.recording:
            text = "Gravar: arraste para selecionar a área  •  clique numa janela ou monitor  •  Esc cancela"
        else:
            text = "Arraste para selecionar  •  clique numa janela ou monitor  •  Enter captura o destaque  •  Esc cancela"
        layout = self._layout(ctx, text, 10)
        tw, _th = layout.get_pixel_size()
        self._pill(ctx, mx + (mw - tw) / 2 - 8 * s, my + 24 * s, layout)

    def _pixel_hex(self, x, y):
        if not (0 <= x < self.shot.width and 0 <= y < self.shot.height):
            return None
        i = y * self.rowstride + x * self.nch
        r, g, b = self.pixels[i], self.pixels[i + 1], self.pixels[i + 2]
        return f"#{r:02X}{g:02X}{b:02X}"

    def _draw_magnifier(self, ctx):
        s = self.scale
        cx, cy = self.cur
        size = MAG_PIXELS * MAG_ZOOM * s
        zoom = MAG_ZOOM * s
        mon = self.shot.monitor_at(cx, cy)
        bx, by = cx + 24 * s, cy + 24 * s
        info_h = 42 * s
        if bx + size > mon[0] + mon[2]:
            bx = cx - 24 * s - size
        if by + size + info_h > mon[1] + mon[3]:
            by = cy - 24 * s - size - info_h

        ctx.save()
        rounded_rect(ctx, bx, by, size, size, 8 * s)
        ctx.clip()
        ctx.set_source_rgb(0.1, 0.1, 0.1)
        ctx.paint()
        ctx.translate(bx + size / 2, by + size / 2)
        ctx.scale(zoom, zoom)
        ctx.translate(-(cx + 0.5), -(cy + 0.5))
        ctx.set_source_surface(self.img, 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_NEAREST)
        ctx.paint()
        ctx.restore()

        # grade e pixel central
        ctx.save()
        ctx.set_line_width(1)
        px = bx + size / 2 - zoom / 2
        py = by + size / 2 - zoom / 2
        ctx.set_source_rgba(1, 1, 1, 0.08)
        for i in range(1, MAG_PIXELS):
            ctx.move_to(bx + i * zoom, by)
            ctx.line_to(bx + i * zoom, by + size)
            ctx.move_to(bx, by + i * zoom)
            ctx.line_to(bx + size, by + i * zoom)
        ctx.stroke()
        ctx.set_source_rgb(*self.accent)
        ctx.set_line_width(2)
        ctx.rectangle(px, py, zoom, zoom)
        ctx.stroke()
        rounded_rect(ctx, bx, by, size, size, 8 * s)
        ctx.set_source_rgba(1, 1, 1, 0.9)
        ctx.set_line_width(2 * s)
        ctx.stroke()
        ctx.restore()

        color = self._pixel_hex(cx, cy) or ""
        layout = self._layout(ctx, f"X: {cx}  Y: {cy}\n{color}", 8)
        ctx.save()
        w, h = self._pill(ctx, bx, by + size + 6 * s, layout)
        if color:
            r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
            rounded_rect(ctx, bx + w + 6 * s, by + size + 6 * s, h, h, 6 * s)
            ctx.set_source_rgb(r, g, b)
            ctx.fill_preserve()
            ctx.set_source_rgba(1, 1, 1, 0.9)
            ctx.set_line_width(1.5 * s)
            ctx.stroke()
        ctx.restore()


def _intersect(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2 = min(a[0] + a[2], b[0] + b[2])
    y2 = min(a[1] + a[3], b[1] + b[3])
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2 - x1, y2 - y1

