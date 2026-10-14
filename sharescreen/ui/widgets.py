"""Componentes de interface reutilizáveis."""
import os

from gi.repository import Gdk, Gtk, Pango

from ..hotkeys import accel_label


def label(text, css=None, xalign=0.0, wrap=False, ellipsize=False):
    lbl = Gtk.Label(label=text, xalign=xalign)
    if css:
        for c in css.split():
            lbl.get_style_context().add_class(c)
    if wrap:
        lbl.set_line_wrap(True)
        lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if ellipsize:
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
    return lbl


def page_scroller(child):
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    clamp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    clamp.set_halign(Gtk.Align.CENTER)
    clamp.set_size_request(640, -1)
    clamp.set_margin_top(18)
    clamp.set_margin_bottom(24)
    clamp.set_margin_start(24)
    clamp.set_margin_end(24)
    clamp.pack_start(child, False, False, 0)
    sw.add(clamp)
    return sw


class PrefGroup(Gtk.Box):
    def __init__(self, title=None, description=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_bottom(18)
        if title:
            self.pack_start(label(title, "group-title"), False, False, 0)
        if description:
            self.pack_start(label(description, "dim-label group-desc", wrap=True), False, False, 0)
        frame = Gtk.Frame()
        frame.get_style_context().add_class("pref-frame")
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.get_style_context().add_class("pref-list")
        self.listbox.set_header_func(self._separator)
        frame.add(self.listbox)
        self.pack_start(frame, False, False, 0)

    @staticmethod
    def _separator(row, before):
        if before and not row.get_header():
            row.set_header(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

    def add_row(self, title, subtitle=None, widget=None, activatable_widget=None):
        row = Gtk.ListBoxRow()
        row.set_activatable(activatable_widget is not None)
        box = Gtk.Box(spacing=12)
        box.get_style_context().add_class("pref-row")
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        texts.set_valign(Gtk.Align.CENTER)
        texts.pack_start(label(title, "pref-title", wrap=True), False, False, 0)
        if subtitle:
            texts.pack_start(label(subtitle, "dim-label pref-subtitle", wrap=True), False, False, 0)
        box.pack_start(texts, True, True, 0)
        if widget:
            widget.set_valign(Gtk.Align.CENTER)
            box.pack_end(widget, False, False, 0)
        row.add(box)
        if activatable_widget is not None:
            self.listbox.connect("row-activated",
                                 lambda _l, r: r is row and activatable_widget.activate())
        self.listbox.add(row)
        return row

    # ----- linhas ligadas à configuração
    def switch(self, cfg, key, title, subtitle=None, on_change=None):
        sw = Gtk.Switch()
        sw.set_active(bool(cfg[key]))

        def changed(s, _p):
            cfg.set(key, s.get_active())
            if on_change:
                on_change(s.get_active())

        sw.connect("notify::active", changed)
        cfg.connect(lambda k, v: k == key and sw.get_active() != bool(v) and sw.set_active(bool(v)))
        self.add_row(title, subtitle, sw, activatable_widget=sw)
        return sw

    def combo(self, cfg, key, title, options, subtitle=None, cast=str):
        cb = Gtk.ComboBoxText()
        for value, text in options:
            cb.append(str(value), text)
        cb.set_active_id(str(cfg[key]))
        cb.connect("changed", lambda c: cfg.set(key, cast(c.get_active_id())))
        cfg.connect(lambda k, v: k == key and cb.get_active_id() != str(v) and cb.set_active_id(str(v)))
        self.add_row(title, subtitle, cb)
        return cb

    def spin(self, cfg, key, title, lo, hi, step=1, subtitle=None, suffix=None):
        sp = Gtk.SpinButton.new_with_range(lo, hi, step)
        sp.set_value(cfg[key])
        sp.connect("value-changed", lambda s: cfg.set(key, int(s.get_value())))
        cfg.connect(lambda k, v: k == key and int(sp.get_value()) != int(v) and sp.set_value(v))
        if suffix:
            box = Gtk.Box(spacing=6)
            box.pack_start(sp, False, False, 0)
            box.pack_start(label(suffix, "dim-label"), False, False, 0)
            self.add_row(title, subtitle, box)
        else:
            self.add_row(title, subtitle, sp)
        return sp

    def entry(self, cfg, key, title, subtitle=None, width=28, on_change=None):
        en = Gtk.Entry()
        en.set_text(cfg[key] or "")
        en.set_width_chars(width)

        def changed(e):
            cfg.set(key, e.get_text())
            if on_change:
                on_change()

        en.connect("changed", changed)
        self.add_row(title, subtitle, en)
        return en

    def folder(self, cfg, key, title, subtitle=None):
        btn = Gtk.FileChooserButton(title=title, action=Gtk.FileChooserAction.SELECT_FOLDER)
        path = os.path.expanduser(cfg[key])
        os.makedirs(path, exist_ok=True)
        btn.set_filename(path)
        btn.set_width_chars(22)
        btn.connect("file-set", lambda b: b.get_filename() and cfg.set(key, b.get_filename()))
        self.add_row(title, subtitle, btn)
        return btn


class HotkeyButton(Gtk.Button):
    """Botão que captura uma combinação de teclas ao ser clicado."""

    def __init__(self, accel, on_change, on_begin=None, on_end=None):
        super().__init__()
        self.accel = accel or ""
        self.on_change = on_change
        self.on_begin = on_begin
        self.on_end = on_end
        self._listening = False
        self._handler = None
        self.set_size_request(190, -1)
        self.get_style_context().add_class("hotkey-button")
        self.connect("clicked", self._start)
        self._refresh()

    def set_accel(self, accel):
        self.accel = accel or ""
        self._refresh()

    def _refresh(self):
        if self._listening:
            self.set_label("Pressione as teclas…")
        else:
            self.set_label(accel_label(self.accel) or "Desativado")
        ctx = self.get_style_context()
        (ctx.add_class if not self.accel and not self._listening else ctx.remove_class)("dim-label")

    def _start(self, *_):
        if self._listening:
            return
        top = self.get_toplevel()
        if not isinstance(top, Gtk.Window):
            return
        self._listening = True
        if self.on_begin:
            self.on_begin()
        self._refresh()
        self._handler = top.connect("key-press-event", self._on_key)
        win = top.get_window()
        if win:
            Gdk.Display.get_default().get_default_seat().grab(
                win, Gdk.SeatCapabilities.KEYBOARD, False, None, None, None, None)
        self._focus_handler = top.connect("focus-out-event", lambda *_: self._stop())

    def _stop(self):
        if not self._listening:
            return False
        top = self.get_toplevel()
        Gdk.Display.get_default().get_default_seat().ungrab()
        if self._handler:
            top.disconnect(self._handler)
            top.disconnect(self._focus_handler)
            self._handler = None
        self._listening = False
        self._refresh()
        if self.on_end:
            self.on_end()
        return False

    def _on_key(self, _w, event):
        keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
        ok, keyval, _g, _l, _c = keymap.translate_keyboard_state(event.hardware_keycode, 0, event.group)
        if not ok:
            keyval = event.keyval
        keyval = Gdk.keyval_to_lower(keyval)
        mods = event.state & Gtk.accelerator_get_default_mod_mask()
        if keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Control_L, Gdk.KEY_Control_R,
                      Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Super_L, Gdk.KEY_Super_R,
                      Gdk.KEY_Meta_L, Gdk.KEY_Meta_R, Gdk.KEY_ISO_Level3_Shift):
            return True
        if keyval == Gdk.KEY_Escape and not mods:
            self._stop()
            return True
        if keyval in (Gdk.KEY_BackSpace, Gdk.KEY_Delete) and not mods:
            self.accel = ""
            self._stop()
            self.on_change("")
            return True
        if keyval == Gdk.KEY_Sys_Req:
            keyval = Gdk.KEY_Print
        accel = Gtk.accelerator_name(keyval, mods)
        self.accel = accel
        self._stop()
        self.on_change(accel)
        return True


def dialog_message(parent, title, text, kind=Gtk.MessageType.INFO, buttons=None):
    dialog = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=kind, text=title)
    if text:
        dialog.format_secondary_text(text)
    for b_label, resp in (buttons or [("OK", Gtk.ResponseType.OK)]):
        dialog.add_button(b_label, resp)
    resp = dialog.run()
    dialog.destroy()
    return resp
