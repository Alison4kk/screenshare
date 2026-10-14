"""Aplicativo principal: coordena captura, gravação, bandeja, atalhos e janelas."""
import os
import signal
import sys

from gi.repository import Gdk, Gio, GLib, Gtk

from . import APP_ID, APP_NAME, capture, desktop, paths, utils
from .config import Config
from .editor import ImageEditor
from .history import History, ThumbnailLoader
from .hotkeys import HotkeyManager
from .notify import Notifier
from .overlay import RegionSelector
from .recorder import Countdown, Recorder
from .tray import Tray

CLI_ACTIONS = [
    ("region", "region", "Capturar uma região"),
    ("fullscreen", "fullscreen", "Capturar a tela inteira"),
    ("window", "window", "Capturar a janela ativa"),
    ("monitor", "monitor", "Capturar o monitor onde está o mouse"),
    ("last-region", "last_region", "Capturar a última região usada"),
    ("record", "record", "Gravar vídeo (ou parar a gravação atual)"),
    ("record-gif", "record_gif", "Gravar GIF (ou parar a gravação atual)"),
]
CLI_FLAGS = [
    ("stop", "Parar a gravação em andamento"),
    ("show", "Mostrar a janela principal"),
    ("history", "Abrir o histórico"),
    ("settings", "Abrir as configurações"),
    ("background", "Iniciar apenas na bandeja"),
    ("quit", "Encerrar o ShareScreen"),
]
RECORD_ACTIONS = ("record", "record_gif")


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        for flag, _action, desc in CLI_ACTIONS:
            self.add_main_option(flag, 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, desc, None)
        for flag, desc in CLI_FLAGS:
            self.add_main_option(flag, 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, desc, None)
        self.add_main_option("delay", 0, GLib.OptionFlags.NONE, GLib.OptionArg.INT,
                             "Atraso em segundos antes da captura", "SEG")
        self.window = None
        self.busy = False
        self.started = False
        self._restore_window = False
        self._restore_after_record = False
        self._quit_after_record = False
        self._css_provider = None
        self._system_theme = None

    # ------------------------------------------------------------ ciclo de vida
    def do_startup(self):
        Gtk.Application.do_startup(self)
        GLib.set_application_name(APP_NAME)
        Gtk.IconTheme.get_default().append_search_path(paths.RES_DIR)
        Gtk.Window.set_default_icon_name("sharescreen")

        self.config = Config()
        self.history = History(self.config["history_limit"])
        self.thumbs = ThumbnailLoader()
        self.notifier = Notifier(self)
        self.recorder = Recorder(self)
        self.recorder.connect("changed", self._on_recorder_changed)
        self._load_css()
        self._apply_theme()

        self.hotkeys = HotkeyManager(self.trigger_hotkey)
        if not utils.is_wayland():
            self.hotkeys.apply(self.config["hotkeys"])
        self.config.connect(self._on_config)

        self.tray = Tray(self.toggle_window, self._build_tray_menu)
        if self.config["autostart"]:
            desktop.set_autostart(True)  # mantém o caminho do executável atualizado

        for sig in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._on_signal)
        self.hold()

    def do_command_line(self, cmdline):
        opts = cmdline.get_options_dict().end().unpack()
        first = not self.started
        self.started = True
        if opts.get("quit"):
            self.quit_app()
            return 0
        delay = opts.get("delay")
        did = False
        if opts.get("stop"):
            if self.recorder.active:
                self.recorder.stop()
            did = True
        for flag, action, _desc in CLI_ACTIONS:
            if opts.get(flag):
                self.trigger(action, delay=delay)
                did = True
                break
        if opts.get("history"):
            self.show_window("history")
            did = True
        if opts.get("settings"):
            self.show_window("settings")
            did = True
        if opts.get("show") or (not did and not opts.get("background")):
            self.show_window()
        if first and self.config["first_run"]:
            GLib.timeout_add(400, self._first_run)
        elif first:
            GLib.timeout_add(1500, self._warn_failed_hotkeys)
        return 0

    def _on_signal(self):
        self.quit_app()
        return GLib.SOURCE_CONTINUE

    def quit_app(self):
        state = self.recorder.state
        if state == "countdown":
            self.recorder.cancel()
        elif state in ("recording", "paused", "finishing"):
            # espera a gravação ser salva antes de sair
            self._quit_after_record = True
            if state != "finishing":
                self.recorder.stop()
            return
        self.config.save()
        self.history.flush()
        self.tray.hide()
        self.quit()

    # ---------------------------------------------------------------- janelas
    def _ensure_window(self):
        if self.window is None:
            from .ui.window import MainWindow
            self.window = MainWindow(self)
        return self.window

    def show_window(self, page=None, section=None):
        win = self._ensure_window()
        if page:
            win.show_page(page, section)
        else:
            win.present_window()

    def toggle_window(self):
        win = self.window
        if win and win.get_visible() and win.is_active():
            win.hide()
        else:
            self.show_window()

    def on_window_hidden(self):
        if not self.config["tray_hint_shown"]:
            self.config.set("tray_hint_shown", True)
            self.notifier.show(f"{APP_NAME} continua na bandeja",
                               "Use os atalhos ou clique no ícone da bandeja. Para sair, use o menu do ícone.")

    def show_error(self, title, text=""):
        print(f"[{APP_NAME}] {title}: {text}", file=sys.stderr)
        self.notifier.show(title, text, icon="dialog-error", urgent=True)

    # ---------------------------------------------------------------- estilo
    def _load_css(self):
        provider = Gtk.CssProvider()
        try:
            provider.load_from_path(paths.resource("style.css"))
        except GLib.Error as e:
            print("CSS:", e.message, file=sys.stderr)
            return
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._css_provider = provider

    def _apply_theme(self):
        settings = Gtk.Settings.get_default()
        if self._system_theme is None:
            self._system_theme = (settings.props.gtk_theme_name,
                                  settings.props.gtk_application_prefer_dark_theme)
        name, prefer_dark = self._system_theme
        mode = self.config["theme"]
        if mode == "system":
            settings.props.gtk_theme_name = name
            settings.props.gtk_application_prefer_dark_theme = prefer_dark
            return
        dark = mode == "dark"
        settings.props.gtk_application_prefer_dark_theme = dark
        candidate = _theme_variant(name, dark)
        settings.props.gtk_theme_name = candidate or name

    # ---------------------------------------------------------------- bandeja
    def _build_tray_menu(self):
        menu = Gtk.Menu()
        hk = self.config["hotkeys"]

        def item(text, cb, action=None, bold=False):
            mi = Gtk.MenuItem(label=text)
            if bold:
                mi.get_child().set_markup(f"<b>{GLib.markup_escape_text(text)}</b>")
            accel = hk.get(action) if action else None
            if accel:
                keyval, mods = Gtk.accelerator_parse(accel)
                if keyval:
                    mi.get_child().set_accel(keyval, mods)
            mi.connect("activate", lambda *_: cb())
            menu.append(mi)

        def sep():
            menu.append(Gtk.SeparatorMenuItem())

        rec = self.recorder
        if rec.state in ("recording", "paused", "countdown"):
            item("Parar gravação e salvar", rec.stop, "record", bold=True)
            if rec.state in ("recording", "paused") and not rec.gst:
                item("Continuar gravação" if rec.state == "paused" else "Pausar gravação",
                     rec.toggle_pause)
            item("Cancelar gravação", rec.cancel)
            sep()
        elif rec.state == "finishing":
            mi = Gtk.MenuItem(label="Finalizando gravação…")
            mi.set_sensitive(False)
            menu.append(mi)
            sep()

        item("Capturar região", lambda: self.trigger("region", from_tray=True), "region")
        item("Capturar tela inteira", lambda: self.trigger("fullscreen", from_tray=True), "fullscreen")
        item("Capturar janela ativa", lambda: self.trigger("window", from_tray=True), "window")
        item("Capturar monitor atual", lambda: self.trigger("monitor", from_tray=True), "monitor")
        item("Capturar última região", lambda: self.trigger("last_region", from_tray=True),
             "last_region")
        sep()
        if not rec.active:
            item("Gravar vídeo…", lambda: self.trigger("record", from_tray=True), "record")
            item("Gravar GIF…", lambda: self.trigger("record_gif", from_tray=True), "record_gif")
            sep()
        item(f"Abrir {APP_NAME}", self.show_window, "open_window", bold=True)
        item("Histórico", lambda: self.show_window("history"))
        item("Abrir pasta de capturas", lambda: utils.open_folder(self.config["screenshots_dir"]))
        item("Configurações", lambda: self.show_window("settings"))
        sep()
        item("Sair", self.quit_app)
        menu.show_all()
        return menu

    def _on_recorder_changed(self, rec):
        active = rec.state != "idle"
        tips = {"countdown": "preparando gravação", "recording": "gravando",
                "paused": "gravação pausada", "finishing": "finalizando gravação"}
        self.tray.set_recording(active, f"{APP_NAME} — {tips[rec.state]}" if active else None)
        self.tray.rebuild()
        if rec.state == "idle":
            if self._restore_after_record and self.window:
                self._restore_after_record = False
                self.window.present_window()
            if self._quit_after_record:
                self._quit_after_record = False
                GLib.timeout_add(300, lambda: (self.quit_app(), False)[1])

    # ---------------------------------------------------------------- config
    def _on_config(self, key, value):
        if key == "hotkeys":
            if not utils.is_wayland():
                self.hotkeys.apply(value)
            self.tray.rebuild()
            self._refresh_hotkey_ui()
        elif key == "theme":
            self._apply_theme()
        elif key == "history_limit":
            self.history.limit = int(value)

    def _refresh_hotkey_ui(self):
        if self.window:
            self.window.settings_page.refresh_hotkeys()

    def system_conflicts(self):
        if utils.is_wayland():
            return []
        return desktop.find_conflicts([a for a in self.config["hotkeys"].values() if a])

    def release_system_keys(self, parent=None):
        conflicts = self.system_conflicts()
        if not conflicts:
            return
        backup = desktop.release(conflicts)
        saved = list(self.config["released_system_keys"])
        known = {(b["schema"], b["key"]) for b in saved}
        saved += [b for b in backup if (b["schema"], b["key"]) not in known]
        self.config.set("released_system_keys", saved)

        def regrab():
            self.hotkeys.apply(self.config["hotkeys"])
            self._refresh_hotkey_ui()
            failed = self.hotkeys.failed()
            if self.window:
                self.window.toast("Atalhos liberados" if not failed else
                                  "Alguns atalhos continuam em uso por outro programa")
            return False

        GLib.timeout_add(900, regrab)

    def restore_system_keys(self):
        backup = self.config["released_system_keys"]
        if not backup:
            return
        self.hotkeys.suspend()
        desktop.restore(backup)
        self.config.set("released_system_keys", [])

        def regrab():
            self.hotkeys.resume()
            self._refresh_hotkey_ui()
            if self.window:
                self.window.toast("Atalhos do sistema restaurados")
            return False

        GLib.timeout_add(1200, regrab)

    # -------------------------------------------------------------- primeiro uso
    def _first_run(self):
        self.config.set("first_run", False)
        self.show_window()
        win = self.window
        dialog = Gtk.Dialog(title=f"Bem-vindo ao {APP_NAME}", transient_for=win, modal=True)
        dialog.add_button("Começar", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        area = dialog.get_content_area()
        area.set_border_width(18)
        area.set_spacing(10)
        title = Gtk.Label(xalign=0)
        title.set_markup(f"<b><big>Bem-vindo ao {APP_NAME}!</big></b>")
        area.pack_start(title, False, False, 0)
        text = Gtk.Label(xalign=0)
        text.set_line_wrap(True)
        text.set_max_width_chars(60)
        text.set_text("O app fica na bandeja do sistema e responde aos atalhos:\n\n"
                      "  Print — tela inteira\n"
                      "  Ctrl+Print — região (arraste ou clique numa janela)\n"
                      "  Alt+Print — janela ativa\n"
                      "  Shift+Print — gravar vídeo (de novo para parar)\n"
                      "  Ctrl+Shift+Print — gravar GIF\n\n"
                      "Tudo pode ser alterado em Configurações → Atalhos.")
        area.pack_start(text, False, False, 0)
        auto = Gtk.CheckButton(label="Iniciar o ShareScreen junto com o sistema")
        auto.set_active(True)
        area.pack_start(auto, False, False, 4)
        conflicts = self.system_conflicts()
        release = None
        if conflicts:
            release = Gtk.CheckButton(
                label="Usar essas teclas no ShareScreen (libera os atalhos de captura do sistema)")
            release.set_active(True)
            area.pack_start(release, False, False, 0)
            hint = Gtk.Label(xalign=0)
            hint.set_line_wrap(True)
            hint.set_max_width_chars(60)
            hint.get_style_context().add_class("dim-label")
            hint.set_text("Em uso hoje: " + "; ".join(desktop.describe(conflicts))
                          + ". Dá para desfazer em Configurações → Atalhos.")
            area.pack_start(hint, False, False, 0)
        dialog.show_all()
        dialog.run()
        if auto.get_active():
            self.config.set("autostart", True)
            desktop.set_autostart(True)
        if release is not None and release.get_active():
            self.release_system_keys(win)
        dialog.destroy()
        self.window.settings_page.refresh_hotkeys()
        return False

    def _warn_failed_hotkeys(self):
        if utils.is_wayland() or not self.hotkeys.available:
            return False
        failed = self.hotkeys.failed()
        if failed:
            from .config import ACTION_LABELS
            names = ", ".join(ACTION_LABELS.get(a, a) for a in failed)
            self.notifier.show("Alguns atalhos não estão ativos",
                               f"{names}: a combinação está em uso. Veja Configurações → Atalhos.",
                               actions=[("fix", "Resolver",
                                         lambda: self.show_window("settings", "hotkeys"))])
        return False

    # ---------------------------------------------------------------- captura
    def trigger_hotkey(self, action):
        self.trigger(action)

    def trigger(self, action, from_window=False, from_tray=False, delay=None):
        if action == "open_window":
            self.toggle_window()
            return
        if action in RECORD_ACTIONS and self.recorder.active:
            if self.recorder.state == "countdown":
                self.recorder.cancel()
            else:
                self.recorder.stop()
            return
        if self.busy:
            return
        self.busy = True
        if delay is None:
            delay = 0 if action in RECORD_ACTIONS else int(self.config["capture_delay"] or 0)
        wait = 300 if from_tray else 30
        win = self.window
        if win and win.get_visible() and self.config["hide_main_window"]:
            win.hide()
            self._restore_window = True
            wait = max(wait, 350)
        if delay > 0:
            GLib.timeout_add(wait, self._start_delay, action, delay)
        else:
            GLib.timeout_add(wait, self._do_capture, action)

    def _start_delay(self, action, delay):
        display = Gdk.Display.get_default()
        _s, x, y = display.get_default_seat().get_pointer().get_position()
        g = display.get_monitor_at_point(x, y).get_geometry()
        cd = Countdown(delay, (g.x, g.y, g.width, g.height), lambda: self._do_capture(action))
        cd.set_caption("Capturando")
        return False

    def _do_capture(self, action):
        try:
            if utils.is_wayland():
                self._capture_wayland(action)
            else:
                self._capture_x11(action)
        except Exception as e:  # noqa: BLE001 — nunca deixar o app travado em "ocupado"
            import traceback
            traceback.print_exc()
            self.show_error("Falha na captura", str(e))
            self._end_capture()
        return False

    def _capture_x11(self, action):
        cfg = self.config
        if action == "last_region" and not cfg["last_region"]:
            action = "region"
        if action in ("region",) + RECORD_ACTIONS:
            shot = capture.grab_screen(include_cursor=cfg["capture_cursor"] and action == "region",
                                       with_windows=cfg["region_detect_windows"])
            if not shot:
                raise RuntimeError("não foi possível ler a tela")
            sel = RegionSelector(shot, lambda rect: self._region_done(action, shot, rect),
                                 recording=action in RECORD_ACTIONS,
                                 magnifier=cfg["region_magnifier"],
                                 crosshair=cfg["region_crosshair"],
                                 detect_windows=cfg["region_detect_windows"])
            sel.show_all()
            return
        shot = capture.grab_screen(include_cursor=cfg["capture_cursor"])
        if not shot:
            raise RuntimeError("não foi possível ler a tela")
        if action == "fullscreen":
            self._process(shot.pixbuf)
        elif action == "monitor":
            self._process(shot.crop(shot.monitor_at(*shot.pointer)))
        elif action == "window":
            rect = capture.active_window_rect()
            if not rect:
                self.notifier.show("Nenhuma janela ativa", "Capturando o monitor atual.")
                rect = shot.monitor_at(*shot.pointer)
            self._process(shot.crop(rect))
        elif action == "last_region":
            self._process(shot.crop(cfg["last_region"]))

    def _capture_wayland(self, action):
        if action in RECORD_ACTIONS:
            self._restore_after_record = self._restore_window
            self._end_capture(restore=False)
            self.recorder.start(None, gif=action == "record_gif")
            return
        from . import portal

        def got(path):
            if not path:
                self._end_capture()
                return
            try:
                handle(path)
            except Exception as e:  # noqa: BLE001
                self.show_error("Falha na captura", str(e))
                self._end_capture()

        def handle(path):
            shot = capture.shot_from_file(path)
            capture.remove_quietly(path)
            if action in ("region", "last_region") and not (action == "last_region"
                                                            and self.config["last_region"]):
                cfg = self.config
                RegionSelector(shot, lambda rect: self._region_done("region", shot, rect),
                               magnifier=cfg["region_magnifier"], crosshair=cfg["region_crosshair"],
                               detect_windows=False).show_all()
            elif action == "last_region":
                self._process(shot.crop(self.config["last_region"]))
            elif action == "monitor":
                self._process(shot.crop(shot.monitor_at(*shot.pointer)))
            else:
                self._process(shot.pixbuf)

        portal.screenshot(got, interactive=(action == "window"))

    def _region_done(self, action, shot, rect):
        try:
            self._region_done_inner(action, shot, rect)
        except Exception as e:  # noqa: BLE001 — nunca deixar o app travado em "ocupado"
            import traceback
            traceback.print_exc()
            self.show_error("Falha na captura", str(e))
            self._end_capture()

    def _region_done_inner(self, action, shot, rect):
        if rect is None:
            self._end_capture()
            return
        self.config.set("last_region", list(rect))
        if action == "region":
            self._process(shot.crop(rect))
        else:
            self._restore_after_record = self._restore_window
            self._end_capture(restore=False)
            self.recorder.start(rect, gif=action == "record_gif")

    def _end_capture(self, restore=True):
        self.busy = False
        if restore and self._restore_window and self.window:
            self.window.present_window()
        self._restore_window = False

    def _process(self, pixbuf):
        if pixbuf is None:
            self.show_error("Nada foi capturado", "A área selecionada está fora da tela.")
            self._end_capture()
            return
        if self.config["play_sound"]:
            utils.play_sound("camera-shutter")
        if self.config["ac_open_editor"]:
            self._end_capture()
            ImageEditor(self, pixbuf, on_done=self._finish_image)
        else:
            self._finish_image(pixbuf)
            self._end_capture()

    def _finish_image(self, pixbuf):
        cfg = self.config
        path = entry = None
        if cfg["ac_save"]:
            fmt = cfg["image_format"]
            try:
                path = utils.build_output_path(cfg, "image", fmt)
                utils.save_pixbuf(pixbuf, path, fmt, cfg["jpeg_quality"])
            except OSError as e:
                path = None
                self.show_error("Não foi possível salvar a captura",
                                f"{e}. Verifique a pasta em Configurações → Captura.")
            except GLib.Error as e:
                capture.remove_quietly(path)
                path = None
                if fmt != "png":  # formato sem suporte no sistema: salva em PNG
                    path = utils.build_output_path(cfg, "image", "png")
                    try:
                        utils.save_pixbuf(pixbuf, path, "png")
                    except GLib.Error:
                        path = None
                if not path:
                    self.show_error("Não foi possível salvar a captura", e.message)
            if path:
                entry = self.history.add(path, "image", pixbuf.get_width(), pixbuf.get_height())
        clip = cfg["ac_clipboard"]
        if clip == "image":
            utils.copy_image(pixbuf)
        elif clip == "path" and path:
            utils.copy_text(path)
        if cfg["ac_notify"]:
            body = []
            if path:
                body.append(os.path.basename(path))
            if clip == "image":
                body.append("Imagem copiada para a área de transferência")
            elif clip == "path" and path:
                body.append("Caminho copiado para a área de transferência")
            actions = []
            if entry:
                actions = [("edit", "Editar", lambda: self.edit_entry(entry)),
                           ("folder", "Mostrar na pasta", lambda: utils.show_in_folder(path))]
            self.notifier.show("Captura salva" if path else "Captura copiada", "\n".join(body),
                               icon=path, actions=actions,
                               on_click=(lambda: utils.open_file(path)) if path else None)
        if cfg["ac_open_file"] and path:
            utils.open_file(path)

    def on_recording_saved(self, path, kind, width, height, duration):
        cfg = self.config
        self.history.add(path, kind, width, height, round(duration, 1))
        clip = cfg["ar_clipboard"]
        if clip == "file":
            utils.copy_file(path, "image/gif" if kind == "gif" else None)
        elif clip == "path":
            utils.copy_text(path)
        if cfg["play_sound"]:
            utils.play_sound("complete")
        if cfg["ar_notify"]:
            try:
                size = utils.human_size(os.path.getsize(path))
            except OSError:
                size = ""
            body = f"{os.path.basename(path)}\n{utils.human_duration(duration)} • {size}"
            if clip == "file":
                body += "\nCopiado para a área de transferência (Ctrl+V para colar)"
            elif clip == "path":
                body += "\nCaminho copiado para a área de transferência"
            self.notifier.show("GIF salvo" if kind == "gif" else "Gravação salva", body,
                               icon="video-x-generic",
                               actions=[("folder", "Mostrar na pasta",
                                         lambda: utils.show_in_folder(path))],
                               on_click=lambda: utils.open_file(path))
        if cfg["ar_open_file"]:
            utils.open_file(path)

    # ---------------------------------------------------------------- histórico
    def open_entry(self, entry, prefer_open=True):
        if not os.path.exists(entry["path"]):
            self.show_error("Arquivo não encontrado", entry["path"])
            return
        utils.open_file(entry["path"])

    def edit_entry(self, entry):
        if entry and os.path.exists(entry["path"]):
            ImageEditor.open_file(self, entry)


def _theme_variant(name, dark):
    """Tenta achar a variante clara/escura de um tema (ex.: Mint-Y-Dark-Aqua <-> Mint-Y-Aqua)."""
    candidates = []
    if dark and "-Dark" not in name:
        for prefix in ("Mint-Y", "Mint-L", "Mint-X"):
            if name.startswith(prefix):
                candidates.append(prefix + "-Dark" + name[len(prefix):])
        candidates.append(name + "-Dark")
        candidates.append(name + "-dark")
    elif not dark:
        candidates += [name.replace("-Dark", ""), name.replace("-dark", "")]
    for cand in candidates:
        if cand == name:
            continue
        for base in (os.path.expanduser("~/.themes"), os.path.expanduser("~/.local/share/themes"),
                     "/usr/share/themes"):
            if os.path.isdir(os.path.join(base, cand, "gtk-3.0")):
                return cand
    return None
