"""Captura da tela (X11 direto; Wayland via xdg-desktop-portal)."""
import os

import cairo
from gi.repository import Gdk, GdkPixbuf

from . import utils, x11


class Shot:
    """Imagem congelada da tela inteira + metadados, tudo em pixels reais."""

    def __init__(self, pixbuf, scale=1.0):
        self.pixbuf = pixbuf
        self.scale = scale
        self.width = pixbuf.get_width()
        self.height = pixbuf.get_height()
        self.monitors = monitor_rects(scale)
        self.windows = []
        self.pointer = pointer_position(scale)

    def crop(self, rect):
        rect = clamp_rect(rect, self.width, self.height)
        if not rect:
            return None
        x, y, w, h = rect
        return self.pixbuf.new_subpixbuf(x, y, w, h).copy()

    def monitor_at(self, x, y):
        for r in self.monitors:
            if r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3]:
                return r
        return self.monitors[0] if self.monitors else (0, 0, self.width, self.height)


def clamp_rect(rect, max_w, max_h):
    x, y, w, h = (int(round(v)) for v in rect)
    x2, y2 = min(max_w, x + w), min(max_h, y + h)
    x, y = max(0, x), max(0, y)
    if x2 - x < 1 or y2 - y < 1:
        return None
    return x, y, x2 - x, y2 - y


def screen_scale():
    root = Gdk.get_default_root_window()
    return root.get_scale_factor() or 1


def monitor_rects(scale=1.0):
    display = Gdk.Display.get_default()
    rects = []
    for i in range(display.get_n_monitors()):
        g = display.get_monitor(i).get_geometry()
        rects.append((int(g.x * scale), int(g.y * scale), int(g.width * scale), int(g.height * scale)))
    return rects


def pointer_position(scale=1.0):
    seat = Gdk.Display.get_default().get_default_seat()
    _screen, x, y = seat.get_pointer().get_position()
    return int(x * scale), int(y * scale)


def grab_screen(include_cursor=False, with_windows=False):
    """Captura todos os monitores (X11). Retorna Shot ou None."""
    root = Gdk.get_default_root_window()
    w, h = root.get_width(), root.get_height()
    pixbuf = Gdk.pixbuf_get_from_window(root, 0, 0, w, h)
    if pixbuf is None:
        return None
    scale = pixbuf.get_width() / float(w) if w else 1.0
    if include_cursor:
        pixbuf = composite_cursor(pixbuf)
    shot = Shot(pixbuf, scale)
    if with_windows:
        d = x11.shared()
        if d:
            shot.windows = d.visible_windows()
    return shot


def shot_from_file(path):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
    root = Gdk.get_default_root_window()
    scale = pixbuf.get_width() / float(root.get_width() or pixbuf.get_width())
    return Shot(pixbuf, scale)


def composite_cursor(pixbuf):
    d = x11.shared()
    cur = d.cursor_image() if d else None
    if not cur:
        return pixbuf
    cx, cy, cw, ch, xhot, yhot, data = cur
    w, h = pixbuf.get_width(), pixbuf.get_height()
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
    ctx = cairo.Context(surf)
    Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
    ctx.paint()
    csurf = cairo.ImageSurface.create_for_data(bytearray(data), cairo.FORMAT_ARGB32, cw, ch, cw * 4)
    ctx.set_source_surface(csurf, cx - xhot, cy - yhot)
    ctx.paint()
    surf.flush()
    return Gdk.pixbuf_get_from_surface(surf, 0, 0, w, h)


def active_window_rect():
    d = x11.shared()
    if not d:
        return None
    win = d.active_window()
    return d.window_rect(win) if win else None


def pixbuf_to_surface(pixbuf):
    w, h = pixbuf.get_width(), pixbuf.get_height()
    fmt = cairo.FORMAT_ARGB32 if pixbuf.get_has_alpha() else cairo.FORMAT_RGB24
    surf = cairo.ImageSurface(fmt, w, h)
    ctx = cairo.Context(surf)
    Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
    ctx.set_operator(cairo.OPERATOR_SOURCE)
    ctx.paint()
    surf.flush()
    return surf


def can_capture_directly():
    return not utils.is_wayland()


def remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass
