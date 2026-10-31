"""Main window."""
from __future__ import annotations

import os
import urllib.parse

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QAction, QIntValidator, QKeySequence
from PyQt6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QSizePolicy, QSpinBox,
                             QSplitter, QStackedWidget, QTabWidget, QToolBar, QToolButton, QVBoxLayout,
                             QWidget)

from .. import __version__
from ..bridge import bridge
from ..config import settings
from ..i18n import tr
from ..protocols import PROTOCOL_LABELS, PROTOCOLS, Site
from ..sites import SiteStore, get_password
from ..transfers import TransferQueue
from . import icons, theme
from .dialogs import AboutDialog, ExistsDialog, ask_password, ask_trust
from .prefs import PrefsDialog
from .queueview import LogView, QueueView
from .sessiontab import SessionTab
from .sitemanager import SiteManager

STATE_COLOR = {"connecting": "#D9A400", "connected": "#22B573", "error": "#E5484D"}


class Welcome(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(88, 88))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QLabel(tr("Bienvenue dans LinSCP"))
        t.setStyleSheet("font-size: 17pt; font-weight: 700;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s = QLabel(tr("SFTP · SCP · FTP / FTPS — choisissez un site ou utilisez la connexion rapide ci-dessus."))
        s.setProperty("muted", True)
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addSpacing(16)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(10)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(self.grid_host)
        h.addStretch(1)
        lay.addLayout(h)
        lay.addSpacing(10)
        b = QPushButton(icons.icon("sites", "#FFFFFF"), tr("Gestionnaire de sites"))
        b.setProperty("accent", True)
        b.clicked.connect(lambda: win.open_site_manager())
        bh = QHBoxLayout()
        bh.addStretch(1)
        bh.addWidget(b)
        bh.addStretch(1)
        lay.addLayout(bh)
        lay.addStretch(2)

    def refresh(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        for i, (sid, s) in enumerate(self.win.store.ordered()[:8]):
            btn = QToolButton()
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIcon(icons.icon("server", icons.ACCENT))
            btn.setIconSize(QSize(30, 30))
            btn.setText(f"{s.label()}\n{s.protocol.upper()} · {s.host}")
            btn.setFixedSize(170, 92)
            btn.setObjectName("card")
            btn.setStyleSheet("QToolButton#card { border: 1px solid %s; border-radius: 12px; background: %s; }"
                              "QToolButton#card:hover { border-color: %s; }"
                              % (theme.current["border"], theme.current["base"], icons.ACCENT))
            btn.clicked.connect(lambda _, x=sid: self.win.open_saved(x))
            self.grid.addWidget(btn, i // 4, i % 4)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LinSCP")
        self.setWindowIcon(icons.app_icon())
        self.resize(1320, 800)
        self.store = SiteStore()
        self.queue = TransferQueue(ask_exists=self._ask_exists)
        self.queue.log.connect(self.log)
        self.queue.idle.connect(self._queue_idle)
        self.queue.item_changed.connect(lambda _: self._update_queue_count())
        self.queue.item_added.connect(lambda _: self._update_queue_count())

        self._build_toolbar()

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(lambda _: self.update_actions())
        self.welcome = Welcome(self)
        self.center = QStackedWidget()
        self.center.addWidget(self.welcome)
        self.center.addWidget(self.tabs)

        self.bottom = QTabWidget()
        self.bottom.setDocumentMode(True)
        self.queue_view = QueueView(self.queue)
        self.log_view = LogView()
        self.bottom.addTab(self.queue_view, icons.icon("queue"), tr("File d'attente"))
        self.bottom.addTab(self.log_view, icons.icon("terminal"), tr("Journal"))
        bw = QWidget()
        bl = QVBoxLayout(bw)
        bl.setContentsMargins(10, 0, 10, 6)
        bl.addWidget(self.bottom)

        self.vsplit = QSplitter(Qt.Orientation.Vertical)
        self.vsplit.setHandleWidth(8)
        self.vsplit.addWidget(self.center)
        self.vsplit.addWidget(bw)
        self.vsplit.setStretchFactor(0, 4)
        self.vsplit.setStretchFactor(1, 1)
        self.vsplit.setSizes([560, 200])
        self.setCentralWidget(self.vsplit)

        self.status_queue = QLabel("")
        self.statusBar().addPermanentWidget(self.status_queue)
        self.statusBar().showMessage(f"LinSCP {__version__}")

        try:
            if settings.get("window_geometry"):
                self.restoreGeometry(QByteArray.fromHex(settings["window_geometry"].encode()))
            if settings.get("splitter"):
                self.vsplit.restoreState(QByteArray.fromHex(settings["splitter"].encode()))
        except Exception:
            pass
        self.welcome.refresh()
        self.update_actions()
        self.log("info", f"LinSCP {__version__}")

    # ------------------------------------------------------------- toolbar
    def _act(self, ico, text, fn, shortcut=None, checkable=False):
        a = QAction(icons.icon(ico), text, self)
        a.setToolTip(text + (f" ({shortcut})" if shortcut else ""))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        a.triggered.connect(fn)
        self.addAction(a)
        return a

    def _build_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        self.a_sites = self._act("sites", tr("Sites"), lambda: self.open_site_manager(), "Ctrl+N")
        tb.addAction(self.a_sites)
        tb.addSeparator()

        # quick connect ---------------------------------------------------------
        self.q_proto = QComboBox()
        for p in PROTOCOLS:
            self.q_proto.addItem(tr(PROTOCOL_LABELS[p]), p)
        self.q_host = QLineEdit()
        self.q_host.setPlaceholderText(tr("Hôte ou sftp://user@hôte"))
        self.q_host.setMinimumWidth(190)
        self.q_user = QLineEdit()
        self.q_user.setPlaceholderText(tr("Utilisateur"))
        self.q_user.setMinimumWidth(100)
        self.q_user.setMaximumWidth(130)
        self.q_pass = QLineEdit()
        self.q_pass.setPlaceholderText(tr("Mot de passe"))
        self.q_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.q_pass.setMinimumWidth(100)
        self.q_pass.setMaximumWidth(130)
        self.q_port = QLineEdit()
        self.q_port.setPlaceholderText(tr("Port"))
        self.q_port.setMaximumWidth(64)
        self.q_port.setValidator(QIntValidator(1, 65535, self.q_port))
        self.q_port.setToolTip(tr("Port (vide = port par défaut)"))
        qb = QPushButton(icons.icon("connect", "#FFFFFF"), tr("Connexion"))
        qb.setProperty("accent", True)
        qb.clicked.connect(self.quick_connect)
        for w in (self.q_host, self.q_user, self.q_pass, self.q_port):
            w.returnPressed.connect(self.quick_connect)
        for w in (self.q_proto, self.q_host, self.q_user, self.q_pass, self.q_port, qb):
            tb.addWidget(w)
            spacer = QWidget()
            spacer.setFixedWidth(4)
            tb.addWidget(spacer)

        grow = QWidget()
        grow.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(grow)

        self.a_upload = self._act("upload", tr("Envoyer…"), self.upload_files)
        self.a_download = self._act("download", tr("Télécharger"), self.download_selected)
        self.a_disconnect = self._act("disconnect", tr("Déconnecter"), lambda: self.close_tab(self.tabs.currentIndex()), "Ctrl+W")
        self.a_layout = self._act("dual", tr("Double panneau"), self.toggle_layout, "Ctrl+D", checkable=True)
        self.a_layout.setChecked(settings.get("layout") != "single")
        self.a_hidden = self._act("eye", tr("Fichiers cachés"), self.toggle_hidden, None, checkable=True)
        self.a_hidden.setChecked(bool(settings.get("show_hidden")))
        for a in (self.a_upload, self.a_download):
            tb.addAction(a)
        self._tb = tb
        tb.addSeparator()
        for a in (self.a_layout, self.a_hidden, self.a_disconnect):
            tb.addAction(a)
            tb.widgetForAction(a).setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        menu = QMenu(self)
        menu.addAction(icons.icon("sites"), tr("Gestionnaire de sites"), lambda: self.open_site_manager())
        menu.addAction(icons.icon("upload"), tr("Envoyer un dossier…"), self.upload_folder)
        menu.addSeparator()
        menu.addAction(icons.icon("settings"), tr("Préférences…"), self.open_prefs)
        menu.addAction(icons.icon("info"), tr("À propos"), lambda: AboutDialog(self).exec())
        menu.addSeparator()
        menu.addAction(icons.icon("close"), tr("Quitter"), self.close)
        mb = QToolButton()
        mb.setIcon(icons.icon("queue"))
        mb.setToolTip(tr("Menu"))
        mb.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        mb.setMenu(menu)
        mb.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        tb.addWidget(mb)
        self._act("close", tr("Quitter"), self.close, "Ctrl+Q")

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        # narrow window: icon-only transfer buttons so the menu never falls into the overflow
        style = Qt.ToolButtonStyle.ToolButtonTextBesideIcon if self.width() >= 1300 \
            else Qt.ToolButtonStyle.ToolButtonIconOnly
        for a in (self.a_upload, self.a_download):
            w = self._tb.widgetForAction(a)
            if w:
                w.setToolButtonStyle(style)

    # ------------------------------------------------------------ helpers
    def log(self, level, msg):
        self.log_view.add(level, msg)
        if level == "error":
            self.statusBar().showMessage(msg, 8000)

    def trust_cb(self, kind, host, fp, changed):
        return bridge().call(lambda: ask_trust(self, kind, host, fp, changed))

    def _ask_exists(self, item, local_size, remote_size):
        can_resume = item.session.site.protocol != "scp"
        d = ExistsDialog(self, item, local_size, remote_size, can_resume)
        d.exec()
        return d.action, d.all.isChecked()

    def current_tab(self) -> SessionTab | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, SessionTab) else None

    def tab_by_id(self, tid):
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if id(w) == tid:
                return w
        return None

    def all_tabs(self):
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def set_tab_state(self, tab, state):
        i = self.tabs.indexOf(tab)
        if i >= 0:
            self.tabs.setTabIcon(i, icons.icon("server", STATE_COLOR.get(state)))

    def update_actions(self):
        t = self.current_tab()
        connected = bool(t and t.session and t.session.connected)
        self.a_upload.setEnabled(connected)
        self.a_download.setEnabled(connected)
        self.a_disconnect.setEnabled(t is not None)
        self.center.setCurrentIndex(1 if self.tabs.count() else 0)
        if t:
            self.setWindowTitle(f"{t.site.label()} — LinSCP")
        else:
            self.setWindowTitle("LinSCP")

    def show_queue(self):
        self.bottom.setCurrentWidget(self.queue_view)

    def _update_queue_count(self):
        n = self.queue.active()
        self.status_queue.setText(tr("{n} transfert(s) en cours", n=n) if n else "")
        self.bottom.setTabText(0, tr("File d'attente") + (f" ({n})" if n else ""))

    def _queue_idle(self):
        self._update_queue_count()
        self.log("ok", tr("File de transferts terminée"))

    # ----------------------------------------------------------- sessions
    def ensure_password(self, site: Site, sid, force=False) -> bool:
        if site.password and not force:
            return True
        if sid and site.save_password and not force:
            site.password = get_password(sid)
            if site.password:
                return True
        needs = (site.protocol in ("sftp", "scp") and site.auth == "password") or \
                (site.protocol.startswith("ftp") and site.user and site.user != "anonymous")
        if not needs:
            return True
        pw = ask_password(self, site)
        if pw is None:
            return False
        site.password = pw
        return True

    def open_tab(self, site: Site, sid=None):
        if not self.ensure_password(site, sid):
            return
        tab = SessionTab(self, site, sid)
        i = self.tabs.addTab(tab, icons.icon("server", STATE_COLOR["connecting"]), site.label())
        self.tabs.setTabToolTip(i, f"{site.protocol.upper()} · {site.host}:{site.effective_port()}")
        cb = QToolButton()
        cb.setIcon(icons.icon("close"))
        cb.setIconSize(QSize(13, 13))
        cb.setAutoRaise(True)
        cb.setToolTip(tr("Déconnecter"))
        cb.setStyleSheet("QToolButton { padding: 2px; border-radius: 5px; }")
        cb.clicked.connect(lambda: self.close_tab(self.tabs.indexOf(tab)))
        self.tabs.tabBar().setTabButton(i, self.tabs.tabBar().ButtonPosition.RightSide, cb)
        self.tabs.setCurrentIndex(i)
        self.update_actions()

    def open_saved(self, sid):
        s = self.store.sites.get(sid)
        if s:
            c = Site.from_dict(s.to_dict())
            self.open_tab(c, sid)

    def open_site_manager(self, select=None):
        d = SiteManager(self, self.store, select)
        ok = d.exec()
        self.welcome.refresh()
        if ok and d.result_site:
            self.open_tab(d.result_site, d.result_sid)

    def quick_connect(self):
        text = self.q_host.text().strip()
        if not text:
            self.q_host.setFocus()
            return
        s = Site(protocol=self.q_proto.currentData(), user=self.q_user.text().strip(),
                 password=self.q_pass.text(), port=int(self.q_port.text() or 0))
        if "://" in text:
            u = urllib.parse.urlsplit(text)
            scheme = {"sftp": "sftp", "scp": "scp", "ssh": "sftp", "ftp": "ftp", "ftps": "ftps",
                      "ftpes": "ftps"}.get(u.scheme.lower())
            if scheme:
                s.protocol = scheme
            s.host = u.hostname or ""
            if u.username:
                s.user = urllib.parse.unquote(u.username)
            if u.password:
                s.password = urllib.parse.unquote(u.password)
            if u.port:
                s.port = u.port
            if u.path and u.path != "/":
                s.remote_dir = urllib.parse.unquote(u.path)
        else:
            if "@" in text:
                s.user, text = text.rsplit("@", 1)
            if text.count(":") == 1:
                text, port = text.split(":")
                if port.isdigit():
                    s.port = int(port)
            s.host = text
        if not s.host:
            return
        self.open_tab(s)
        self.q_pass.clear()

    def close_tab(self, i):
        if i < 0:
            return
        tab = self.tabs.widget(i)
        busy = [it for it in self.queue.items if it.session is getattr(tab, "session", None)
                and it.status in ("queued", "running")]
        if busy and QMessageBox.question(self, tr("Déconnecter"),
                                         tr("{n} transfert(s) en cours sur cette session seront annulés. Continuer ?",
                                            n=len(busy))) != QMessageBox.StandardButton.Yes:
            return
        for it in busy:
            self.queue.cancel(it)
        tab.close_session()
        self.tabs.removeTab(i)
        tab.deleteLater()
        self.update_actions()

    # ------------------------------------------------------------ actions
    def upload_files(self):
        t = self.current_tab()
        if not t or not t.session or not t.session.connected:
            return
        if settings.get("layout") != "single" and t.active is t.local and t.local.selected_entries():
            t.transfer(t.local, t.local.selected_entries())
            return
        files, _ = QFileDialog.getOpenFileNames(self, tr("Envoyer des fichiers"), t.local.cwd)
        if files:
            t.upload(files, t.remote.cwd)

    def upload_folder(self):
        t = self.current_tab()
        if not t or not t.session or not t.session.connected:
            return
        d = QFileDialog.getExistingDirectory(self, tr("Envoyer un dossier"), t.local.cwd)
        if d:
            t.upload([d], t.remote.cwd)

    def download_selected(self):
        t = self.current_tab()
        if t:
            ents = t.remote.selected_entries()
            if ents:
                t.transfer(t.remote, ents)

    def toggle_layout(self):
        settings["layout"] = "dual" if self.a_layout.isChecked() else "single"
        settings.save()
        for t in self.all_tabs():
            t.apply_layout()

    def toggle_hidden(self):
        v = not bool(settings.get("show_hidden"))
        settings["show_hidden"] = v
        settings.save()
        self.a_hidden.setChecked(v)
        for t in self.all_tabs():
            t.local.proxy.set_hidden(v)
            t.remote.proxy.set_hidden(v)

    def open_prefs(self):
        old_theme = settings.get("theme")
        if PrefsDialog(self).exec():
            if settings.get("theme") != old_theme:
                theme.apply(QApplication.instance(), settings.get("theme"))
                self._reicon()
            self.a_layout.setChecked(settings.get("layout") != "single")
            self.a_hidden.setChecked(bool(settings.get("show_hidden")))
            for t in self.all_tabs():
                t.apply_layout()
                t.local.proxy.set_hidden(bool(settings.get("show_hidden")))
                t.remote.proxy.set_hidden(bool(settings.get("show_hidden")))

    def _reicon(self):
        QMessageBox.information(self, tr("Thème"), tr("Le nouveau thème sera entièrement appliqué au prochain démarrage."))

    # -------------------------------------------------------------- close
    def closeEvent(self, ev):
        n = self.queue.active()
        if n and QMessageBox.question(self, "LinSCP", tr("{n} transfert(s) en cours. Quitter quand même ?", n=n)) \
                != QMessageBox.StandardButton.Yes:
            ev.ignore()
            return
        self.queue.cancel_all()
        for t in self.all_tabs():
            t.close_session()
        settings["window_geometry"] = bytes(self.saveGeometry().toHex()).decode()
        settings["splitter"] = bytes(self.vsplit.saveState().toHex()).decode()
        settings.save()
        ev.accept()
