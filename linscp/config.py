"""Settings and paths."""
from __future__ import annotations

import json
import os

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "linscp")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

DEFAULTS = {
    "language": "",              # "" = follow system, "fr", "en"
    "layout": "dual",            # dual | single
    "theme": "system",           # system | light | dark
    "parallel": 2,               # simultaneous transfers
    "on_exists": "ask",          # ask | overwrite | resume | skip
    "show_hidden": False,
    "preserve_time": True,
    "confirm_delete": True,
    "local_dir": os.path.expanduser("~"),
    "window_geometry": "",
    "splitter": "",
}


class Settings(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        try:
            with open(SETTINGS_FILE) as f:
                self.update(json.load(f))
        except Exception:
            pass

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self, f, indent=1)
        os.replace(tmp, SETTINGS_FILE)


settings = Settings()
