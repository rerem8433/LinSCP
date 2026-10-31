"""Run a callable in the GUI thread from a worker thread and wait for its result."""
from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication


class _Job:
    __slots__ = ("fn", "result", "error", "event")

    def __init__(self, fn):
        self.fn = fn
        self.result = None
        self.error = None
        self.event = threading.Event()


class GuiBridge(QObject):
    _sig = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._sig.connect(self._run)

    @pyqtSlot(object)
    def _run(self, job: _Job):
        try:
            job.result = job.fn()
        except Exception as e:  # pragma: no cover
            job.error = e
        job.event.set()

    def call(self, fn):
        app = QApplication.instance()
        if app is None or QThread.currentThread() is app.thread():
            return fn()
        job = _Job(fn)
        self._sig.emit(job)
        job.event.wait()
        if job.error:
            raise job.error
        return job.result


_bridge: GuiBridge | None = None


def bridge() -> GuiBridge:
    global _bridge
    if _bridge is None:
        _bridge = GuiBridge()
    return _bridge
