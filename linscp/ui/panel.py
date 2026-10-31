"""Local and remote file panels."""
from __future__ import annotations

import grp
import json
import os
import posixpath
import pwd
import shutil
import stat as statmod

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QFrame, QHBoxLayout, QHeaderView, QLabel,
                             QLineEdit, QMenu, QMessageBox, QSizePolicy, QStackedWidget, QToolButton,
                             QTreeView, QVBoxLayout, QWidget, QInputDialog)

from ..config import settings
from ..i18n import tr
from ..protocols import Entry
from . import icons
from .models import (ENTRY_ROLE, REMOTE_MIME, FileModel, SortProxy, human_size, local_mime,
                     remote_mime)


# --------------------------------------------------------------------------- path bar
class PathBar(QFrame):
    """Clickable breadcrumb; click the empty area (or Ctrl+L) to type a path."""
    path_entered = pyqtSignal(str)

    def __init__(self, root_icon: str):
        super().__init__()
        self.setObjectName("card")
        self.root_icon = root_icon
        self.path = "/"
        self.stack = QStackedWidget()
        self.crumbs = QWidget()
        self.cl = QHBoxLayout(self.crumbs)
        self.cl.setContentsMargins(4, 0, 4, 0)
        self.cl.setSpacing(0)
        self.edit = QLineEdit()
        self.edit.setFrame(False)
        self.edit.setStyleSheet("border: none; background: transparent; padding: 4px 6px;")
        self.edit.returnPressed.connect(self._commit)
        self.edit.installEventFilter(self)
        self.stack.addWidget(self.crumbs)
        self.stack.addWidget(self.edit)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(self.stack)
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.IBeamCursor)

    def set_path(self, p: str):
        self.path = p
        while self.cl.count():
            w = self.cl.takeAt(0).widget()
            if w:
                w.deleteLater()
        parts = [x for x in p.split("/") if x]
        root = self._btn("", "/")
        root.setIcon(icons.icon(self.root_icon))
        self.cl.addWidget(root)
        shown = parts
        acc = ""
        if len(parts) > 5:
            for x in parts[:-4]:
                acc += "/" + x
            more = self._btn("…", acc)
            self.cl.addWidget(self._sep())
            self.cl.addWidget(more)
            shown = parts[-4:]
        for x in shown:
            acc += "/" + x
            self.cl.addWidget(self._sep())
            self.cl.addWidget(self._btn(x, acc))
        self.cl.addStretch(1)
        self.stack.setCurrentIndex(0)

    def _btn(self, text, target):
        b = QToolButton()
        b.setText(text)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet("QToolButton { padding: 3px 6px; }")
        b.clicked.connect(lambda: self.path_entered.emit(target))
        return b

    def _sep(self):
        l = QLabel("›")
        l.setProperty("muted", True)
        l.setStyleSheet("padding: 0 1px;")
        return l

    def mousePressEvent(self, ev):
        self.start_edit()

    def start_edit(self):
        self.edit.setText(self.path)
        self.stack.setCurrentIndex(1)
        self.edit.setFocus()
        self.edit.selectAll()

    def _commit(self):
        t = self.edit.text().strip()
        self.stack.setCurrentIndex(0)
        if t:
            self.path_entered.emit(t)

    def eventFilter(self, obj, ev):
        if obj is self.edit:
            if ev.type() == QEvent.Type.FocusOut:
                self.stack.setCurrentIndex(0)
            elif ev.type() == QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_Escape:
                self.stack.setCurrentIndex(0)
                return True
        return False


class FileView(QTreeView):
    focused = pyqtSignal()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.focused.emit()


# --------------------------------------------------------------------------- base panel
class FilePanel(QWidget):
    is_remote = False

    def __init__(self, tab, title: str, root_icon: str):
        super().__init__()
        self.tab = tab
        self.cwd = "/"
        self.history: list[str] = []
        self.loading = False

        # header ------------------------------------------------------------
        head = QFrame()
        head.setObjectName("panelHeader")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(4)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight: 600;")
        self.title_icon = QLabel()
        self.title_icon.setPixmap(icons.icon(root_icon).pixmap(18, 18))
        hl.addWidget(self.title_icon)
        hl.addWidget(self.title)
        hl.addStretch(1)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("Filtrer…"))
        self.filter.setClearButtonEnabled(True)
        self.filter.setMaximumWidth(170)
        self.filter.textChanged.connect(lambda t: self.proxy.set_text(t))
        hl.addWidget(self.filter)

        nav = QHBoxLayout()
        nav.setSpacing(2)
        self.b_back = self._tool("up", tr("Dossier parent (Retour arrière)"), self.go_up)
        self.b_home = self._tool("home", tr("Dossier personnel"), self.go_home)
        self.b_refresh = self._tool("refresh", tr("Actualiser (Ctrl+R)"), self.refresh)
        self.b_mkdir = self._tool("new-folder", tr("Nouveau dossier (F7)"), self.ask_mkdir)
        self.pathbar = PathBar(root_icon)
        self.pathbar.path_entered.connect(self.navigate)
        for b in (self.b_back, self.b_home):
            nav.addWidget(b)
        nav.addWidget(self.pathbar, 1)
        nav.addWidget(self.b_refresh)
        nav.addWidget(self.b_mkdir)

        # view --------------------------------------------------------------
        self.model = FileModel(self)
        self.proxy = SortProxy()
        self.proxy.setSourceModel(self.model)
        self.proxy.set_hidden(bool(settings.get("show_hidden")))
        v = self.view = FileView()
        v.setModel(self.proxy)
        v.setRootIsDecorated(False)
        v.setUniformRowHeights(True)
        v.setAlternatingRowColors(False)
        v.setSortingEnabled(True)
        v.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        v.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        v.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        v.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        v.setDragEnabled(True)
        v.setAcceptDrops(True)
        v.setDropIndicatorShown(True)
        v.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        v.setDefaultDropAction(Qt.DropAction.CopyAction)
        v.setIconSize(QSize(20, 20))
        v.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        v.customContextMenuRequested.connect(self._menu)
        v.doubleClicked.connect(self._activate)
        v.focused.connect(lambda: self.tab.set_active_panel(self))
        h = v.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c, w in ((1, 90), (2, 130), (3, 95), (4, 110)):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
            h.resizeSection(c, w)
        h.setSectionsMovable(False)

        self.footer = QLabel("")
        self.footer.setProperty("muted", True)
        v.selectionModel().selectionChanged.connect(self._update_footer)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(head)
        lay.addLayout(nav)
        lay.addWidget(v, 1)
        lay.addWidget(self.footer)

        for seq, fn in (("F2", self.ask_rename), ("F7", self.ask_mkdir), ("Delete", self.ask_delete),
                        ("F8", self.ask_delete), ("Ctrl+R", self.refresh), ("Backspace", self.go_up),
                        ("Ctrl+L", self.pathbar.start_edit), ("F5", self.transfer_selected),
                        ("Return", self._activate_current), ("Ctrl+H", self.tab.win.toggle_hidden)):
            a = QAction(self)
            a.setShortcut(QKeySequence(seq))
            a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            a.triggered.connect(fn)
            v.addAction(a)

    def _tool(self, ico, tip, fn):
        b = QToolButton()
        b.setIcon(icons.icon(ico))
        b.setToolTip(tip)
        b.setAutoRaise(True)
        b.clicked.connect(fn)
        return b

    # ------------------------------------------------------------- helpers
    def join(self, a, b):
        return posixpath.join(a, b) if self.is_remote else os.path.join(a, b)

    def parent_of(self, p):
        return (posixpath.dirname(p.rstrip("/")) or "/") if self.is_remote else (os.path.dirname(p.rstrip("/")) or "/")

    def selected_entries(self) -> list[Entry]:
        rows = self.view.selectionModel().selectedRows()
        out = []
        for r in rows:
            e = self.proxy.data(r, ENTRY_ROLE)
            if e and e.name != "..":
                out.append(e)
        return out

    def current_entry(self):
        idx = self.view.currentIndex()
        return self.proxy.data(idx.siblingAtColumn(0), ENTRY_ROLE) if idx.isValid() else None

    def set_entries(self, entries, keep_selection=True):
        selected = {e.name for e in self.selected_entries()} if keep_selection else set()
        self.model.set_entries(entries, self.cwd != "/")
        if selected:
            sm = self.view.selectionModel()
            for row in range(self.proxy.rowCount()):
                idx = self.proxy.index(row, 0)
                if self.proxy.data(idx, ENTRY_ROLE).name in selected:
                    sm.select(idx, sm.SelectionFlag.Select | sm.SelectionFlag.Rows)
        self._update_footer()

    def _update_footer(self, *a):
        ents = [e for e in self.model.entries if e.name != ".."]
        sel = self.selected_entries()
        if sel:
            size = sum(e.size for e in sel if not e.is_dir)
            self.footer.setText(tr("{n} sélectionné(s) · {s}", n=len(sel), s=human_size(size)))
        else:
            nd = sum(1 for e in ents if e.is_dir)
            self.footer.setText(tr("{d} dossier(s), {f} fichier(s)", d=nd, f=len(ents) - nd))

    def select_name(self, name):
        for row in range(self.proxy.rowCount()):
            idx = self.proxy.index(row, 0)
            if self.proxy.data(idx, ENTRY_ROLE).name == name:
                self.view.setCurrentIndex(idx)
                self.view.scrollTo(idx)
                return

    # -------------------------------------------------------------- actions
    def go_up(self):
        if self.cwd != "/":
            child = os.path.basename(self.cwd.rstrip("/"))
            self.navigate(self.parent_of(self.cwd), select=child)

    def _activate_current(self):
        idx = self.view.currentIndex()
        if idx.isValid():
            self._activate(idx)

    def _activate(self, idx):
        e = self.proxy.data(idx.siblingAtColumn(0), ENTRY_ROLE)
        if e is None:
            return
        if e.name == "..":
            self.go_up()
        elif e.is_dir:
            self.navigate(self.join(self.cwd, e.name))
        else:
            self.open_file(e)

    def transfer_selected(self):
        ents = self.selected_entries()
        if ents:
            self.tab.transfer(self, ents)

    def ask_mkdir(self):
        name, ok = QInputDialog.getText(self, tr("Nouveau dossier"), tr("Nom du dossier :"))
        if ok and name.strip():
            self.mkdir(name.strip())

    def ask_rename(self):
        e = self.current_entry()
        if not e or e.name == "..":
            return
        name, ok = QInputDialog.getText(self, tr("Renommer"), tr("Nouveau nom :"), text=e.name)
        if ok and name.strip() and name.strip() != e.name:
            self.rename(e, name.strip())

    def ask_delete(self):
        ents = self.selected_entries()
        if not ents:
            return
        if settings.get("confirm_delete", True):
            what = ents[0].name if len(ents) == 1 else tr("{n} éléments", n=len(ents))
            r = QMessageBox.question(self, tr("Supprimer"), tr("Supprimer définitivement {w} ?", w=what))
            if r != QMessageBox.StandardButton.Yes:
                return
        self.delete(ents)

    def _menu(self, pos):
        ents = self.selected_entries()
        m = QMenu(self)
        if ents:
            if self.is_remote:
                m.addAction(icons.icon("download"), tr("Télécharger") + "\tF5", self.transfer_selected)
            else:
                act = m.addAction(icons.icon("upload"), tr("Envoyer") + "\tF5", self.transfer_selected)
                act.setEnabled(self.tab.session is not None and self.tab.session.connected)
            if len(ents) == 1 and not ents[0].is_dir and not self.is_remote:
                m.addAction(icons.icon("open"), tr("Ouvrir"), lambda: self.open_file(ents[0]))
            m.addSeparator()
            if len(ents) == 1:
                m.addAction(icons.icon("rename"), tr("Renommer") + "\tF2", self.ask_rename)
            m.addAction(icons.icon("delete"), tr("Supprimer") + "\tSuppr", self.ask_delete)
            if self.supports_chmod():
                m.addAction(icons.icon("lock"), tr("Permissions…"), lambda: self.ask_chmod(ents))
            m.addSeparator()
            m.addAction(icons.icon("copy"), tr("Copier le chemin"),
                        lambda: QApplication.clipboard().setText(
                            "\n".join(self.join(self.cwd, e.name) for e in ents)))
            m.addSeparator()
        m.addAction(icons.icon("new-folder"), tr("Nouveau dossier") + "\tF7", self.ask_mkdir)
        m.addAction(icons.icon("refresh"), tr("Actualiser") + "\tCtrl+R", self.refresh)
        if not self.is_remote:
            m.addAction(icons.icon("open"), tr("Ouvrir dans le gestionnaire de fichiers"),
                        lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.cwd)))
        m.exec(self.view.viewport().mapToGlobal(pos))

    def ask_chmod(self, ents):
        from .dialogs import PermissionsDialog
        first = ents[0]
        d = PermissionsDialog(self, first.mode if first.mode is not None else 0o644,
                              first.name if len(ents) == 1 else tr("{n} éléments", n=len(ents)),
                              any(e.is_dir for e in ents))
        if d.exec():
            self.chmod(ents, d.mode(), d.recursive())

    # ------------------------------------------------------- drag and drop
    def handle_drop(self, data, target):
        dest = self.join(self.cwd, target.name) if target and target.name != ".." else (
            self.parent_of(self.cwd) if target else self.cwd)
        return self.tab.drop_on(self, data, dest)

    # ------------------------------------------------------------ abstract
    def navigate(self, path, select=None): ...
    def refresh(self): ...
    def go_home(self): ...
    def mkdir(self, name): ...
    def rename(self, e, new): ...
    def delete(self, ents): ...
    def chmod(self, ents, mode, recursive): ...
    def supports_chmod(self): return True
    def open_file(self, e): ...
    def make_mime(self, entries): ...
    def can_accept(self, data): ...


# --------------------------------------------------------------------------- local
def _owner(uid, gid):
    try:
        u = pwd.getpwuid(uid).pw_name
    except KeyError:
        u = str(uid)
    try:
        g = grp.getgrgid(gid).gr_name
    except KeyError:
        g = str(gid)
    return u, g


class LocalPanel(FilePanel):
    is_remote = False

    def __init__(self, tab):
        super().__init__(tab, tr("Cet ordinateur"), "computer")
        start = settings.get("local_dir") or os.path.expanduser("~")
        if tab.site and tab.site.local_dir and os.path.isdir(os.path.expanduser(tab.site.local_dir)):
            start = os.path.expanduser(tab.site.local_dir)
        if not os.path.isdir(start):
            start = os.path.expanduser("~")
        self.navigate(start)

    def list_local(self, path):
        out = []
        with os.scandir(path) as it:
            for d in it:
                try:
                    st = d.stat(follow_symlinks=True)
                except OSError:
                    try:
                        st = d.stat(follow_symlinks=False)
                    except OSError:
                        continue
                is_link = d.is_symlink()
                u, g = _owner(st.st_uid, st.st_gid)
                e = Entry(d.name, statmod.S_ISDIR(st.st_mode), 0 if statmod.S_ISDIR(st.st_mode) else st.st_size,
                          st.st_mtime, statmod.S_IMODE(st.st_mode), u, g, is_link,
                          os.readlink(d.path) if is_link else "")
                out.append(e)
        return out

    def navigate(self, path, select=None):
        path = os.path.abspath(os.path.expanduser(path))
        try:
            entries = self.list_local(path)
        except OSError as e:
            QMessageBox.warning(self, tr("Erreur"), f"{path}\n{e.strerror or e}")
            return
        changed = path != self.cwd
        self.cwd = path
        self.pathbar.set_path(path)
        self.set_entries(entries, keep_selection=not changed)
        if select:
            self.select_name(select)
        settings["local_dir"] = path

    def refresh(self):
        self.navigate(self.cwd)

    def refresh_if(self, d):
        if os.path.abspath(d) == self.cwd:
            self.refresh()

    def go_home(self):
        self.navigate(os.path.expanduser("~"))

    def _try(self, fn):
        try:
            fn()
        except OSError as e:
            QMessageBox.warning(self, tr("Erreur"), str(e))
        self.refresh()

    def mkdir(self, name):
        self._try(lambda: os.mkdir(os.path.join(self.cwd, name)))
        self.select_name(name)

    def rename(self, e, new):
        self._try(lambda: os.rename(os.path.join(self.cwd, e.name), os.path.join(self.cwd, new)))
        self.select_name(new)

    def delete(self, ents):
        def go():
            for e in ents:
                p = os.path.join(self.cwd, e.name)
                if e.is_dir and not e.is_link:
                    shutil.rmtree(p)
                else:
                    os.remove(p)
        self._try(go)

    def chmod(self, ents, mode, recursive):
        def go():
            for e in ents:
                p = os.path.join(self.cwd, e.name)
                os.chmod(p, mode)
                if recursive and e.is_dir:
                    for root, dirs, files in os.walk(p):
                        for n in dirs + files:
                            os.chmod(os.path.join(root, n), mode)
        self._try(go)

    def open_file(self, e):
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.join(self.cwd, e.name)))

    def make_mime(self, entries):
        return local_mime([os.path.join(self.cwd, e.name) for e in entries])

    def can_accept(self, data):
        return data.hasFormat(REMOTE_MIME)


# --------------------------------------------------------------------------- remote
class RemotePanel(FilePanel):
    is_remote = True

    def __init__(self, tab):
        super().__init__(tab, tab.site.label(), "server")
        self.set_enabled(False)
        self._pending = None

    def set_enabled(self, on):
        for w in (self.view, self.b_back, self.b_home, self.b_refresh, self.b_mkdir, self.pathbar, self.filter):
            w.setEnabled(on)

    @property
    def session(self):
        return self.tab.session

    def _busy(self, on):
        self.loading = on
        if on:
            self.footer.setText(tr("Chargement…"))
            self.view.viewport().setCursor(Qt.CursorShape.BusyCursor)
        else:
            self.view.viewport().unsetCursor()

    def _error(self, e):
        self.tab.win.log("error", f"{self.tab.site.label()}: {e}")
        QMessageBox.warning(self, tr("Erreur"), str(e) or e.__class__.__name__)

    def navigate(self, path, select=None):
        if not self.session:
            return
        target = path if path.startswith("/") else posixpath.join(self.cwd, path)

        def job(fs):
            p = posixpath.normpath(target) if fs.__class__.__name__ == "FTPFS" else target
            p = fs.normalize(p)
            return p, fs.listdir(p)

        def ok(res):
            self._busy(False)
            p, entries = res
            changed = p != self.cwd
            self.cwd = p
            self.pathbar.set_path(p)
            self.set_entries(entries, keep_selection=not changed)
            if select:
                self.select_name(select)

        def err(e):
            self._busy(False)
            self._update_footer()
            self._error(e)

        self._busy(True)
        self.session.run(job, ok, err)

    def refresh(self):
        self.navigate(self.cwd)

    def refresh_if(self, d):
        if not self.loading and d.rstrip("/") == self.cwd.rstrip("/"):
            self.refresh()

    def go_home(self):
        if self.session:
            self.navigate(self.session.home)

    def _op(self, fn, select=None):
        def err(e):
            self._error(e)
            self.refresh()
        self.session.run(fn, lambda _: self.navigate(self.cwd, select), err)

    def mkdir(self, name):
        p = posixpath.join(self.cwd, name)
        self._op(lambda fs: fs.mkdir(p), name)

    def rename(self, e, new):
        a, b = posixpath.join(self.cwd, e.name), posixpath.join(self.cwd, new)
        self._op(lambda fs: fs.rename(a, b), new)

    def delete(self, ents):
        cwd = self.cwd

        def job(fs):
            for e in ents:
                p = posixpath.join(cwd, e.name)
                if e.is_dir and not e.is_link:
                    fs.remove_tree(p)
                else:
                    fs.remove(p)
        self._op(job)

    def supports_chmod(self):
        return self.session is not None and self.tab.site.protocol in ("sftp", "scp", "ftp", "ftps", "ftps-implicit")

    def chmod(self, ents, mode, recursive):
        cwd = self.cwd

        def walk(fs, p):
            for c in fs.listdir(p):
                cp = posixpath.join(p, c.name)
                fs.chmod(cp, mode)
                if c.is_dir and not c.is_link:
                    walk(fs, cp)

        def job(fs):
            for e in ents:
                p = posixpath.join(cwd, e.name)
                fs.chmod(p, mode)
                if recursive and e.is_dir:
                    walk(fs, p)
        self._op(job)

    def open_file(self, e):
        self.tab.transfer(self, [e])

    def make_mime(self, entries):
        items = [(posixpath.join(self.cwd, e.name), e.is_dir, e.size) for e in entries]
        return remote_mime(id(self.tab), items)

    def can_accept(self, data):
        return data.hasUrls() and self.session is not None and self.session.connected
