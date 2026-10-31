"""File list model shared by the local and remote panels."""
from __future__ import annotations

import json
import time

from PyQt6.QtCore import QAbstractTableModel, QMimeData, QModelIndex, QSortFilterProxyModel, Qt, QUrl

from ..i18n import lang, tr
from ..protocols import Entry
from . import icons, theme

REMOTE_MIME = "application/x-linscp-remote"
COLS = ["Nom", "Taille", "Modifié", "Droits", "Propriétaire"]
ENTRY_ROLE = Qt.ItemDataRole.UserRole + 1


def human_size(n: int) -> str:
    units = ["o", "Ko", "Mo", "Go", "To"] if lang() == "fr" else ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            if u == units[0]:
                return f"{int(f)} {u}"
            s = f"{f:.1f}" if f < 100 else f"{f:.0f}"
            return (s.replace(".", ",") if lang() == "fr" else s) + f" {u}"
        f /= 1024
    return str(n)


def fmt_time(ts) -> str:
    if not ts:
        return ""
    lt = time.localtime(ts)
    return time.strftime("%d/%m/%Y %H:%M" if lang() == "fr" else "%Y-%m-%d %H:%M", lt)


class FileModel(QAbstractTableModel):
    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.entries: list[Entry] = []

    def set_entries(self, entries: list[Entry], with_parent: bool):
        self.beginResetModel()
        self.entries = ([Entry("..", True)] if with_parent else []) + list(entries)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QModelIndex()):
        return len(COLS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return tr(COLS[section])
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        e = self.entries[index.row()]
        c = index.column()
        if role == ENTRY_ROLE:
            return e
        if role == Qt.ItemDataRole.DisplayRole:
            if c == 0:
                return e.name
            if e.name == "..":
                return ""
            if c == 1:
                return "" if e.is_dir else human_size(e.size)
            if c == 2:
                return fmt_time(e.mtime)
            if c == 3:
                return e.perms
            if c == 4:
                return f"{e.owner}:{e.group}" if e.group else e.owner
        if role == Qt.ItemDataRole.DecorationRole and c == 0:
            if e.name == "..":
                return icons.icon("up")
            return icons.file_icon(e.name, e.is_dir, e.is_link, theme.is_dark)
        if role == Qt.ItemDataRole.ToolTipRole and c == 0 and e.is_link and e.link_target:
            return f"{e.name} → {e.link_target}"
        if role == Qt.ItemDataRole.TextAlignmentRole and c == 1:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole and c > 0:
            from PyQt6.QtGui import QColor
            return QColor(theme.current["muted"])
        return None

    def flags(self, index):
        f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.isValid():
            e = self.entries[index.row()]
            if e.name != "..":
                f |= Qt.ItemFlag.ItemIsDragEnabled
            if e.is_dir:
                f |= Qt.ItemFlag.ItemIsDropEnabled
        else:
            f |= Qt.ItemFlag.ItemIsDropEnabled
        return f

    # ---------------------------------------------------------- drag & drop
    def supportedDropActions(self):
        return Qt.DropAction.CopyAction

    def supportedDragActions(self):
        return Qt.DropAction.CopyAction

    def mimeTypes(self):
        return ["text/uri-list", REMOTE_MIME]

    def mimeData(self, indexes):
        rows = sorted({i.row() for i in indexes})
        entries = [self.entries[r] for r in rows if self.entries[r].name != ".."]
        return self.panel.make_mime(entries)

    def canDropMimeData(self, data, action, row, column, parent):
        return self.panel.can_accept(data)

    def dropMimeData(self, data, action, row, column, parent):
        target = None
        if parent.isValid():
            e = self.entries[parent.row()]
            if e.is_dir:
                target = e
        return self.panel.handle_drop(data, target)


class SortProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.show_hidden = False
        self.text = ""
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_hidden(self, v):
        self.show_hidden = v
        self.invalidateFilter()

    def set_text(self, t):
        self.text = t.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        e = self.sourceModel().entries[row]
        if e.name == "..":
            return True
        if not self.show_hidden and e.name.startswith("."):
            return False
        return not self.text or self.text in e.name.lower()

    def lessThan(self, left, right):
        a = self.sourceModel().entries[left.row()]
        b = self.sourceModel().entries[right.row()]
        asc = self.sortOrder() == Qt.SortOrder.AscendingOrder
        # ".." always on top, folders before files, whatever the sort order
        if a.name == ".." or b.name == "..":
            return (a.name == "..") == asc
        if a.is_dir != b.is_dir:
            return a.is_dir == asc
        c = left.column()
        if c == 1:
            ka, kb = a.size, b.size
        elif c == 2:
            ka, kb = a.mtime or 0, b.mtime or 0
        elif c == 3:
            ka, kb = a.perms, b.perms
        elif c == 4:
            ka, kb = a.owner.lower(), b.owner.lower()
        else:
            ka, kb = a.name.lower(), b.name.lower()
        if ka == kb:
            return a.name.lower() < b.name.lower()
        return ka < kb


def local_mime(paths: list[str]) -> QMimeData:
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(p) for p in paths])
    return m


def remote_mime(tab_id: int, entries: list[tuple[str, bool, int]]) -> QMimeData:
    m = QMimeData()
    m.setData(REMOTE_MIME, json.dumps({"tab": tab_id, "items": entries}).encode())
    return m
