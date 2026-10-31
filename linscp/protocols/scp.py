"""SCP backend: shell commands for browsing + the classic SCP protocol for transfers.

Works on servers without an SFTP subsystem (Dropbear on routers / Android boxes,
BusyBox userlands…), like WinSCP's SCP mode.
"""
from __future__ import annotations

import calendar
import os
import posixpath
import re
import shlex
import time

from .base import CHUNK, Entry, RemoteFS, parse_perm_string
from .ssh_common import open_ssh

q = shlex.quote

_LINE = re.compile(
    r"^([\-dlbcpsDw?][rwxsStTl\-]{9})[.+@]?\s+\d+\s+(\S+)\s+(\S+)\s+(?:\d+,\s*)?(\d+)\s+(.*)$")
_FULL = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:\.\d+)?(?: ([+-]\d{4}))? (.*)$")
_BBFULL = re.compile(r"^\w{3} (\w{3}) +(\d+) (\d{2}):(\d{2}):(\d{2}) (\d{4}) (.*)$")
_CLASSIC = re.compile(r"^(\w{3}) +(\d+) +(\d{1,2}:\d{2}|\d{4}) (.*)$")
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def parse_ls_line(line: str):
    m = _LINE.match(line)
    if not m:
        return None
    perms, owner, group, size, rest = m.groups()
    mtime = None
    name = None
    f = _FULL.match(rest)
    if f:
        t = time.strptime(f.group(1), "%Y-%m-%d %H:%M:%S")
        mtime = float(calendar.timegm(t))
        if f.group(2):
            off = int(f.group(2)[1:3]) * 3600 + int(f.group(2)[3:5]) * 60
            mtime -= off if f.group(2)[0] == "+" else -off
        name = f.group(3)
    else:
        b = _BBFULL.match(rest)
        if b and b.group(1) in _MONTHS:
            mon, day, hh, mm, ss, yr, name = b.groups()
            mtime = time.mktime((int(yr), _MONTHS[mon], int(day), int(hh), int(mm), int(ss), 0, 0, -1))
        else:
            c = _CLASSIC.match(rest)
            if not c or c.group(1) not in _MONTHS:
                return None
            mon, day, yt, name = c.groups()
            now = time.localtime()
            if ":" in yt:
                hh, mm = map(int, yt.split(":"))
                yr = now.tm_year
                ts = time.mktime((yr, _MONTHS[mon], int(day), hh, mm, 0, 0, 0, -1))
                if ts > time.time() + 86400:     # "Dec 31 23:00" seen in January
                    ts = time.mktime((yr - 1, _MONTHS[mon], int(day), hh, mm, 0, 0, 0, -1))
                mtime = ts
            else:
                mtime = time.mktime((int(yt), _MONTHS[mon], int(day), 0, 0, 0, 0, 0, -1))
    kind = perms[0]
    target = ""
    if kind == "l" and " -> " in name:
        name, target = name.split(" -> ", 1)
    return Entry(name=name, is_dir=kind == "d", size=int(size), mtime=mtime,
                 mode=parse_perm_string(perms), owner=owner, group=group,
                 is_link=kind == "l", link_target=target)


class SCPError(IOError):
    pass


class SCPFS(RemoteFS):
    supports_resume = False

    def connect(self):
        self.client = open_ssh(self.site, self.trust_cb)
        self._full_time = None   # learnt on first listing

    def close(self):
        try:
            self.client.close()
        except Exception:
            pass

    def is_alive(self):
        t = self.client.get_transport() if getattr(self, "client", None) else None
        return bool(t and t.is_active())

    # ------------------------------------------------------------------ shell
    def _exec(self, cmd: str):
        """Open a channel and run cmd. Dropbear sometimes refuses a channel opened right after
        another one closed: retry a few times before giving up."""
        import paramiko
        last = None
        for attempt in range(6):
            chan = None
            try:
                chan = self.client.get_transport().open_session(timeout=15)
                chan.exec_command(cmd)
                return chan
            except paramiko.SSHException as e:
                last = e
                if chan is not None:
                    try:
                        chan.close()
                    except Exception:
                        pass
                t = self.client.get_transport()
                if t is None or not t.is_active():
                    raise
                time.sleep(0.05 * (attempt + 1))
        raise last

    @staticmethod
    def _finish(chan):
        """Wait for the remote command to end so the server frees the channel."""
        try:
            chan.shutdown_write()
        except Exception:
            pass
        try:
            chan.status_event.wait(5)   # bounded: a cancelled transfer must not hang here
        except Exception:
            pass
        chan.close()

    def run(self, cmd: str, check: bool = True) -> tuple[int, str, str]:
        chan = self._exec(cmd)
        out, err = bytearray(), bytearray()
        while True:
            if chan.recv_ready():
                out += chan.recv(65536)
            elif chan.recv_stderr_ready():
                err += chan.recv_stderr(65536)
            elif chan.exit_status_ready() and not chan.recv_ready() and not chan.recv_stderr_ready():
                break
            else:
                time.sleep(0.005)
        rc = chan.recv_exit_status()
        chan.close()
        o, e = out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
        if check and rc != 0:
            raise SCPError(e.strip() or f"exit status {rc}")
        return rc, o, e

    def home(self):
        return self.run("pwd")[1].strip() or "/"

    def normalize(self, path):
        rc, out, _ = self.run(f"cd {q(path)} && pwd", check=False)
        if rc != 0:
            raise SCPError(f"{path}: No such directory")
        return out.strip() or posixpath.normpath(path)

    def _ls(self, args: str, path: str) -> list[str]:
        if self._full_time is not False:
            rc, out, err = self.run(f"LC_ALL=C ls {args} --full-time {q(path)}", check=False)
            low = err.lower()
            unsupported = any(w in low for w in ("unrecognized", "invalid option", "unknown option",
                                                 "illegal option", "usage:"))
            if not unsupported:
                if rc != 0 and not out:
                    raise SCPError(err.strip() or f"ls failed on {path}")
                self._full_time = True
                return out.splitlines()
            self._full_time = False
        rc, out, err = self.run(f"LC_ALL=C ls {args} {q(path)}", check=False)
        if rc != 0 and not out:
            raise SCPError(err.strip() or f"ls failed on {path}")
        return out.splitlines()

    def listdir(self, path):
        lines = self._ls("-lA", path.rstrip("/") + "/")
        entries = [e for e in (parse_ls_line(l) for l in lines) if e and e.name not in (".", "..")]
        links = [e for e in entries if e.is_link]
        if links:
            names = " ".join(q(e.name) for e in links)
            _, out, _ = self.run(
                f"cd {q(path)} && for f in {names}; do [ -d \"$f\" ] && printf '%s\\n' \"$f\"; done; true",
                check=False)
            dirs = set(out.splitlines())
            for e in links:
                e.is_dir = e.name in dirs
        return entries

    def stat(self, path):
        try:
            lines = self._ls("-ldA", path)
        except SCPError:
            return None
        for l in lines:
            e = parse_ls_line(l)
            if e:
                e.name = posixpath.basename(path.rstrip("/")) or "/"
                return e
        return None

    def mkdir(self, path): self.run(f"mkdir {q(path)}")
    def remove(self, path): self.run(f"rm -f {q(path)}")
    def rmdir(self, path): self.run(f"rmdir {q(path)}")
    def remove_tree(self, path): self.run(f"rm -rf {q(path)}")
    def rename(self, src, dst): self.run(f"mv -f {q(src)} {q(dst)}")
    def chmod(self, path, mode): self.run(f"chmod {mode:o} {q(path)}")

    def set_mtime(self, path, mtime):
        stamp = time.strftime("%Y%m%d%H%M.%S", time.gmtime(mtime))
        self.run(f"TZ=UTC0 touch -t {stamp} {q(path)}", check=False)

    # --------------------------------------------------------------- protocol
    @staticmethod
    def _ack(chan):
        b = chan.recv(1)
        if b == b"\0":
            return
        if not b:
            raise SCPError("Connection closed by the remote scp")
        msg = SCPFS._readline(chan)
        raise SCPError(msg.strip() or "scp error")

    @staticmethod
    def _readline(chan) -> str:
        buf = bytearray()
        while True:
            c = chan.recv(1)
            if not c or c == b"\n":
                break
            buf += c
        return buf.decode("utf-8", "replace")

    def download(self, remote, local, progress, offset=0):
        chan = self._exec(f"scp -pf {q(remote)}")
        try:
            chan.sendall(b"\0")
            mtime = None
            while True:
                first = chan.recv(1)
                if not first:
                    raise SCPError("No answer from remote scp (is scp installed on the server?)")
                if first in (b"\x01", b"\x02"):
                    raise SCPError(self._readline(chan).strip())
                line = self._readline(chan)
                if first == b"T":
                    mtime = float(line.split()[0])
                    chan.sendall(b"\0")
                    continue
                if first == b"C":
                    size = int(line.split(" ", 2)[1])
                    break
                raise SCPError(f"Unexpected scp reply: {first!r}{line}")
            chan.sendall(b"\0")
            done = 0
            with open(local, "wb") as lf:
                while done < size:
                    data = chan.recv(min(CHUNK, size - done))
                    if not data:
                        raise SCPError("Connection lost during transfer")
                    lf.write(data)
                    done += len(data)
                    progress(done)
            self._ack(chan)
            chan.sendall(b"\0")
            if mtime:
                os.utime(local, (mtime, mtime))
        except BaseException:
            chan.close()          # cancelled / failed: don't wait for the remote scp
            raise
        self._finish(chan)

    def upload(self, local, remote, progress, offset=0):
        st = os.stat(local)
        chan = self._exec(f"scp -pt {q(remote)}")
        try:
            self._ack(chan)
            chan.sendall(f"T{int(st.st_mtime)} 0 {int(st.st_atime)} 0\n".encode())
            self._ack(chan)
            name = posixpath.basename(remote).replace("\n", "_")
            chan.sendall(f"C{st.st_mode & 0o7777:04o} {st.st_size} {name}\n".encode())
            self._ack(chan)
            done = 0
            with open(local, "rb") as lf:
                while True:
                    data = lf.read(CHUNK)
                    if not data:
                        break
                    chan.sendall(data)
                    done += len(data)
                    progress(done)
            chan.sendall(b"\0")
            self._ack(chan)
        except BaseException:
            chan.close()
            raise
        self._finish(chan)
