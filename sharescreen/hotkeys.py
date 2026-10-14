"""Atalhos globais no X11 usando XGrabKey numa conexão própria."""
import ctypes
import time

from gi.repository import Gdk, GLib, Gtk

from . import x11

# Variações de modificadores "travados" que devem ser ignoradas (CapsLock, NumLock).
_IGNORED = (0, x11.LockMask, x11.Mod2Mask, x11.LockMask | x11.Mod2Mask)
_RELEVANT = x11.ShiftMask | x11.ControlMask | x11.Mod1Mask | x11.Mod4Mask


def parse_accel(accel):
    """Converte '<Control>Print' em (keyval, modificadores X)."""
    if not accel:
        return None
    keyval, mods = Gtk.accelerator_parse(accel)
    if not keyval:
        return None
    if keyval == Gdk.KEY_Sys_Req:
        keyval = Gdk.KEY_Print
    xm = 0
    if mods & Gdk.ModifierType.SHIFT_MASK:
        xm |= x11.ShiftMask
    if mods & Gdk.ModifierType.CONTROL_MASK:
        xm |= x11.ControlMask
    if mods & Gdk.ModifierType.MOD1_MASK:
        xm |= x11.Mod1Mask
    if mods & (Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.MOD4_MASK):
        xm |= x11.Mod4Mask
    return keyval, xm


def accel_label(accel):
    parsed = accel and Gtk.accelerator_parse(accel)
    if not parsed or not parsed[0]:
        return ""
    return Gtk.accelerator_get_label(*parsed)


class HotkeyManager:
    def __init__(self, on_action):
        self.on_action = on_action
        self.available = False
        self.mapping = {}
        self.status = {}  # ação -> True (ativo) / False (falhou)
        self._bindings = {}
        self._suspended = False
        self._last = (None, 0.0)
        try:
            self._d = x11.XDisplay()
        except OSError:
            self._d = None
            return
        self.available = True
        GLib.io_add_watch(self._d.fileno(), GLib.PRIORITY_DEFAULT, GLib.IOCondition.IN,
                          self._on_events)

    # ------------------------------------------------------------------ API
    def apply(self, mapping):
        """Registra todos os atalhos (ação -> acelerador)."""
        self.mapping = dict(mapping)
        if self._suspended or not self.available:
            return
        self._ungrab_all()
        self.status = {}
        for action, accel in self.mapping.items():
            if accel:
                self.status[action] = self._grab(action, accel)
        self._on_events()

    def suspend(self):
        """Libera as teclas temporariamente (ex.: enquanto o usuário define um atalho)."""
        self._suspended = True
        self._ungrab_all()

    def resume(self):
        self._suspended = False
        self.apply(self.mapping)

    def failed(self):
        return [a for a, ok in self.status.items() if not ok]

    # ------------------------------------------------------------- internos
    def _grab(self, action, accel):
        parsed = parse_accel(accel)
        if not parsed:
            return False
        keyval, mods = parsed
        keycode = x11.xlib.XKeysymToKeycode(self._d.dpy, keyval)
        if not keycode or (keycode, mods) in self._bindings:
            return False
        with self._d.trap() as errors:
            for extra in _IGNORED:
                x11.xlib.XGrabKey(self._d.dpy, keycode, mods | extra, self._d.root, False,
                                  x11.GrabModeAsync, x11.GrabModeAsync)
        if errors:
            with self._d.trap():
                for extra in _IGNORED:
                    x11.xlib.XUngrabKey(self._d.dpy, keycode, mods | extra, self._d.root)
            return False
        self._bindings[(keycode, mods)] = action
        return True

    def _ungrab_all(self):
        if not self.available:
            return
        with self._d.trap():
            for keycode, mods in self._bindings:
                for extra in _IGNORED:
                    x11.xlib.XUngrabKey(self._d.dpy, keycode, mods | extra, self._d.root)
        self._bindings = {}

    def _on_events(self, *_args):
        ev = x11.XEvent()
        while x11.xlib.XPending(self._d.dpy):
            x11.xlib.XNextEvent(self._d.dpy, ctypes.byref(ev))
            if ev.type != x11.KeyPress:
                continue
            # Solta o teclado imediatamente para que a sobreposição de seleção possa capturá-lo.
            x11.xlib.XUngrabKeyboard(self._d.dpy, 0)
            x11.xlib.XFlush(self._d.dpy)
            action = self._bindings.get((ev.xkey.keycode, ev.xkey.state & _RELEVANT))
            if not action or self._suspended:
                continue
            now = time.monotonic()
            last_action, last_time = self._last
            if action == last_action and now - last_time < 0.35:  # repetição automática
                continue
            self._last = (action, now)
            GLib.idle_add(self._dispatch, action)
        return True

    def _dispatch(self, action):
        self.on_action(action)
        return False

