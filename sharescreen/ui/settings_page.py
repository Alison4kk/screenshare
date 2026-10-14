"""Configurações."""
import os

from gi.repository import Gtk

from .. import APP_NAME, VERSION, desktop, paths, utils
from ..config import ACTIONS, DEFAULT_HOTKEYS
from .widgets import HotkeyButton, PrefGroup, dialog_message, label, page_scroller


class SettingsPage(Gtk.Box):
    def __init__(self, app, window):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.app = app
        self.window = window
        self.cfg = app.config
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        sidebar = Gtk.StackSidebar()
        sidebar.set_stack(self.stack)
        sidebar.set_size_request(190, -1)
        self.pack_start(sidebar, False, False, 0)
        self.pack_start(self.stack, True, True, 0)

        self.stack.add_titled(page_scroller(self._general()), "general", "Geral")
        self.stack.add_titled(page_scroller(self._capture()), "capture", "Captura")
        self.stack.add_titled(page_scroller(self._after()), "after", "Após a captura")
        self.stack.add_titled(page_scroller(self._recording()), "recording", "Gravação")
        self.stack.add_titled(page_scroller(self._hotkeys()), "hotkeys", "Atalhos")
        self.stack.add_titled(page_scroller(self._advanced()), "advanced", "Avançado")

    def show_section(self, name):
        self.stack.set_visible_child_name(name)

    # ---------------------------------------------------------------- Geral
    def _general(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        g = PrefGroup("Inicialização")
        g.switch(self.cfg, "autostart", "Iniciar junto com o sistema",
                 "O ShareScreen fica na bandeja, pronto para os atalhos",
                 on_change=desktop.set_autostart)
        g.switch(self.cfg, "close_to_tray", "Fechar a janela mantém o app na bandeja",
                 "Desative para encerrar o app ao fechar a janela")
        box.pack_start(g, False, False, 0)

        g = PrefGroup("Aparência e som")
        g.combo(self.cfg, "theme", "Tema", [("system", "Seguir o sistema"), ("dark", "Escuro"),
                                             ("light", "Claro")])
        g.switch(self.cfg, "play_sound", "Tocar som ao capturar")
        box.pack_start(g, False, False, 0)
        return box

    # -------------------------------------------------------------- Captura
    def _capture(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        g = PrefGroup("Arquivos")
        g.folder(self.cfg, "screenshots_dir", "Pasta das capturas")
        g.combo(self.cfg, "image_format", "Formato da imagem",
                [("png", "PNG (sem perdas)"), ("jpg", "JPEG (menor)"), ("webp", "WebP")])
        g.spin(self.cfg, "jpeg_quality", "Qualidade JPEG/WebP", 10, 100, 5, suffix="%")
        g.switch(self.cfg, "use_subfolders", "Organizar em subpastas",
                 on_change=lambda *_: self._update_preview())
        g.entry(self.cfg, "subfolder_pattern", "Padrão da subpasta",
                "Ex.: %Y-%m cria uma pasta por mês", width=16, on_change=self._update_preview)
        g.entry(self.cfg, "filename_pattern", "Padrão do nome do arquivo",
                "%Y ano, %m mês, %d dia, %H hora, %M minuto, %S segundo",
                on_change=self._update_preview)
        self.preview = label("", "dim-label", wrap=True)
        g.add_row("Exemplo", None, self.preview)
        box.pack_start(g, False, False, 0)
        self._update_preview()

        g = PrefGroup("Captura")
        g.switch(self.cfg, "capture_cursor", "Incluir o cursor do mouse")
        g.spin(self.cfg, "capture_delay", "Atraso antes de capturar", 0, 30, 1, suffix="s")
        g.switch(self.cfg, "hide_main_window", "Esconder esta janela durante a captura")
        box.pack_start(g, False, False, 0)

        g = PrefGroup("Seleção de região")
        g.switch(self.cfg, "region_magnifier", "Mostrar lupa",
                 "Ampliação com coordenadas e cor do pixel")
        g.switch(self.cfg, "region_crosshair", "Mostrar linhas-guia")
        g.switch(self.cfg, "region_detect_windows", "Detectar janelas",
                 "Clique sobre uma janela para capturá-la sem arrastar")
        box.pack_start(g, False, False, 0)
        return box

    def _update_preview(self):
        if not hasattr(self, "preview"):
            return
        folder = os.path.expanduser(self.cfg["screenshots_dir"])
        if self.cfg["use_subfolders"] and self.cfg["subfolder_pattern"].strip():
            folder = os.path.join(folder, utils.safe_strftime(self.cfg["subfolder_pattern"]))
        name = utils.safe_strftime(self.cfg["filename_pattern"]) + "." + self.cfg["image_format"]
        text = os.path.join(folder, name).replace(os.path.expanduser("~"), "~")
        self.preview.set_text(text)
        self.preview.set_max_width_chars(40)

    # --------------------------------------------------------- Após captura
    def _after(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        g = PrefGroup("Depois de capturar uma imagem",
                      "Estas tarefas rodam em sequência após cada captura (ou ao concluir no editor).")
        g.switch(self.cfg, "ac_open_editor", "Abrir no editor",
                 "Adicione setas, texto, numeração, desfoque e recorte antes de salvar")
        g.switch(self.cfg, "ac_save", "Salvar o arquivo na pasta de capturas")
        g.combo(self.cfg, "ac_clipboard", "Copiar para a área de transferência",
                [("image", "A imagem"), ("path", "O caminho do arquivo"), ("none", "Nada")])
        g.switch(self.cfg, "ac_notify", "Mostrar notificação",
                 "Com botões para abrir, editar ou mostrar na pasta")
        g.switch(self.cfg, "ac_open_file", "Abrir a imagem no visualizador padrão")
        box.pack_start(g, False, False, 0)

        g = PrefGroup("Depois de gravar")
        g.switch(self.cfg, "ar_notify", "Mostrar notificação")
        g.combo(self.cfg, "ar_clipboard", "Copiar para a área de transferência",
                [("file", "O arquivo (cole em chats, navegador, pastas)"),
                 ("path", "O caminho do arquivo"), ("none", "Nada")],
                "Com “O arquivo”, basta Ctrl+V no Telegram, Discord, WhatsApp Web, Nemo…")
        g.switch(self.cfg, "ar_open_file", "Abrir o vídeo no reprodutor padrão")
        box.pack_start(g, False, False, 0)
        return box

    # ------------------------------------------------------------- Gravação
    def _recording(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if utils.is_wayland():
            box.pack_start(_info_bar(
                "Sessão Wayland detectada: a gravação usa o portal do sistema e grava o monitor ou "
                "janela escolhidos na caixa de diálogo (seleção de região e pausa ficam indisponíveis)."),
                False, False, 0)
        g = PrefGroup("Vídeo")
        g.folder(self.cfg, "videos_dir", "Pasta das gravações")
        g.combo(self.cfg, "video_format", "Formato",
                [("mp4", "MP4 (H.264) — mais compatível"), ("webm", "WebM (VP9)"),
                 ("mkv", "MKV (H.264)")])
        g.combo(self.cfg, "video_quality", "Qualidade",
                [("high", "Alta"), ("medium", "Média"), ("low", "Baixa (arquivos menores)")])
        g.spin(self.cfg, "video_fps", "Quadros por segundo", 5, 60, 5, suffix="fps")
        box.pack_start(g, False, False, 0)

        g = PrefGroup("Áudio")
        g.switch(self.cfg, "audio_system", "Gravar o som do computador",
                 "O que está tocando nos alto-falantes/fones")
        g.switch(self.cfg, "audio_mic", "Gravar o microfone", "Usa o microfone padrão do sistema")
        box.pack_start(g, False, False, 0)

        g = PrefGroup("Durante a gravação")
        g.switch(self.cfg, "record_cursor", "Mostrar o cursor no vídeo")
        g.spin(self.cfg, "record_countdown", "Contagem regressiva", 0, 10, 1, suffix="s")
        g.switch(self.cfg, "record_border", "Mostrar borda ao redor da área",
                 "A borda fica do lado de fora e não aparece no vídeo")
        g.switch(self.cfg, "record_toolbar", "Mostrar barra de controle",
                 "Tempo, pausar, parar e cancelar")
        box.pack_start(g, False, False, 0)

        g = PrefGroup("GIF")
        g.spin(self.cfg, "gif_fps", "Quadros por segundo", 5, 30, 1, suffix="fps")
        g.spin(self.cfg, "gif_max_width", "Largura máxima", 0, 3840, 80,
               "0 mantém o tamanho original", suffix="px")
        box.pack_start(g, False, False, 0)
        return box

    # -------------------------------------------------------------- Atalhos
    def _hotkeys(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hk = self.app.hotkeys
        if utils.is_wayland() or not hk.available:
            box.pack_start(_info_bar(
                "Atalhos globais próprios só funcionam no X11. Configure atalhos personalizados "
                "nas configurações de teclado do sistema usando os comandos listados abaixo."),
                False, False, 0)

        g = PrefGroup("Atalhos globais",
                      "Clique no botão e pressione a combinação desejada. Esc cancela, "
                      "Backspace desativa.")
        self.hk_buttons = {}
        self.hk_status = {}
        for action, text in ACTIONS:
            row_box = Gtk.Box(spacing=8)
            status = Gtk.Image()
            self.hk_status[action] = status
            btn = HotkeyButton(self.cfg["hotkeys"].get(action, ""),
                               on_change=lambda accel, a=action: self._set_hotkey(a, accel),
                               on_begin=hk.suspend, on_end=hk.resume)
            self.hk_buttons[action] = btn
            row_box.pack_start(status, False, False, 0)
            row_box.pack_start(btn, False, False, 0)
            g.add_row(text, None, row_box)
        box.pack_start(g, False, False, 0)

        g = PrefGroup("Conflitos com o sistema",
                      "Se o Cinnamon/GNOME/MATE já usa uma tecla (ex.: Print Screen), o ShareScreen "
                      "pode liberá-la para você. Dá para desfazer a qualquer momento.")
        self.conflict_label = label("", "dim-label", wrap=True)
        self.release_btn = Gtk.Button(label="Liberar atalhos")
        self.release_btn.get_style_context().add_class("suggested-action")
        self.release_btn.connect("clicked", lambda *_: self.app.release_system_keys(self.window))
        g.add_row("Situação", None, self.conflict_label)
        g.add_row("Usar as teclas no ShareScreen",
                  "Remove as combinações conflitantes dos atalhos do sistema", self.release_btn)
        self.restore_btn = Gtk.Button(label="Restaurar")
        self.restore_btn.connect("clicked", lambda *_: self.app.restore_system_keys())
        g.add_row("Devolver as teclas ao sistema",
                  "Restaura os atalhos de captura originais do ambiente", self.restore_btn)
        reset = Gtk.Button(label="Restaurar padrões")
        reset.connect("clicked", lambda *_: self._reset_hotkeys())
        g.add_row("Atalhos padrão do ShareScreen",
                  "Print, Ctrl+Print, Alt+Print, Shift+Print, Ctrl+Shift+Print", reset)
        box.pack_start(g, False, False, 0)

        g = PrefGroup("Linha de comando",
                      "Útil para criar atalhos no próprio sistema (ou no Wayland).")
        cmd = desktop.launcher_command()
        for flag, text in (("--region", "Região"), ("--fullscreen", "Tela inteira"),
                           ("--window", "Janela ativa"), ("--monitor", "Monitor atual"),
                           ("--record", "Gravar vídeo / parar"), ("--record-gif", "Gravar GIF / parar"),
                           ("--show", "Abrir janela")):
            full = f"{cmd} {flag}"
            copy = Gtk.Button.new_from_icon_name("edit-copy-symbolic", Gtk.IconSize.BUTTON)
            copy.set_tooltip_text("Copiar comando")
            copy.connect("clicked", lambda _b, c=full: (utils.copy_text(c),
                                                        self.window.toast("Comando copiado")))
            row = Gtk.Box(spacing=8)
            cmd_label = label(flag, "monospace")
            row.pack_start(cmd_label, False, False, 0)
            row.pack_start(copy, False, False, 0)
            g.add_row(text, None, row)
        box.pack_start(g, False, False, 0)
        self.refresh_hotkeys()
        return box

    def _set_hotkey(self, action, accel):
        if accel:
            for other, value in self.cfg["hotkeys"].items():
                if other != action and value == accel:
                    self.cfg.set_hotkey(other, "")
                    self.hk_buttons[other].set_accel("")
        self.cfg.set_hotkey(action, accel)

    def _reset_hotkeys(self):
        self.cfg.set("hotkeys", dict(DEFAULT_HOTKEYS))
        for action, btn in self.hk_buttons.items():
            btn.set_accel(DEFAULT_HOTKEYS.get(action, ""))

    def refresh_hotkeys(self):
        if not hasattr(self, "hk_status"):
            return
        hk = self.app.hotkeys
        for action, img in self.hk_status.items():
            accel = self.cfg["hotkeys"].get(action, "")
            ok = hk.status.get(action)
            if not accel:
                img.clear()
                img.set_tooltip_text(None)
            elif ok:
                img.set_from_icon_name("emblem-ok-symbolic", Gtk.IconSize.BUTTON)
                img.set_tooltip_text("Ativo")
            else:
                img.set_from_icon_name("dialog-warning-symbolic", Gtk.IconSize.BUTTON)
                img.set_tooltip_text("Não foi possível registrar: a combinação está em uso por "
                                     "outro programa ou pelo sistema")
            btn = self.hk_buttons.get(action)
            if btn and btn.accel != accel:
                btn.set_accel(accel)
        conflicts = self.app.system_conflicts()
        failed = [a for a in hk.failed()]
        if conflicts:
            self.conflict_label.set_text("Em uso pelo sistema:\n" + "\n".join(desktop.describe(conflicts)))
        elif failed:
            self.conflict_label.set_text("Algumas combinações estão em uso por outro programa. "
                                         "Escolha outra tecla para elas.")
        else:
            self.conflict_label.set_text("Nenhum conflito. Todos os atalhos estão ativos.")
        self.release_btn.set_sensitive(bool(conflicts))
        self.restore_btn.set_sensitive(bool(self.cfg["released_system_keys"]))

    # ------------------------------------------------------------- Avançado
    def _advanced(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        g = PrefGroup("Histórico")
        g.spin(self.cfg, "history_limit", "Máximo de itens no histórico", 50, 10000, 50)
        prune = Gtk.Button(label="Limpar ausentes")
        prune.connect("clicked", lambda *_: (self.app.history.prune_missing(),
                                             self.window.toast("Itens ausentes removidos")))
        g.add_row("Remover itens cujo arquivo não existe mais", None, prune)
        clear = Gtk.Button(label="Limpar histórico")
        clear.get_style_context().add_class("destructive-action")
        clear.connect("clicked", lambda *_: self._clear_history())
        g.add_row("Limpar todo o histórico", "Os arquivos no disco NÃO são apagados", clear)
        box.pack_start(g, False, False, 0)

        g = PrefGroup("Pastas")
        for text, path in (("Configurações", paths.CONFIG_DIR), ("Dados", paths.DATA_DIR),
                           ("Cache (miniaturas)", paths.CACHE_DIR)):
            btn = Gtk.Button(label="Abrir")
            btn.connect("clicked", lambda _b, p=path: utils.open_folder(p))
            g.add_row(text, path.replace(os.path.expanduser("~"), "~"), btn)
        box.pack_start(g, False, False, 0)

        g = PrefGroup("Sobre")
        g.add_row(f"{APP_NAME} {VERSION}", "Captura de tela e gravação para Linux", None)
        session = "Wayland" if utils.is_wayland() else "X11"
        tray = getattr(self.app.tray, "backend", None) or "—"
        g.add_row("Ambiente", f"Sessão {session} • bandeja: {tray} • "
                              f"ffmpeg: {'ok' if utils.which('ffmpeg') else 'não encontrado'}", None)
        box.pack_start(g, False, False, 0)
        return box

    def _clear_history(self):
        resp = dialog_message(self.window, "Limpar o histórico?",
                              "A lista será esvaziada. Os arquivos continuarão nas pastas.",
                              Gtk.MessageType.QUESTION,
                              [("Cancelar", Gtk.ResponseType.CANCEL), ("Limpar", Gtk.ResponseType.OK)])
        if resp == Gtk.ResponseType.OK:
            self.app.history.clear()


def _info_bar(text):
    box = Gtk.Box(spacing=10)
    box.get_style_context().add_class("info-box")
    box.set_margin_bottom(14)
    box.pack_start(Gtk.Image.new_from_icon_name("dialog-information-symbolic", Gtk.IconSize.BUTTON),
                   False, False, 0)
    box.pack_start(label(text, wrap=True), True, True, 0)
    return box
