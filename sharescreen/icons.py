"""Ícones vetoriais desenhados com Cairo (grade 24x24).

Independem do tema de ícones instalado e herdam a cor do texto do tema.
"""
import math

import cairo
from gi.repository import Gtk


def _rrect(ctx, x, y, w, h, r):
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    ctx.close_path()


rounded_rect = _rrect


def _poly(ctx, pts, close=False):
    ctx.move_to(*pts[0])
    for p in pts[1:]:
        ctx.line_to(*p)
    if close:
        ctx.close_path()


def _corners(ctx, a=4, b=20, L=5):
    _poly(ctx, [(a, a + L), (a, a), (a + L, a)])
    _poly(ctx, [(b - L, a), (b, a), (b, a + L)])
    _poly(ctx, [(b, b - L), (b, b), (b - L, b)])
    _poly(ctx, [(a + L, b), (a, b), (a, b - L)])
    ctx.stroke()


def i_region(ctx):
    _corners(ctx)
    _poly(ctx, [(12, 9), (12, 15)])
    _poly(ctx, [(9, 12), (15, 12)])
    ctx.stroke()


def i_fullscreen(ctx):
    _rrect(ctx, 2.5, 4.5, 19, 13, 2)
    ctx.stroke()
    _poly(ctx, [(9, 20.5), (15, 20.5)])
    ctx.stroke()
    _poly(ctx, [(6, 10), (6, 8), (8, 8)])
    _poly(ctx, [(16, 8), (18, 8), (18, 10)])
    _poly(ctx, [(18, 12), (18, 14), (16, 14)])
    _poly(ctx, [(8, 14), (6, 14), (6, 12)])
    ctx.stroke()


def i_monitor(ctx):
    _rrect(ctx, 2.5, 4.5, 19, 13, 2)
    ctx.stroke()
    _poly(ctx, [(12, 17.5), (12, 20.5)])
    _poly(ctx, [(8, 20.5), (16, 20.5)])
    ctx.stroke()


def i_window(ctx):
    _rrect(ctx, 3, 4.5, 18, 15, 2)
    ctx.stroke()
    _poly(ctx, [(3, 9), (21, 9)])
    ctx.stroke()
    for x in (6, 8.5, 11):
        ctx.arc(x, 6.8, 0.9, 0, 2 * math.pi)
        ctx.fill()


def i_last_region(ctx):
    _corners(ctx)
    ctx.arc(12, 12, 3.6, -0.3, 1.5 * math.pi)
    ctx.stroke()
    _poly(ctx, [(12, 6.8), (14, 8.4), (12, 10)], close=True)
    ctx.fill()


def i_record(ctx):
    ctx.arc(12, 12, 8.5, 0, 2 * math.pi)
    ctx.stroke()
    ctx.arc(12, 12, 4.5, 0, 2 * math.pi)
    ctx.fill()


def i_gif(ctx):
    _rrect(ctx, 2.5, 5.5, 19, 13, 2.5)
    ctx.stroke()
    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(7.5)
    ext = ctx.text_extents("GIF")
    ctx.move_to(12 - ext.width / 2 - ext.x_bearing, 12 - ext.height / 2 - ext.y_bearing)
    ctx.show_text("GIF")


def i_folder(ctx):
    _poly(ctx, [(3, 7), (3, 18.5), (21, 18.5), (21, 8.5), (11.5, 8.5), (9.5, 6), (3, 6), (3, 7)])
    ctx.stroke()


def i_select(ctx):
    _poly(ctx, [(6, 3.5), (6, 19), (10, 15.2), (12.6, 20.6), (15, 19.5), (12.4, 14.2), (17.5, 14)],
          close=True)
    ctx.stroke()


def i_arrow(ctx):
    _poly(ctx, [(5, 19), (18, 6)])
    ctx.stroke()
    _poly(ctx, [(19.5, 4.5), (11, 7), (17, 13)], close=True)
    ctx.fill()


def i_rect(ctx):
    _rrect(ctx, 4, 6, 16, 12, 1)
    ctx.stroke()


def i_ellipse(ctx):
    ctx.save()
    ctx.translate(12, 12)
    ctx.scale(8.5, 6.5)
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.restore()
    ctx.stroke()


def i_line(ctx):
    _poly(ctx, [(5, 19), (19, 5)])
    ctx.stroke()


def i_pen(ctx):
    ctx.move_to(4, 17)
    ctx.curve_to(7, 9, 10, 9, 11, 13)
    ctx.curve_to(12, 17, 15, 18, 20, 7)
    ctx.stroke()


def i_highlight(ctx):
    ctx.save()
    r, g, b, a = _source_rgba(ctx)
    ctx.set_source_rgba(r, g, b, 0.35 * a)
    ctx.rectangle(3, 15, 18, 5)
    ctx.fill()
    ctx.restore()
    _poly(ctx, [(9, 15), (16, 4), (19.5, 6.5), (12.5, 17), (9, 17)], close=True)
    ctx.stroke()


def i_text(ctx):
    _poly(ctx, [(5.5, 6), (18.5, 6)])
    _poly(ctx, [(12, 6), (12, 19)])
    _poly(ctx, [(9.5, 19), (14.5, 19)])
    ctx.stroke()


def i_number(ctx):
    ctx.arc(12, 12, 8.5, 0, 2 * math.pi)
    ctx.stroke()
    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(10)
    ext = ctx.text_extents("1")
    ctx.move_to(12 - ext.width / 2 - ext.x_bearing, 12 - ext.height / 2 - ext.y_bearing)
    ctx.show_text("1")


def i_blur(ctx):
    r, g, b, a = _source_rgba(ctx)
    for i, (x, y) in enumerate([(6, 6), (12, 6), (18, 6), (6, 12), (12, 12), (18, 12),
                                (6, 18), (12, 18), (18, 18)]):
        ctx.set_source_rgba(r, g, b, a * (0.35 + 0.65 * ((i * 5) % 3) / 2))
        ctx.arc(x, y, 2.3 if i % 2 else 1.6, 0, 2 * math.pi)
        ctx.fill()


def i_pixelate(ctx):
    r, g, b, a = _source_rgba(ctx)
    for row in range(3):
        for col in range(3):
            alpha = 1.0 if (row + col) % 2 == 0 else 0.35
            ctx.set_source_rgba(r, g, b, a * alpha)
            ctx.rectangle(4 + col * 5.5, 4 + row * 5.5, 5, 5)
            ctx.fill()


def i_crop(ctx):
    _poly(ctx, [(7, 3), (7, 17), (21, 17)])
    _poly(ctx, [(3, 7), (17, 7), (17, 21)])
    ctx.stroke()


def i_stop(ctx):
    _rrect(ctx, 6, 6, 12, 12, 2)
    ctx.fill()


def i_pause(ctx):
    _rrect(ctx, 6.5, 5.5, 4, 13, 1)
    _rrect(ctx, 13.5, 5.5, 4, 13, 1)
    ctx.fill()


def i_play(ctx):
    _poly(ctx, [(8, 5.5), (19, 12), (8, 18.5)], close=True)
    ctx.fill()


def i_close(ctx):
    _poly(ctx, [(7, 7), (17, 17)])
    _poly(ctx, [(17, 7), (7, 17)])
    ctx.stroke()


def _source_rgba(ctx):
    src = ctx.get_source()
    try:
        return src.get_rgba()
    except (AttributeError, cairo.Error, TypeError):
        return 1, 1, 1, 1


ICONS = {name[2:]: fn for name, fn in globals().items() if name.startswith("i_")}


def draw(ctx, name, size, rgba, line_width=1.8):
    ctx.save()
    ctx.scale(size / 24.0, size / 24.0)
    ctx.set_source_rgba(*rgba)
    ctx.set_line_width(line_width)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ICONS[name](ctx)
    ctx.restore()


class Icon(Gtk.DrawingArea):
    """Ícone Cairo. Se `badge` for uma cor (r,g,b), desenha um quadrado colorido de fundo."""

    def __init__(self, name, size=20, badge=None, rgba=None):
        super().__init__()
        self.name = name
        self.size = size
        self.badge = badge
        self.rgba = rgba
        self.set_size_request(size, size)
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)
        self.connect("draw", self._on_draw)

    def set_name_icon(self, name):
        self.name = name
        self.queue_draw()

    def _on_draw(self, _w, ctx):
        size = self.size
        if self.badge:
            _rrect(ctx, 0, 0, size, size, size * 0.26)
            ctx.set_source_rgb(*self.badge)
            ctx.fill()
            pad = size * 0.2
            ctx.translate(pad, pad)
            draw(ctx, self.name, size - 2 * pad, self.rgba or (1, 1, 1, 1), 2.0)
            return
        if self.rgba:
            rgba = self.rgba
        else:
            c = self.get_style_context().get_color(self.get_state_flags())
            rgba = (c.red, c.green, c.blue, c.alpha)
        draw(ctx, self.name, size, rgba)
