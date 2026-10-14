import copy
import json
import os

from gi.repository import GLib

from . import paths

DEFAULT_HOTKEYS = {
    "region": "<Control>Print",
    "fullscreen": "Print",
    "window": "<Alt>Print",
    "monitor": "",
    "last_region": "",
    "record": "<Shift>Print",
    "record_gif": "<Control><Shift>Print",
    "open_window": "",
}

# Ordem e rótulos usados na interface (atalhos, menu da bandeja, CLI).
ACTIONS = [
    ("region", "Capturar região"),
    ("fullscreen", "Capturar tela inteira"),
    ("window", "Capturar janela ativa"),
    ("monitor", "Capturar monitor atual"),
    ("last_region", "Capturar última região"),
    ("record", "Gravar vídeo (iniciar/parar)"),
    ("record_gif", "Gravar GIF (iniciar/parar)"),
    ("open_window", "Abrir janela principal"),
]
ACTION_LABELS = dict(ACTIONS)

DEFAULTS = {
    # Geral
    "config_version": 2,
    "first_run": True,
    "autostart": False,
    "close_to_tray": True,
    "tray_hint_shown": False,
    "theme": "system",  # system | dark | light
    "play_sound": True,
    # Captura
    "screenshots_dir": "",
    "videos_dir": "",
    "use_subfolders": True,
    "subfolder_pattern": "%Y-%m",
    "filename_pattern": "ShareScreen_%Y-%m-%d_%H-%M-%S",
    "image_format": "png",
    "jpeg_quality": 90,
    "capture_cursor": False,
    "capture_delay": 0,
    "hide_main_window": True,
    "region_magnifier": True,
    "region_crosshair": True,
    "region_detect_windows": True,
    "last_region": None,
    # Após captura
    "ac_save": True,
    "ac_clipboard": "image",  # image | path | none
    "ac_open_editor": False,
    "ac_notify": True,
    "ac_open_file": False,
    # Gravação
    "video_format": "mp4",  # mp4 | webm | mkv
    "video_fps": 30,
    "video_quality": "medium",  # high | medium | low
    "record_cursor": True,
    "audio_system": False,
    "audio_mic": False,
    "record_countdown": 3,
    "record_border": True,
    "record_toolbar": True,
    "gif_fps": 15,
    "gif_max_width": 0,
    "ar_clipboard": "file",  # file | path | none
    "ar_notify": True,
    "ar_open_file": False,
    # Atalhos
    "hotkeys": dict(DEFAULT_HOTKEYS),
    "released_system_keys": [],
    # Editor
    "editor_color": "#ff3b30",
    "editor_width": 4,
    # Histórico
    "history_limit": 2000,
}


class Config:
    def __init__(self):
        paths.ensure_dirs()
        self.path = os.path.join(paths.CONFIG_DIR, "config.json")
        self.data = copy.deepcopy(DEFAULTS)
        self._listeners = []
        self._save_id = 0
        self._load()
        if not self.data["screenshots_dir"]:
            self.data["screenshots_dir"] = paths.default_pictures_dir()
        if not self.data["videos_dir"]:
            self.data["videos_dir"] = paths.default_videos_dir()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
        except (OSError, ValueError):
            return
        for key, value in loaded.items():
            if key == "hotkeys" and isinstance(value, dict):
                self.data["hotkeys"].update(value)
            elif key in DEFAULTS:
                self.data[key] = value
        if loaded.get("config_version", 1) < 2:
            # v2: gravações passam a ir para a área de transferência como arquivo
            if self.data["ar_clipboard"] == "none":
                self.data["ar_clipboard"] = "file"
            self.data["config_version"] = 2

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        if self.data.get(key) == value:
            return
        self.data[key] = value
        self._schedule_save()
        for cb in list(self._listeners):
            cb(key, value)

    def set_hotkey(self, action, accel):
        hotkeys = dict(self.data["hotkeys"])
        hotkeys[action] = accel or ""
        self.set("hotkeys", hotkeys)

    def connect(self, callback):
        self._listeners.append(callback)

    def _schedule_save(self):
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(400, self._save_timeout)

    def _save_timeout(self):
        self._save_id = 0
        self.save()
        return False

    def save(self):
        if self._save_id:
            GLib.source_remove(self._save_id)
            self._save_id = 0
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)
