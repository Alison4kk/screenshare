"""Bindings mínimos (ctypes) de Xlib/XFixes.

Usados para: lista de janelas e geometria (detecção de janelas na seleção de
região), janela ativa, imagem do cursor e atalhos globais (XGrabKey).
Nenhuma dependência além das bibliotecas do X que já existem no sistema.
"""
import array
import ctypes
import ctypes.util
from contextlib import contextmanager
from ctypes import (CFUNCTYPE, POINTER, Structure, Union, byref, c_char_p, c_int, c_long,
                    c_short, c_ubyte, c_uint, c_ulong, c_ushort, c_void_p)

Window = c_ulong
Atom = c_ulong

KeyPress = 2
GrabModeAsync = 1
AnyPropertyType = 0

ShiftMask = 1 << 0
LockMask = 1 << 1
ControlMask = 1 << 2
Mod1Mask = 1 << 3
Mod2Mask = 1 << 4
Mod4Mask = 1 << 6


class XKeyEvent(Structure):
    _fields_ = [("type", c_int), ("serial", c_ulong), ("send_event", c_int),
                ("display", c_void_p), ("window", Window), ("root", Window),
                ("subwindow", Window), ("time", c_ulong), ("x", c_int), ("y", c_int),
                ("x_root", c_int), ("y_root", c_int), ("state", c_uint),
                ("keycode", c_uint), ("same_screen", c_int)]


class XEvent(Union):
    _fields_ = [("type", c_int), ("xkey", XKeyEvent), ("pad", c_long * 24)]


class XErrorEvent(Structure):
    _fields_ = [("type", c_int), ("display", c_void_p), ("resourceid", c_ulong),
                ("serial", c_ulong), ("error_code", c_ubyte), ("request_code", c_ubyte),
                ("minor_code", c_ubyte)]


class XFixesCursorImage(Structure):
    _fields_ = [("x", c_short), ("y", c_short), ("width", c_ushort), ("height", c_ushort),
                ("xhot", c_ushort), ("yhot", c_ushort), ("cursor_serial", c_ulong),
                ("pixels", POINTER(c_ulong)), ("atom", Atom), ("name", c_char_p)]


ErrorHandler = CFUNCTYPE(c_int, c_void_p, POINTER(XErrorEvent))


def _load(name):
    path = ctypes.util.find_library(name)
    if not path:
        return None
    try:
        return ctypes.CDLL(path)
    except OSError:
        return None


xlib = _load("X11")
xfixes = _load("Xfixes")


def _proto(fn, restype, *argtypes):
    fn.restype = restype
    fn.argtypes = list(argtypes)


if xlib:
    _proto(xlib.XOpenDisplay, c_void_p, c_char_p)
    _proto(xlib.XCloseDisplay, c_int, c_void_p)
    _proto(xlib.XDefaultRootWindow, Window, c_void_p)
    _proto(xlib.XInternAtom, Atom, c_void_p, c_char_p, c_int)
    _proto(xlib.XGetWindowProperty, c_int, c_void_p, Window, Atom, c_long, c_long, c_int, Atom,
           POINTER(Atom), POINTER(c_int), POINTER(c_ulong), POINTER(c_ulong), POINTER(c_void_p))
    _proto(xlib.XFree, c_int, c_void_p)
    _proto(xlib.XGetGeometry, c_int, c_void_p, Window, POINTER(Window), POINTER(c_int),
           POINTER(c_int), POINTER(c_uint), POINTER(c_uint), POINTER(c_uint), POINTER(c_uint))
    _proto(xlib.XTranslateCoordinates, c_int, c_void_p, Window, Window, c_int, c_int,
           POINTER(c_int), POINTER(c_int), POINTER(Window))
    _proto(xlib.XGrabKey, c_int, c_void_p, c_int, c_uint, Window, c_int, c_int, c_int)
    _proto(xlib.XUngrabKey, c_int, c_void_p, c_int, c_uint, Window)
    _proto(xlib.XUngrabKeyboard, c_int, c_void_p, c_ulong)
    _proto(xlib.XKeysymToKeycode, c_ubyte, c_void_p, c_ulong)
    _proto(xlib.XSync, c_int, c_void_p, c_int)
    _proto(xlib.XFlush, c_int, c_void_p)
    _proto(xlib.XPending, c_int, c_void_p)
    _proto(xlib.XNextEvent, c_int, c_void_p, POINTER(XEvent))
    _proto(xlib.XConnectionNumber, c_int, c_void_p)
    _proto(xlib.XSetErrorHandler, c_void_p, c_void_p)

if xfixes:
    _proto(xfixes.XFixesQueryExtension, c_int, c_void_p, POINTER(c_int), POINTER(c_int))
    _proto(xfixes.XFixesGetCursorImage, POINTER(XFixesCursorImage), c_void_p)


class XDisplay:
    """Conexão própria com o servidor X."""

    def __init__(self):
        if not xlib:
            raise OSError("libX11 não encontrada")
        self.dpy = xlib.XOpenDisplay(None)
        if not self.dpy:
            raise OSError("não foi possível abrir o display X")
        self.root = xlib.XDefaultRootWindow(self.dpy)
        self._atoms = {}
        self._xfixes_ok = None

    def fileno(self):
        return xlib.XConnectionNumber(self.dpy)

    def atom(self, name):
        a = self._atoms.get(name)
        if a is None:
            a = self._atoms[name] = xlib.XInternAtom(self.dpy, name.encode(), False)
        return a

    @contextmanager
    def trap(self):
        """Captura erros X (BadAccess, BadWindow...) em vez de abortar."""
        errors = []

        def handler(_dpy, ev):
            errors.append(ev.contents.error_code)
            return 0

        cb = ErrorHandler(handler)
        old = xlib.XSetErrorHandler(ctypes.cast(cb, c_void_p))
        try:
            yield errors
            xlib.XSync(self.dpy, False)
        finally:
            xlib.XSetErrorHandler(old)
            del cb

    # ----------------------------------------------------------- propriedades
    def get_property(self, win, name, max_items=4096):
        actual_type, actual_format = Atom(), c_int()
        nitems, after = c_ulong(), c_ulong()
        data = c_void_p()
        status = xlib.XGetWindowProperty(self.dpy, win, self.atom(name), 0, max_items, False,
                                         AnyPropertyType, byref(actual_type), byref(actual_format),
                                         byref(nitems), byref(after), byref(data))
        if status != 0 or not data.value:
            return None
        try:
            n = nitems.value
            if actual_format.value == 32:
                arr = (c_ulong * n).from_address(data.value)
                return [v & 0xFFFFFFFF for v in arr]
            if actual_format.value == 8:
                return ctypes.string_at(data.value, n)
            if actual_format.value == 16:
                arr = (c_ushort * n).from_address(data.value)
                return list(arr)
            return None
        finally:
            xlib.XFree(data)

    def get_cardinals(self, win, name):
        value = self.get_property(win, name)
        return value if isinstance(value, list) else []

    # --------------------------------------------------------------- janelas
    def active_window(self):
        v = self.get_cardinals(self.root, "_NET_ACTIVE_WINDOW")
        return v[0] if v and v[0] else None

    def window_rect(self, win, include_decorations=True):
        """Retângulo visível da janela (coordenadas da raiz, em pixels)."""
        with self.trap() as errors:
            root, x, y = Window(), c_int(), c_int()
            w, h, bw, depth = c_uint(), c_uint(), c_uint(), c_uint()
            ok = xlib.XGetGeometry(self.dpy, win, byref(root), byref(x), byref(y),
                                   byref(w), byref(h), byref(bw), byref(depth))
            ax, ay, child = c_int(), c_int(), Window()
            ok2 = ok and xlib.XTranslateCoordinates(self.dpy, win, self.root, 0, 0,
                                                     byref(ax), byref(ay), byref(child))
            frame = self.get_cardinals(win, "_NET_FRAME_EXTENTS")
            gtk = self.get_cardinals(win, "_GTK_FRAME_EXTENTS")
        if errors or not ok or not ok2:
            return None
        rx, ry, rw, rh = ax.value, ay.value, w.value, h.value
        if len(gtk) == 4:  # sombras de janelas com decoração do cliente (CSD)
            left, right, top, bottom = (_signed(v) for v in gtk)
            rx += left
            ry += top
            rw -= left + right
            rh -= top + bottom
        elif include_decorations and len(frame) == 4:
            left, right, top, bottom = (_signed(v) for v in frame)
            rx -= left
            ry -= top
            rw += left + right
            rh += top + bottom
        if rw <= 0 or rh <= 0:
            return None
        return rx, ry, rw, rh

    def visible_windows(self):
        """Janelas visíveis na área de trabalho atual, da mais alta para a mais baixa."""
        stack = self.get_cardinals(self.root, "_NET_CLIENT_LIST_STACKING") \
            or self.get_cardinals(self.root, "_NET_CLIENT_LIST")
        desk = self.get_cardinals(self.root, "_NET_CURRENT_DESKTOP")
        current = desk[0] if desk else None
        hidden = self.atom("_NET_WM_STATE_HIDDEN")
        skip_types = {self.atom("_NET_WM_WINDOW_TYPE_DESKTOP")}
        result = []
        for win in reversed(stack):
            with self.trap() as errors:
                state = self.get_cardinals(win, "_NET_WM_STATE")
                wdesk = self.get_cardinals(win, "_NET_WM_DESKTOP")
                wtype = self.get_cardinals(win, "_NET_WM_WINDOW_TYPE")
            if errors or hidden in state or skip_types.intersection(wtype):
                continue
            if current is not None and wdesk and wdesk[0] not in (current, 0xFFFFFFFF):
                continue
            rect = self.window_rect(win)
            if rect:
                result.append(rect)
        return result

    # ---------------------------------------------------------------- cursor
    def cursor_image(self):
        """(x, y, largura, altura, xhot, yhot, bytes ARGB32 pré-multiplicado)."""
        if not xfixes:
            return None
        if self._xfixes_ok is None:
            ev, err = c_int(), c_int()
            self._xfixes_ok = bool(xfixes.XFixesQueryExtension(self.dpy, byref(ev), byref(err)))
        if not self._xfixes_ok:
            return None
        img = xfixes.XFixesGetCursorImage(self.dpy)
        if not img:
            return None
        try:
            c = img.contents
            n = c.width * c.height
            pixels = (c_ulong * n).from_address(ctypes.addressof(c.pixels.contents))
            data = array.array("I", (p & 0xFFFFFFFF for p in pixels)).tobytes()
            return c.x, c.y, c.width, c.height, c.xhot, c.yhot, data
        finally:
            xlib.XFree(img)

    def close(self):
        if self.dpy:
            xlib.XCloseDisplay(self.dpy)
            self.dpy = None


def _signed(v):
    return v - (1 << 32) if v & 0x80000000 else v


_shared = None


def shared():
    """Conexão compartilhada para consultas (não usada para atalhos)."""
    global _shared
    if _shared is None:
        try:
            _shared = XDisplay()
        except OSError:
            _shared = False
    return _shared or None
