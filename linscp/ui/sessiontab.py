"""One tab = one remote session (+ its local panel in dual mode)."""
from __future__ import annotations

import json
import os
import posixpath

from PyQt6.QtCore import QStandardPaths, Qt, QTimer
from PyQt6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QSplitter,
                             QStackedWidget, QVBoxLayout, QWidget)

from ..config import settings
from ..i18n import tr
from ..session import Session
from . import icons
from .models import REMOTE_MIME
from .panel import LocalPanel, RemotePanel


class StatusCard(QWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        card = QFrame()
        card.setObjectName("card")
        card.setMaximumWidth(460)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(26, 24, 26, 24)
        cl.setSpacing(10)
        self.ico = QLabel()
        self.ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel()
        self.title.setProperty("title", True)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg = QLabel()
        self.msg.setWordWrap(True)
        self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg.setProperty("muted", True)
        self.msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row = QHBoxLayout()
        row.addStretch(1)
        self.b_edit = QPushButton(icons.icon("sites"), tr("Modifier le site"))
        self.b_edit.clicked.connect(lambda: tab.win.open_site_manager(tab.sid))
        self.b_retry = QPushButton(icons.icon("retry", "#FFFFFF"), tr("Réessayer"))
        self.b_retry.setProperty("accent", True)
        self.b_retry.clicked.connect(tab.reconnect)
        row.addWidget(self.b_edit)
        row.addWidget(self.b_retry)
        row.addStretch(1)
        for w in (self.ico, self.title, self.msg):
            cl.addWidget(w)
        cl.addLayout(row)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(card)
        h.addStretch(1)
        lay.addLayout(h)
        lay.addStretch(2)

    def connecting(self, site):
        self.ico.setPixmap(icons.icon("connect", icons.ACCENT).pixmap(42, 42))
        self.title.setText(tr("Connexion en cours…"))
        self.msg.setText(f"{site.user + '@' if site.user else ''}{site.host}:{site.effective_port()}")
        self.b_retry.hide()
        self.b_edit.hide()

    def failed(self, err, can_edit):
        self.ico.setPixmap(icons.icon("alert", "#E5484D").pixmap(42, 42))
        self.title.setText(tr("Connexion impossible"))
        self.msg.setText(err)
        self.b_retry.show()
        self.b_edit.setVisible(can_edit)

    def closed(self, err):
        self.ico.setPixmap(icons.icon("disconnect").pixmap(42, 42))
        self.title.setText(tr("Déconnecté"))
        self.msg.setText(err or "")
        self.b_retry.show()
        self.b_edit.hide()


class SessionTab(QWidget):
    def __init__(self, win, site, sid=None):
        super().__init__()
        self.win = win
        self.site = site
        self.sid = sid
        self.session: Session | None = None
        self.active = None
        self._pending_remote = set()
        self._pending_local = set()

        self.local = LocalPanel(self)
        self.remote = RemotePanel(self)
        self.card = StatusCard(self)
        self.rstack = QStackedWidget()
        self.rstack.addWidget(self.card)
        self.rstack.addWidget(self.remote)
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.setHandleWidth(12)
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(self.local)
        self.split.addWidget(self.rstack)
        self.split.setSizes([1, 1])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 4)
        lay.addWidget(self.split)
        self.apply_layout()

        self._rt = QTimer(self, singleShot=True, interval=350, timeout=self._flush_refresh)
        q = win.queue
        q.remote_dir_changed.connect(self._remote_changed)
        q.local_dir_changed.connect(self._local_changed)
        self.connect_session()

    # ------------------------------------------------------------- session
    def connect_session(self):
        self.session = Session(self.site, self.win.trust_cb, self.sid)
        self.session.state.connect(self._state)
        self.card.connecting(self.site)
        self.rstack.setCurrentIndex(0)
        self.win.set_tab_state(self, "connecting")
        self.win.log("info", tr("Connexion à {h}…", h=f"{self.site.host}:{self.site.effective_port()}"))
        self.session.open(self._connected, self._failed)

    def reconnect(self):
        if self.session:
            self.session.state.disconnect()
            self.session.close()
        if not self.win.ensure_password(self.site, self.sid, force=True):
            return
        self.connect_session()

    def _connected(self, home):
        self.rstack.setCurrentIndex(1)
        self.remote.set_enabled(True)
        self.remote.title.setText(f"{self.site.label()} · {self.site.protocol.upper()}")
        self.win.set_tab_state(self, "connected")
        self.win.log("ok", tr("Connecté à {h}", h=self.site.host))
        self.remote.navigate(home)
        self.win.update_actions()

    def _failed(self, e):
        if self.session and self.session.connected:
            return   # an operation failed, not the connection (panel already reported it)
        msg = str(e) or e.__class__.__name__
        if e.__class__.__name__ == "PasswordRequiredException":
            from .dialogs import ask_password
            pw = ask_password(self, self.site, passphrase=True)
            if pw is not None:
                self.site.password = pw
                self.session.close()
                self.connect_session()
                return
        if "Authentication failed" in msg or "530" in msg:
            msg = tr("Identifiant ou mot de passe refusé par le serveur.") + f"\n({msg})"
        self.card.failed(msg, self.sid is not None)
        self.rstack.setCurrentIndex(0)
        self.win.set_tab_state(self, "error")
        self.win.log("error", f"{self.site.host}: {msg}")
        if self.session:
            self.session.close()
            self.session = None
        self.win.update_actions()

    def _state(self, st, msg):
        if st == "disconnected" and msg:
            self.win.log("warn", tr("Connexion perdue ({m}), reconnexion…", m=msg))

    def close_session(self):
        if self.session:
            try:
                self.session.state.disconnect()
            except TypeError:
                pass
            self.session.close()
            self.session = None

    # ------------------------------------------------------------- layout
    def apply_layout(self):
        single = settings.get("layout") == "single"
        self.local.setVisible(not single)

    def set_active_panel(self, p):
        self.active = p
        self.win.update_actions()

    def other_panel(self, p):
        return self.remote if p is self.local else self.local

    # ---------------------------------------------------------- transfers
    def _download_dir(self):
        if settings.get("layout") != "single":
            return self.local.cwd
        start = settings.get("download_dir") or QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DownloadLocation) or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, tr("Télécharger vers…"), start)
        if d:
            settings["download_dir"] = d
        return d or None

    def transfer(self, panel, entries):
        if not self.session or not self.session.connected:
            return
        if panel is self.remote:
            dest = self._download_dir()
            if not dest:
                return
            items = [(posixpath.join(self.remote.cwd, e.name), e.is_dir, e.size) for e in entries]
            self.download(items, dest)
        else:
            paths = [os.path.join(self.local.cwd, e.name) for e in entries]
            self.upload(paths, self.remote.cwd)

    def download(self, items, dest_dir):
        for path, is_dir, size in items:
            self.win.queue.add(self.session, "down", path, os.path.join(dest_dir, posixpath.basename(path)),
                               is_dir, size)
        self.win.show_queue()

    def upload(self, paths, remote_dir):
        if not self.session or not self.session.connected:
            return
        for p in paths:
            p = p.rstrip("/")
            is_dir = os.path.isdir(p)
            size = 0 if is_dir else os.path.getsize(p)
            self.win.queue.add(self.session, "up", p, posixpath.join(remote_dir, os.path.basename(p)), is_dir, size)
        self.win.show_queue()

    def drop_on(self, panel, data, dest):
        if panel is self.local and data.hasFormat(REMOTE_MIME):
            info = json.loads(bytes(data.data(REMOTE_MIME)).decode())
            src_tab = self.win.tab_by_id(info["tab"])
            if src_tab is None or not src_tab.session:
                return False
            src_tab.download([tuple(i) for i in info["items"]], dest)
            return True
        if panel is self.remote and data.hasUrls():
            paths = [u.toLocalFile() for u in data.urls() if u.isLocalFile()]
            if paths:
                self.upload(paths, dest)
                return True
        return False

    # ------------------------------------------------- refresh after copy
    def _remote_changed(self, session, d):
        if session is self.session:
            self._pending_remote.add(d)
            self._rt.start()

    def _local_changed(self, d):
        self._pending_local.add(d)
        self._rt.start()

    def _flush_refresh(self):
        for d in self._pending_remote:
            self.remote.refresh_if(d)
        for d in self._pending_local:
            self.local.refresh_if(d)
        self._pending_remote.clear()
        self._pending_local.clear()
