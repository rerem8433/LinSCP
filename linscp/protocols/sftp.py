"""SFTP backend (paramiko)."""
from __future__ import annotations

import posixpath
import stat as statmod
import threading

import paramiko

from .base import CHUNK, Entry, RemoteFS, mode_from_stat
from .ssh_common import open_ssh


_orig_hook = threading.excepthook


def _quiet_prefetch(args):
    # Cancelling a download closes the connection under paramiko's prefetch thread:
    # its "Socket is closed" error is expected, don't spam stderr with it.
    if args.thread is not None and "prefetch" in (args.thread.name or "") and \
            issubclass(args.exc_type, (OSError, EOFError)):
        return
    _orig_hook(args)


threading.excepthook = _quiet_prefetch


def _entry(name: str, a: paramiko.SFTPAttributes) -> Entry:
    mode = a.st_mode or 0
    return Entry(
        name=name,
        is_dir=statmod.S_ISDIR(mode),
        size=a.st_size or 0,
        mtime=float(a.st_mtime) if a.st_mtime is not None else None,
        mode=mode_from_stat(mode) if a.st_mode is not None else None,
        owner=str(a.st_uid) if a.st_uid is not None else "",
        group=str(a.st_gid) if a.st_gid is not None else "",
        is_link=statmod.S_ISLNK(mode),
    )


class SFTPFS(RemoteFS):
    def connect(self):
        self.client = open_ssh(self.site, self.trust_cb)
        self.sftp = self.client.open_sftp()
        self._uids = {}

    def close(self):
        for o in (getattr(self, "sftp", None), getattr(self, "client", None)):
            try:
                o and o.close()
            except Exception:
                pass

    def is_alive(self):
        t = self.client.get_transport() if getattr(self, "client", None) else None
        return bool(t and t.is_active())

    def home(self):
        return self.sftp.normalize(".")

    def normalize(self, path):
        return self.sftp.normalize(path)

    def listdir(self, path):
        out = []
        for a in self.sftp.listdir_attr(path):
            e = _entry(a.filename, a)
            # owner/group names come from the longname ("-rw-r--r-- 1 user group …")
            ln = getattr(a, "longname", "") or ""
            parts = ln.split(None, 8)
            if len(parts) >= 4 and parts[0][:1] in "-dlbcps":
                e.owner, e.group = parts[2], parts[3]
            if e.is_link:
                full = posixpath.join(path, a.filename)
                try:
                    e.link_target = self.sftp.readlink(full) or ""
                    t = self.sftp.stat(full)
                    e.is_dir = statmod.S_ISDIR(t.st_mode or 0)
                    if not e.is_dir:
                        e.size = t.st_size or 0
                except Exception:
                    pass
            out.append(e)
        return out

    def stat(self, path):
        try:
            a = self.sftp.stat(path)
        except FileNotFoundError:
            return None
        except IOError as e:
            if getattr(e, "errno", None) == 2:
                return None
            raise
        return _entry(posixpath.basename(path.rstrip("/")) or "/", a)

    def mkdir(self, path): self.sftp.mkdir(path)
    def remove(self, path): self.sftp.remove(path)
    def rmdir(self, path): self.sftp.rmdir(path)

    def rename(self, src, dst):
        try:
            self.sftp.posix_rename(src, dst)
        except Exception:
            self.sftp.rename(src, dst)

    def chmod(self, path, mode): self.sftp.chmod(path, mode)

    def set_mtime(self, path, mtime):
        try:
            self.sftp.utime(path, (mtime, mtime))
        except Exception:
            pass

    def download(self, remote, local, progress, offset=0):
        size = self.sftp.stat(remote).st_size or 0
        done = offset
        rf = self.sftp.open(remote, "rb")
        try:
            with open(local, "r+b" if offset else "wb") as lf:
                if offset:
                    rf.seek(offset)
                    lf.seek(offset)
                    lf.truncate()
                try:   # pipelined reads, bounded so a fast link never buffers a whole ISO in RAM
                    rf.prefetch(size, max_concurrent_requests=128)
                except TypeError:   # paramiko < 2.11
                    rf.prefetch(size)
                while True:
                    data = rf.read(CHUNK)
                    if not data:
                        break
                    lf.write(data)
                    done += len(data)
                    progress(done)
        except BaseException:
            # closing a prefetching file would wait for the whole file: drop the connection instead
            self.close()
            raise
        rf.close()

    def upload(self, local, remote, progress, offset=0):
        done = offset
        with open(local, "rb") as lf, self.sftp.open(remote, "r+b" if offset else "wb") as rf:
            rf.set_pipelined(True)
            if offset:
                lf.seek(offset)
                rf.seek(offset)
            while True:
                data = lf.read(CHUNK)
                if not data:
                    break
                rf.write(data)
                done += len(data)
                progress(done)
            rf.flush()
