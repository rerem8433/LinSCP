"""FTP / FTPS (explicit & implicit) backend (ftplib)."""
from __future__ import annotations

import calendar
import ftplib
import hashlib
import json
import os
import posixpath
import re
import ssl
import time

from ..config import CONFIG_DIR
from .base import CHUNK, Entry, RemoteFS
from .scp import parse_ls_line

KNOWN_CERTS = os.path.join(CONFIG_DIR, "known_certs.json")

_DOS = re.compile(r"^(\d{2})-(\d{2})-(\d{2,4})\s+(\d{1,2}):(\d{2})(AM|PM)?\s+(<DIR>|\d+)\s+(.*)$", re.I)


def _tls_context() -> ssl.SSLContext:
    # Trust is decided by fingerprint (trust on first use), like SSH host keys:
    # most home servers / NAS use self-signed certificates.
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _open_data(ftp, cmd, rest=None):
    """Open the data connection. If the server answers 425 (it cannot reach us in active
    mode, or our passive connection failed), switch active <-> passive once and retry."""
    try:
        return ftplib.FTP.ntransfercmd(ftp, cmd, rest)
    except (ftplib.error_temp, OSError) as e:
        if getattr(ftp, "_mode_switched", False):
            raise
        refused_active = isinstance(e, ftplib.error_temp) and str(e).startswith("425")
        failed_passive = not isinstance(e, ftplib.Error) and ftp.passiveserver
        if not (refused_active or failed_passive):
            raise
        ftp._mode_switched = True
        ftp.set_pasv(not ftp.passiveserver)
        return ftplib.FTP.ntransfercmd(ftp, cmd, rest)


class _PlainFTP(ftplib.FTP):
    def ntransfercmd(self, cmd, rest=None):
        return _open_data(self, cmd, rest)


class _ExplicitTLS(ftplib.FTP_TLS):
    def ntransfercmd(self, cmd, rest=None):
        # Reuse the control-channel TLS session on data channels (vsftpd/ProFTPD require it)
        conn, size = _open_data(self, cmd, rest)
        if self._prot_p:
            sess = getattr(self.sock, "session", None)
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=sess)
        return conn, size


class _ImplicitTLS(_ExplicitTLS):
    _sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value, server_hostname=self.host)
        self._sock = value


def _load_certs() -> dict:
    try:
        with open(KNOWN_CERTS) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cert(hid: str, fp: str) -> None:
    d = _load_certs()
    d[hid] = fp
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(KNOWN_CERTS, "w") as f:
        json.dump(d, f, indent=1)


def _parse_dos(line: str):
    m = _DOS.match(line)
    if not m:
        return None
    mo, d, y, hh, mi, ampm, sz, name = m.groups()
    y = int(y)
    y = y + 2000 if y < 70 else (y + 1900 if y < 100 else y)
    hh = int(hh) % 12 + (12 if ampm and ampm.upper() == "PM" else 0) if ampm else int(hh)
    ts = time.mktime((y, int(mo), int(d), hh, int(mi), 0, 0, 0, -1))
    is_dir = sz.upper() == "<DIR>"
    return Entry(name=name, is_dir=is_dir, size=0 if is_dir else int(sz), mtime=ts)


def _mlsd_time(v: str):
    try:
        return float(calendar.timegm(time.strptime(v[:14], "%Y%m%d%H%M%S")))
    except Exception:
        return None


class FTPFS(RemoteFS):
    def connect(self):
        s = self.site
        proto = s.protocol
        if proto == "ftp":
            ftp = _PlainFTP(timeout=20)
        elif proto == "ftps":
            ftp = _ExplicitTLS(context=_tls_context(), timeout=20)
        else:
            ftp = _ImplicitTLS(context=_tls_context(), timeout=20)
        ftp.encoding = "utf-8"
        ftp.connect(s.host, s.effective_port())
        if proto == "ftps":
            ftp.auth()
        if proto != "ftp":
            self._check_cert(ftp)
        ftp.login(s.user or "anonymous", s.password or ("anonymous@" if not s.user else ""))
        if proto != "ftp":
            ftp.prot_p()
        ftp.set_pasv(bool(s.passive))
        try:
            ftp.sendcmd("OPTS UTF8 ON")
        except ftplib.all_errors:
            pass
        ftp.voidcmd("TYPE I")
        self.feat = set()
        try:
            for line in ftp.sendcmd("FEAT").splitlines()[1:]:
                self.feat.add(line.strip().split(" ")[0].upper())
        except ftplib.all_errors:
            pass
        self.ftp = ftp

    def _check_cert(self, ftp):
        der = ftp.sock.getpeercert(binary_form=True) or b""
        fp = "SHA256:" + ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest())
        hid = f"{self.site.host}:{self.site.effective_port()}"
        known = _load_certs().get(hid)
        if known == fp:
            return
        if self.trust_cb is None or not self.trust_cb("tls", hid, fp, known is not None):
            ftp.close()
            raise ssl.SSLError("Certificate rejected by user")
        _save_cert(hid, fp)

    def close(self):
        ftp = getattr(self, "ftp", None)
        if ftp:
            try:
                ftp.quit()
            except Exception:
                try:
                    ftp.close()
                except Exception:
                    pass

    def is_alive(self):
        try:
            self.ftp.voidcmd("NOOP")
            return True
        except Exception:
            return False

    def home(self):
        return self.ftp.pwd() or "/"

    def normalize(self, path):
        self.ftp.cwd(path)
        return self.ftp.pwd()

    def listdir(self, path):
        if "MLSD" in self.feat or "MLST" in self.feat:
            try:
                return self._mlsd(path)
            except ftplib.error_perm:
                pass
        lines: list[str] = []
        self.ftp.retrlines(f"LIST -a {path}" if not " " in path else f"LIST {path}", lines.append)
        if not lines:   # some servers reject "-a"
            self.ftp.retrlines(f"LIST {path}", lines.append)
        out = []
        for l in lines:
            e = parse_ls_line(l) or _parse_dos(l)
            if e and e.name not in (".", ".."):
                out.append(e)
        for e in out:
            if e.is_link:
                e.is_dir = self._is_dir(posixpath.join(path, e.name))
        return out

    def _is_dir(self, p):
        try:
            cur = self.ftp.pwd()
            self.ftp.cwd(p)
            self.ftp.cwd(cur)
            return True
        except ftplib.all_errors:
            return False

    def _mlsd(self, path):
        out = []
        for name, f in self.ftp.mlsd(path, facts=["type", "size", "modify", "unix.mode",
                                                  "unix.owner", "unix.group", "unix.uid", "unix.gid"]):
            t = f.get("type", "").lower()
            if t in ("cdir", "pdir") or name in (".", ".."):
                continue
            link = t.startswith("os.unix=slink") or t.startswith("os.unix=symlink")
            e = Entry(name=name, is_dir=t == "dir", size=int(f.get("size", 0) or 0),
                      mtime=_mlsd_time(f.get("modify", "")),
                      owner=f.get("unix.owner", f.get("unix.uid", "")),
                      group=f.get("unix.group", f.get("unix.gid", "")), is_link=link)
            if "unix.mode" in f:
                try:
                    e.mode = int(f["unix.mode"], 8) & 0o7777
                except ValueError:
                    pass
            if link:
                e.link_target = t.split(":", 1)[1] if ":" in t else ""
                e.is_dir = self._is_dir(posixpath.join(path, name))
            out.append(e)
        return out

    def stat(self, path):
        if "MLST" in self.feat:
            try:
                resp = self.ftp.sendcmd(f"MLST {path}")
            except ftplib.error_perm:
                return None
            for line in resp.splitlines()[1:-1]:
                facts, _, _ = line.strip().partition(" ")
                f = dict(x.split("=", 1) for x in facts.split(";") if "=" in x)
                f = {k.lower(): v for k, v in f.items()}
                e = Entry(name=posixpath.basename(path.rstrip("/")) or "/",
                          is_dir=f.get("type", "").lower() in ("dir", "cdir"),
                          size=int(f.get("size", 0) or 0), mtime=_mlsd_time(f.get("modify", "")))
                return e
            return None
        return super().stat(path)

    def mkdir(self, path): self.ftp.mkd(path)
    def remove(self, path): self.ftp.delete(path)
    def rmdir(self, path): self.ftp.rmd(path)
    def rename(self, src, dst): self.ftp.rename(src, dst)
    def chmod(self, path, mode): self.ftp.voidcmd(f"SITE CHMOD {mode:o} {path}")

    def set_mtime(self, path, mtime):
        if "MFMT" in self.feat:
            try:
                self.ftp.voidcmd(f"MFMT {time.strftime('%Y%m%d%H%M%S', time.gmtime(mtime))} {path}")
            except ftplib.all_errors:
                pass

    def download(self, remote, local, progress, offset=0):
        done = [offset]
        with open(local, "r+b" if offset else "wb") as lf:
            if offset:
                lf.seek(offset)
                lf.truncate()

            def cb(data):
                lf.write(data)
                done[0] += len(data)
                progress(done[0])
            self.ftp.retrbinary(f"RETR {remote}", cb, CHUNK, rest=offset or None)

    def upload(self, local, remote, progress, offset=0):
        done = [offset]

        def cb(data):
            done[0] += len(data)
            progress(done[0])
        with open(local, "rb") as lf:
            if offset:
                lf.seek(offset)
                self.ftp.storbinary(f"APPE {remote}", lf, CHUNK, cb)
            else:
                self.ftp.storbinary(f"STOR {remote}", lf, CHUNK, cb)
