"""Janela principal."""
from gi.repository import GLib, Gtk

from .. import APP_NAME, utils
from .capture_page import CapturePage
from .history_page import HistoryPage
from .settings_page import SettingsPage


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME)
        self.app = app
        self.set_default_size(1080, 720)
        self.set_icon_name("sharescreen")
        self._toast_id = 0

        header = Gtk.HeaderBar(show_close_button=True)
        self.set_titlebar(header)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        switcher = Gtk.StackSwitcher(stack=self.stack)
        header.set_custom_title(switcher)

        menu_btn = Gtk.MenuButton()
        menu_btn.add(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        menu_btn.set_popover(self._menu_popover(menu_btn))
        header.pack_end(menu_btn)

        quick = Gtk.Button.new_from_icon_name("applets-screenshooter-symbolic", Gtk.IconSize.BUTTON)
        quick.set_tooltip_text("Capturar região")
        quick.connect("clicked", lambda *_: app.trigger("region", from_window=True))
        header.pack_start(quick)

        overlay = Gtk.Overlay()
        overlay.add(self.stack)
        self.toast_rev = Gtk.Revealer()
        self.toast_rev.set_halign(Gtk.Align.CENTER)
        self.toast_rev.set_valign(Gtk.Align.END)
        self.toast_rev.set_margin_bottom(20)
        self.toast_label = Gtk.Label()
        self.toast_label.get_style_context().add_class("toast")
        self.toast_rev.add(self.toast_label)
        overlay.add_overlay(self.toast_rev)
        self.add(overlay)

        self.capture_page = CapturePage(app, self)
        self.history_page = HistoryPage(app, self)
        self.settings_page = SettingsPage(app, self)
        self.stack.add_titled(self.capture_page, "capture", "Capturar")
        self.stack.add_titled(self.history_page, "history", "Histórico")
        self.stack.add_titled(self.settings_page, "settings", "Configurações")

        self.connect("delete-event", self._on_delete)
        header.show_all()
        overlay.show_all()

    def _menu_popover(self, relative):
        pop = Gtk.Popover.new(relative)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_border_width(6)
        items = [
            ("Abrir pasta de capturas", lambda: utils.open_folder(self.app.config["screenshots_dir"])),
            ("Abrir pasta de vídeos", lambda: utils.open_folder(self.app.config["videos_dir"])),
            None,
            ("Atalhos de teclado", lambda: self.show_page("settings", "hotkeys")),
            ("Sobre o ShareScreen", self._about),
            None,
            ("Sair", self.app.quit_app),
        ]
        for it in items:
            if it is None:
                box.pack_start(Gtk.Separator(), False, False, 4)
                continue
            btn = Gtk.ModelButton(text=it[0])
            btn.set_alignment(0, 0.5)
            btn.connect("clicked", lambda _b, cb=it[1]: (pop.popdown(), cb()))
            box.pack_start(btn, False, False, 0)
        box.show_all()
        pop.add(box)
        return pop

    def _about(self):
        from .. import VERSION, paths
        from gi.repository import GdkPixbuf
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name(APP_NAME)
        dialog.set_version(VERSION)
        dialog.set_comments("Captura de tela, gravação de vídeo e GIF com editor de imagens.")
        try:
            dialog.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(paths.resource("sharescreen.svg"), 96, 96))
        except GLib.Error:
            pass
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.run()
        dialog.destroy()

    def show_page(self, name, section=None):
        self.stack.set_visible_child_name(name)
        if section:
            self.settings_page.show_section(section)
        self.present_window()

    def present_window(self):
        self.show()
        self.deiconify()
        self.present_with_time(Gtk.get_current_event_time() or 0)

    def toast(self, text):
        self.toast_label.set_text(text)
        self.toast_rev.set_reveal_child(True)
        if self._toast_id:
            GLib.source_remove(self._toast_id)
        self._toast_id = GLib.timeout_add(2200, self._hide_toast)

    def _hide_toast(self):
        self._toast_id = 0
        self.toast_rev.set_reveal_child(False)
        return False

    def _on_delete(self, *_):
        if self.app.config["close_to_tray"]:
            self.hide()
            self.app.on_window_hidden()
            return True
        self.app.quit_app()
        return True
