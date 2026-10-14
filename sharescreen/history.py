"""Histórico de capturas/gravações + gerador de miniaturas em segundo plano."""
import datetime
import json
import os
import queue
import subprocess
import threading
import uuid

from gi.repository import GdkPixbuf, GLib

from . import paths, utils

THUMB_W, THUMB_H = 320, 200


class History:
    def __init__(self, limit=2000):
        paths.ensure_dirs()
        self.path = os.path.join(paths.DATA_DIR, "history.json")
        self.limit = limit
        self.items = []
        self._listeners = []
        self._save_id = 0
        try:
            with open(self.path, encoding="utf-8") as f:
                self.items = [i for i in json.load(f) if isinstance(i, dict) and "path" in i]
        except (OSError, ValueError):
            self.items = []

    def connect(self, cb):
        self._listeners.append(cb)

    def _changed(self):
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(300, self._save)
        for cb in list(self._listeners):
            cb()

    def _save(self):
        self._save_id = 0
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.path)
        return False

    def flush(self):
        if self._save_id:
            GLib.source_remove(self._save_id)
            self._save()

    def add(self, path, kind, width=0, height=0, duration=None):
        entry = {
            "id": uuid.uuid4().hex,
            "path": path,
            "kind": kind,  # image | video | gif
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "width": width,
            "height": height,
            "duration": duration,
        }
        self.items.insert(0, entry)
        for old in self.items[self.limit:]:
            remove_thumb(old)
        del self.items[self.limit:]
        self._changed()
        return entry

    def get(self, entry_id):
        return next((i for i in self.items if i["id"] == entry_id), None)

    def update(self, entry, **changes):
        entry.update(changes)
        remove_thumb(entry)
        self._changed()

    def remove(self, entry):
        if entry in self.items:
            self.items.remove(entry)
            remove_thumb(entry)
            self._changed()

    def clear(self):
        for e in self.items:
            remove_thumb(e)
        self.items = []
        self._changed()

    def entries(self, kind=None, query=None):
        q = (query or "").lower().strip()
        out = []
        for e in self.items:
            if kind and e["kind"] != kind:
                continue
            if q and q not in os.path.basename(e["path"]).lower():
                continue
            out.append(e)
        return out

    def prune_missing(self):
        before = len(self.items)
        keep = [e for e in self.items if os.path.exists(e["path"])]
        if len(keep) != before:
            for e in self.items:
                if e not in keep:
                    remove_thumb(e)
            self.items = keep
            self._changed()


def thumb_path(entry):
    return os.path.join(paths.THUMBS_DIR, entry["id"] + ".png")


def remove_thumb(entry):
    try:
        os.remove(thumb_path(entry))
    except OSError:
        pass


class ThumbnailLoader:
    """Gera/carrega miniaturas numa thread e entrega via callback no loop principal."""

    def __init__(self):
        self._q = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def request(self, entry, callback, size=(THUMB_W, THUMB_H)):
        self._q.put((dict(entry), callback, size))

    def _run(self):
        while True:
            entry, callback, size = self._q.get()
            try:
                pixbuf = self._load(entry, size)
            except (GLib.Error, OSError, subprocess.SubprocessError):
                pixbuf = None
            GLib.idle_add(_deliver, callback, pixbuf)

    def _load(self, entry, size):
        tpath = thumb_path(entry)
        src = entry["path"]
        if not os.path.exists(src):
            return None
        if not (os.path.exists(tpath) and os.path.getmtime(tpath) >= os.path.getmtime(src)):
            if entry["kind"] == "video":
                if not utils.which("ffmpeg"):
                    return None
                seek = "0.5" if (entry.get("duration") or 1) > 1 else "0"
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", seek,
                                "-i", src, "-frames:v", "1", "-vf",
                                f"scale={THUMB_W * 2}:-2", tpath],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
                               check=False)
                if not os.path.exists(tpath):
                    return None
            else:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(src, THUMB_W * 2, THUMB_H * 2, True)
                pb.savev(tpath, "png", [], [])
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(tpath, size[0], size[1], True)


def _deliver(callback, pixbuf):
    callback(pixbuf)
    return False
