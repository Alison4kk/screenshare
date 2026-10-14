import os
import sys

MISSING_HELP = """O ShareScreen precisa de alguns pacotes do sistema.
No Linux Mint / Ubuntu / Debian, instale com:

  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 ffmpeg \\
      gir1.2-notify-0.7 gir1.2-xapp-1.0

Detalhe: {err}
"""


def main():
    session_wayland = (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
                       or os.environ.get("WAYLAND_DISPLAY"))
    if session_wayland and "GDK_BACKEND" not in os.environ:
        # Roda via XWayland: permite a sobreposição de seleção cobrir todos os monitores.
        os.environ["GDK_BACKEND"] = "x11"
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        gi.require_version("GdkPixbuf", "2.0")
        gi.require_version("Pango", "1.0")
        gi.require_version("PangoCairo", "1.0")
        import cairo  # noqa: F401
        from gi.repository import Gtk  # noqa: F401
        gi.require_foreign("cairo")
    except (ImportError, ValueError) as err:
        sys.stderr.write(MISSING_HELP.format(err=err))
        return 1
    from gi.repository import Gdk, GLib
    GLib.set_prgname("sharescreen")
    Gdk.set_program_class("ShareScreen")
    from .app import Application
    return Application().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
