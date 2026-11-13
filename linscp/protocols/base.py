"""Common API shared by every protocol backend."""
from __future__ import annotations

import posixpath
import stat as statmod
from dataclasses import dataclass, field
from typing import Callable, Optional

CHUNK = 64 * 1024


class Cancelled(Exception):
    """Raised when the user cancels a transfer."""


class ConnectionLost(Exception):
    """Raised when the remote side dropped the connection."""


@dataclass
class Entry:
    name: str
    is_dir: bool
    size: int = 0
    mtime: Optional[float] = None
    mode: Optional[int] = None          # permission bits (0o755…)
    owner: str = ""
    group: str = ""
    is_link: bool = False
    link_target: str = ""

    @property
    def perms(self) -> str:
        if self.mode is None:
            return ""
        out = "d" if self.is_dir else ("l" if self.is_link else "-")
        for who in (6, 3, 0):
            bits = (self.mode >> who) & 7
            out += ("r" if bits & 4 else "-") + ("w" if bits & 2 else "-") + ("x" if bits & 1 else "-")
        return out


# progress(done_bytes) -> None ; raise Cancelled to stop
Progress = Callable[[int], None]


def parse_perm_string(s: str) -> Optional[int]:
    """'drwxr-xr-x' -> 0o755"""
    if len(s) < 10:
        return None
    mode = 0
    for i, ch in enumerate(s[1:10]):
        if ch not in "-":
            mode |= 1 << (8 - i)
    # setuid/setgid/sticky shown as s/S/t/T: keep only rwx semantics
    for idx, bit in ((3, 0o100), (6, 0o010), (9, 0o001)):
        if s[idx] in "ST":
            mode &= ~bit
    return mode


@dataclass
class Site:
    name: str = ""
    protocol: str = "sftp"          # sftp | scp | ftp | ftps | ftps-implicit
    host: str = ""
    port: int = 0
    user: str = ""
    auth: str = "password"          # password | key
    key_file: str = ""
    remote_dir: str = ""
    local_dir: str = ""
    passive: bool = True
    save_password: bool = False
    notes: str = ""
    password: str = field(default="", repr=False, compare=False)

    def default_port(self) -> int:
        return {"sftp": 22, "scp": 22, "ftp": 21, "ftps": 21, "ftps-implicit": 990}.get(self.protocol, 22)

    def effective_port(self) -> int:
        return self.port or self.default_port()

    def label(self) -> str:
        if self.name:
            return self.name
        u = f"{self.user}@" if self.user else ""
        return f"{u}{self.host}"

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d.pop("password", None)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Site":
        s = cls()
        for k, v in d.items():
            if hasattr(s, k) and k != "password":
                setattr(s, k, v)
        return s


class RemoteFS:
    """Abstract remote filesystem. All paths are absolute POSIX paths."""

    supports_resume = True
    supports_chmod = True

    def __init__(self, site: Site, trust_cb=None):
        self.site = site
        # trust_cb(kind, host, fingerprint, changed) -> bool  (kind: 'ssh'|'tls')
        self.trust_cb = trust_cb

    # --- life-cycle -------------------------------------------------------
    def connect(self) -> None: ...
    def close(self) -> None: ...
    def is_alive(self) -> bool: return True

    # --- browsing ---------------------------------------------------------
    def home(self) -> str: return "/"
    def normalize(self, path: str) -> str: return posixpath.normpath(path) or "/"
    def listdir(self, path: str) -> list[Entry]: raise NotImplementedError
    def stat(self, path: str) -> Optional[Entry]:
        parent, name = posixpath.split(path.rstrip("/") or "/")
        if not name:
            return Entry("/", True)
        for e in self.listdir(parent or "/"):
            if e.name == name:
                return e
        return None

    # --- modifications ----------------------------------------------------
    def mkdir(self, path: str) -> None: raise NotImplementedError
    def remove(self, path: str) -> None: raise NotImplementedError
    def rmdir(self, path: str) -> None: raise NotImplementedError
    def rename(self, src: str, dst: str) -> None: raise NotImplementedError
    def chmod(self, path: str, mode: int) -> None: raise NotImplementedError
    def set_mtime(self, path: str, mtime: float) -> None: pass

    def remove_tree(self, path: str) -> None:
        for e in self.listdir(path):
            p = posixpath.join(path, e.name)
            if e.is_dir and not e.is_link:
                self.remove_tree(p)
            else:
                self.remove(p)
        self.rmdir(path)

    def makedirs(self, path: str) -> None:
        parts = [p for p in path.split("/") if p]
        cur = ""
        for p in parts:
            cur += "/" + p
            st = None
            try:
                st = self.stat(cur)
            except Exception:
                pass
            if st is None:
                try:
                    self.mkdir(cur)
                except Exception:
                    st2 = self.stat(cur)
                    if st2 is None or not st2.is_dir:
                        raise

    # --- transfers --------------------------------------------------------
    def download(self, remote: str, local: str, progress: Progress, offset: int = 0) -> None:
        raise NotImplementedError

    def upload(self, local: str, remote: str, progress: Progress, offset: int = 0) -> None:
        raise NotImplementedError


def mode_from_stat(st_mode: int) -> int:
    return statmod.S_IMODE(st_mode)
