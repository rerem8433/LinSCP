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
    _kr = keyring.get_keyring()
    HAVE_KEYRING = not isinstance(_kr, _fail.Keyring) and "null" not in type(_kr).__module__
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


# --------------------------------------------------------------------------- passwords
# System keyring (Secret Service: GNOME Keyring / KWallet) when available. Otherwise
# (python3-keyring missing, no Secret Service running…) fall back to a local file readable
# only by the user (chmod 600), like WinSCP's own password storage: obfuscated, not encrypted.
PASSWORDS_FILE = os.path.join(CONFIG_DIR, "passwords.json")


def storage_name() -> str:
    return "keyring" if HAVE_KEYRING else "file"


def _key() -> bytes:
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(p) as f:
                return (f.read().strip() + "LinSCP").encode()
        except OSError:
            pass
    return b"LinSCP"


def _xor(data: bytes) -> bytes:
    k = _key()
    return bytes(b ^ k[i % len(k)] for i, b in enumerate(data))


def _file_load() -> dict:
    try:
        with open(PASSWORDS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _file_save(d: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = PASSWORDS_FILE + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(d, f)
    os.replace(tmp, PASSWORDS_FILE)


def _file_get(sid):
    import base64
    v = _file_load().get(sid)
    if not v:
        return ""
    try:
        return _xor(base64.b64decode(v)).decode()
    except Exception:
        return ""


def _file_set(sid, pw):
    import base64
    d = _file_load()
    d[sid] = base64.b64encode(_xor(pw.encode())).decode()
    _file_save(d)


def _file_del(sid):
    d = _file_load()
    if d.pop(sid, None) is not None:
        _file_save(d)


def get_password(sid: str) -> str:
    if HAVE_KEYRING:
        try:
            pw = keyring.get_password(KEYRING_SERVICE, sid)
            if pw:
                return pw
        except Exception:
            pass
    return _file_get(sid)


def set_password(sid: str, pw: str) -> bool:
    if HAVE_KEYRING:
        try:
            keyring.set_password(KEYRING_SERVICE, sid, pw)
            _file_del(sid)
            return True
        except Exception:   # keyring locked / refused: keep it locally instead
            pass
    _file_set(sid, pw)
    return True


def delete_password(sid: str):
    if HAVE_KEYRING:
        try:
            keyring.delete_password(KEYRING_SERVICE, sid)
        except Exception:
            pass
    _file_del(sid)
