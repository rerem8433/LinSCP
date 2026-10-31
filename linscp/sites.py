"""Saved sites (JSON) + passwords in the system keyring (Secret Service / GNOME Keyring / KWallet)."""
from __future__ import annotations

import json
import os
import uuid

from .config import CONFIG_DIR
from .protocols import Site

SITES_FILE = os.path.join(CONFIG_DIR, "sites.json")
KEYRING_SERVICE = "LinSCP"

try:
    import keyring  # type: ignore
    from keyring.backends import fail as _fail  # type: ignore
    HAVE_KEYRING = not isinstance(keyring.get_keyring(), _fail.Keyring)
except Exception:  # pragma: no cover
    keyring = None
    HAVE_KEYRING = False


class SiteStore:
    def __init__(self):
        self.sites: dict[str, Site] = {}   # id -> Site
        self.load()

    def load(self):
        self.sites.clear()
        try:
            with open(SITES_FILE) as f:
                data = json.load(f)
        except Exception:
            return
        for item in data.get("sites", []):
            sid = item.pop("id", None) or uuid.uuid4().hex
            self.sites[sid] = Site.from_dict(item)

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = {"version": 1, "sites": [dict(id=sid, **s.to_dict()) for sid, s in self.sites.items()]}
        tmp = SITES_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, SITES_FILE)

    def ordered(self):
        return sorted(self.sites.items(), key=lambda kv: kv[1].label().lower())

    def put(self, site: Site, sid: str | None = None) -> str:
        sid = sid or uuid.uuid4().hex
        self.sites[sid] = site
        if site.save_password and site.password:
            set_password(sid, site.password)
        elif not site.save_password:
            delete_password(sid)
        self.save()
        return sid

    def delete(self, sid: str):
        self.sites.pop(sid, None)
        delete_password(sid)
        self.save()


def get_password(sid: str) -> str:
    if not HAVE_KEYRING:
        return ""
    try:
        return keyring.get_password(KEYRING_SERVICE, sid) or ""
    except Exception:
        return ""


def set_password(sid: str, pw: str) -> bool:
    if not HAVE_KEYRING:
        return False
    try:
        keyring.set_password(KEYRING_SERVICE, sid, pw)
        return True
    except Exception:
        return False


def delete_password(sid: str):
    if not HAVE_KEYRING:
        return
    try:
        keyring.delete_password(KEYRING_SERVICE, sid)
    except Exception:
        pass
