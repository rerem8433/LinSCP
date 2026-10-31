"""Transfer queue: parallel workers, one connection per worker and per session, resume support."""
from __future__ import annotations

import itertools
import os
import posixpath
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal

from .config import settings
from .protocols import Cancelled, Site, make_fs

_ids = itertools.count(1)

QUEUED, RUNNING, DONE, ERROR, CANCELLED, SKIPPED = "queued", "running", "done", "error", "cancelled", "skipped"


class TransferItem:
    def __init__(self, session, direction: str, src: str, dst: str, is_dir: bool, size: int = 0):
        self.id = next(_ids)
        self.session = session          # object with .site (Site incl. password) and .trust_cb
        self.direction = direction      # "up" | "down"
        self.src = src
        self.dst = dst
        self.is_dir = is_dir
        self.size = size
        self.done = 0
        self.status = QUEUED
        self.error = ""
        self.speed = 0.0
        self.cancel = False
        self.started = 0.0
        self.files = 0                  # for folders: number of files queued

    @property
    def name(self):
        p = self.src.rstrip("/")
        return os.path.basename(p) if self.direction == "up" else posixpath.basename(p)


class TransferQueue(QObject):
    item_added = pyqtSignal(object)
    item_changed = pyqtSignal(object)
    remote_dir_changed = pyqtSignal(object, str)    # session, remote dir
    local_dir_changed = pyqtSignal(str)
    idle = pyqtSignal()
    log = pyqtSignal(str, str)                      # level, message

    def __init__(self, ask_exists=None):
        super().__init__()
        self.items: list[TransferItem] = []
        self.lock = threading.Lock()
        self.workers: list[threading.Thread] = []
        self.ask_exists = ask_exists      # fn(item, local_size, remote_size) -> (action, apply_all) (GUI thread)
        self._policy_all = None
        self._ask_lock = threading.Lock()

    # ------------------------------------------------------------------ API
    def add(self, session, direction, src, dst, is_dir, size=0):
        it = TransferItem(session, direction, src, dst, is_dir, size)
        with self.lock:
            self.items.append(it)
        self.item_added.emit(it)
        self._spawn()
        return it

    def cancel(self, item: TransferItem):
        item.cancel = True
        if item.status == QUEUED:
            item.status = CANCELLED
            self.item_changed.emit(item)

    def cancel_all(self):
        for it in list(self.items):
            if it.status in (QUEUED, RUNNING):
                self.cancel(it)

    def clear_finished(self):
        with self.lock:
            self.items = [i for i in self.items if i.status in (QUEUED, RUNNING)]

    def retry(self, item: TransferItem):
        if item.status in (ERROR, CANCELLED):
            item.status, item.error, item.cancel, item.done = QUEUED, "", False, 0
            self.item_changed.emit(item)
            self._spawn()

    def active(self) -> int:
        return sum(1 for i in self.items if i.status in (QUEUED, RUNNING))

    # -------------------------------------------------------------- workers
    def _spawn(self):
        with self.lock:
            self.workers = [w for w in self.workers if w.is_alive()]
            pending = sum(1 for i in self.items if i.status == QUEUED)
            want = min(max(1, int(settings.get("parallel", 2))), pending)
            for _ in range(want - len(self.workers)):
                w = threading.Thread(target=self._worker, daemon=True)
                self.workers.append(w)
                w.start()

    def _next(self):
        with self.lock:
            for it in self.items:
                if it.status == QUEUED:
                    it.status = RUNNING
                    return it
        return None

    def _worker(self):
        conns: dict[int, object] = {}
        try:
            while True:
                it = self._next()
                if it is None:
                    break
                key = id(it.session)
                try:
                    fs = conns.get(key)
                    if fs is None:
                        fs = make_fs(_copy_site(it.session.site), it.session.trust_cb)
                        fs.connect()
                        conns[key] = fs
                    self._run(fs, it)
                except Cancelled:
                    it.status = CANCELLED
                    self._drop(conns, key)
                except Exception as e:
                    it.status = ERROR
                    it.error = str(e) or e.__class__.__name__
                    self.log.emit("error", f"{it.name}: {it.error}")
                    self._drop(conns, key)
                self.item_changed.emit(it)
        finally:
            for fs in conns.values():
                try:
                    fs.close()
                except Exception:
                    pass
            with self.lock:
                last = not any(i.status in (QUEUED, RUNNING) for i in self.items)
                me = threading.current_thread()
                self.workers = [w for w in self.workers if w is not me]
            if last and not self.workers:
                self._policy_all = None
                self.idle.emit()

    @staticmethod
    def _drop(conns, key):
        fs = conns.pop(key, None)
        if fs:
            try:
                fs.close()
            except Exception:
                pass

    # ------------------------------------------------------------- one item
    def _run(self, fs, it: TransferItem):
        it.started = time.time()
        if it.is_dir:
            self._expand(fs, it)
            return
        if it.direction == "down":
            self._download(fs, it)
        else:
            self._upload(fs, it)

    def _expand(self, fs, it: TransferItem):
        """Create the target folder and queue its content."""
        children = []
        if it.direction == "down":
            os.makedirs(it.dst, exist_ok=True)
            for e in fs.listdir(it.src):
                children.append((posixpath.join(it.src, e.name), os.path.join(it.dst, e.name),
                                 e.is_dir, e.size))
            self.local_dir_changed.emit(os.path.dirname(it.dst.rstrip("/")))
        else:
            st = fs.stat(it.dst)
            if st is None:
                fs.mkdir(it.dst)
            with os.scandir(it.src) as sd:
                for e in sd:
                    is_dir = e.is_dir(follow_symlinks=True)
                    size = 0 if is_dir else e.stat().st_size
                    children.append((e.path, posixpath.join(it.dst, e.name), is_dir, size))
            self.remote_dir_changed.emit(it.session, posixpath.dirname(it.dst.rstrip("/")) or "/")
        # folders last so files of the current level start first
        children.sort(key=lambda c: c[2])
        it.files = len(children)
        it.status = DONE
        for src, dst, is_dir, size in children:
            if it.cancel:
                break
            self.add(it.session, it.direction, src, dst, is_dir, size)

    def _decide(self, it, local_size, remote_size) -> str:
        policy = settings.get("on_exists", "ask")
        if policy == "ask" and self.ask_exists:
            with self._ask_lock:            # one question at a time, even with parallel workers
                if self._policy_all:
                    return self._policy_all
                from .bridge import bridge
                action, apply_all = bridge().call(lambda: self.ask_exists(it, local_size, remote_size))
                if apply_all:
                    self._policy_all = action
                return action
        return policy if policy != "ask" else "overwrite"

    def _progress(self, it):
        last = [0.0]
        base = [None]

        def cb(done):
            if it.cancel:
                raise Cancelled()
            it.done = done
            now = time.time()
            if base[0] is None:
                base[0] = (now, done)
            if now - last[0] >= 0.15:
                t0, d0 = base[0]
                it.speed = (done - d0) / max(now - t0, 1e-3)
                last[0] = now
                self.item_changed.emit(it)
        return cb

    def _download(self, fs, it: TransferItem):
        st = fs.stat(it.src)
        if st is None:
            raise FileNotFoundError(it.src)
        it.size = st.size
        offset = 0
        if os.path.exists(it.dst):
            lsize = os.path.getsize(it.dst)
            action = self._decide(it, lsize, st.size)
            if action == "skip":
                it.status = SKIPPED
                return
            if action == "resume" and fs.supports_resume and 0 < lsize < st.size:
                offset = lsize
            elif action == "resume" and lsize == st.size:
                it.done, it.status = st.size, DONE
                return
        os.makedirs(os.path.dirname(it.dst) or ".", exist_ok=True)
        it.status = RUNNING
        self.item_changed.emit(it)
        fs.download(it.src, it.dst, self._progress(it), offset)
        if settings.get("preserve_time", True) and st.mtime:
            try:
                os.utime(it.dst, (st.mtime, st.mtime))
            except OSError:
                pass
        if st.mode is not None and st.mode & 0o111:
            try:
                os.chmod(it.dst, os.stat(it.dst).st_mode | 0o100)
            except OSError:
                pass
        it.done = it.size
        it.status = DONE
        self.local_dir_changed.emit(os.path.dirname(it.dst))

    def _upload(self, fs, it: TransferItem):
        lst = os.stat(it.src)
        it.size = lst.st_size
        offset = 0
        st = fs.stat(it.dst)
        if st is not None:
            if st.is_dir:
                raise IsADirectoryError(it.dst)
            action = self._decide(it, lst.st_size, st.size)
            if action == "skip":
                it.status = SKIPPED
                return
            if action == "resume" and fs.supports_resume and 0 < st.size < lst.st_size:
                offset = st.size
            elif action == "resume" and st.size == lst.st_size:
                it.done, it.status = it.size, DONE
                return
        it.status = RUNNING
        self.item_changed.emit(it)
        fs.upload(it.src, it.dst, self._progress(it), offset)
        if settings.get("preserve_time", True):
            fs.set_mtime(it.dst, lst.st_mtime)
        it.done = it.size
        it.status = DONE
        self.remote_dir_changed.emit(it.session, posixpath.dirname(it.dst) or "/")


def _copy_site(s: Site) -> Site:
    c = Site.from_dict(s.to_dict())
    c.password = s.password
    return c
