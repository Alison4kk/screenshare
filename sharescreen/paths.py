import os

from gi.repository import GLib

CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "sharescreen")
DATA_DIR = os.path.join(GLib.get_user_data_dir(), "sharescreen")
CACHE_DIR = os.path.join(GLib.get_user_cache_dir(), "sharescreen")
THUMBS_DIR = os.path.join(CACHE_DIR, "thumbs")

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
RES_DIR = os.path.join(PKG_DIR, "data")


def resource(name):
    return os.path.join(RES_DIR, name)


def ensure_dirs():
    for d in (CONFIG_DIR, DATA_DIR, CACHE_DIR, THUMBS_DIR):
        os.makedirs(d, exist_ok=True)


def _special(kind, fallback):
    path = GLib.get_user_special_dir(kind)
    if not path or os.path.realpath(path) == os.path.realpath(os.path.expanduser("~")):
        path = os.path.join(os.path.expanduser("~"), fallback)
    return path


def default_pictures_dir():
    return os.path.join(_special(GLib.UserDirectory.DIRECTORY_PICTURES, "Pictures"), "ShareScreen")


def default_videos_dir():
    return os.path.join(_special(GLib.UserDirectory.DIRECTORY_VIDEOS, "Videos"), "ShareScreen")
