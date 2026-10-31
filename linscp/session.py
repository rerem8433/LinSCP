"""A browsing session: one connection used sequentially by a background thread."""
from __future__ import annotations

import ftplib
import queue
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from .protocols import Site, make_fs

try:
    import paramiko
    _SSH_ERR = (paramiko.SSHException,)
except Exception:  # pragma: no cover
    _SSH_ERR = ()

CONN_ERRORS = (EOFError, ConnectionError, BrokenPipeError, TimeoutError, ftplib.error_temp, OSError) + _SSH_ERR


class Session(QObject):
    _done = pyqtSignal(object, object, object)       # callback, result, error
    state = pyqtSignal(str, str)                     # connecting|connected|disconnected|error, message

    def __init__(self, site: Site, trust_cb, sid: str | None = None):
        super().__init__()
        self.site = site
        self.sid = sid
        self.trust_cb = trust_cb
        self.fs = None
        self.home = "/"
        self.connected = False
        self.dead = False
        self._q: queue.Queue = queue.Queue()
        self._done.connect(self._deliver)
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    # ------------------------------------------------------------------ API
    def open(self, ok=None, err=None):
        def job(fs):
            return self.home
        self.run(job, ok, err)

    def run(self, fn, ok=None, err=None):
        """fn(fs) runs in the session thread; ok(result) / err(exc) run in the GUI thread."""
        self._q.put((fn, ok, err))

    def close(self):
        self.dead = True          # owner is going away: drop pending callbacks
        self._q.put(None)

    # -------------------------------------------------------------- thread
    def _connect(self):
        self.state.emit("connecting", "")
        fs = make_fs(self.site, self.trust_cb)
        fs.connect()
        self.fs = fs
        try:
            self.home = fs.normalize(self.site.remote_dir) if self.site.remote_dir else fs.home()
        except Exception:
            self.home = fs.home()
        self.connected = True
        self.state.emit("connected", "")

    def _loop(self):
        while True:
            job = self._q.get()
            if job is None:
                break
            fn, ok, err = job
            try:
                res = self._call(fn)
                out = (ok, res, None)
            except Exception as e:
                out = (err, None, e)
            try:
                self._done.emit(*out)
            except RuntimeError:   # application already shutting down
                break
        if self.fs:
            try:
                self.fs.close()
            except Exception:
                pass
        self.connected = False
        try:
            self.state.emit("disconnected", "")
        except RuntimeError:   # application already shutting down
            pass

    def _call(self, fn):
        if self.fs is None:
            try:
                self._connect()
            except Exception as e:
                self.state.emit("error", str(e) or e.__class__.__name__)
                raise
        try:
            return fn(self.fs)
        except CONN_ERRORS as e:
            if self.fs.is_alive():
                raise
            # connection dropped (timeout, NAS sleep…): reconnect once and retry
            try:
                self.fs.close()
            except Exception:
                pass
            self.fs = None
            self.connected = False
            self.state.emit("disconnected", str(e))
            self._connect()
            return fn(self.fs)

    def _deliver(self, cb, res, err):
        if self.dead:
            return
        if err is not None:
            if cb:
                cb(err)
        elif cb:
            cb(res)
