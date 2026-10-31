"""Transfer queue widget + log."""
from __future__ import annotations

import time

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QPlainTextEdit, QStyledItemDelegate,
                             QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..i18n import tr
from ..transfers import CANCELLED, DONE, ERROR, QUEUED, RUNNING, SKIPPED, TransferItem, TransferQueue
from . import icons, theme
from .models import human_size

PROG_COL = 3
STATUS_TXT = {QUEUED: "En attente", RUNNING: "En cours", DONE: "Terminé", ERROR: "Erreur",
              CANCELLED: "Annulé", SKIPPED: "Ignoré"}
STATUS_COLOR = {DONE: "#22B573", ERROR: "#E5484D", CANCELLED: "#9AA4B2", SKIPPED: "#9AA4B2"}


class ProgressDelegate(QStyledItemDelegate):
    def paint(self, p: QPainter, opt, index):
        frac = index.data(Qt.ItemDataRole.UserRole)
        if frac is None:
            return super().paint(p, opt, index)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(opt.rect).adjusted(6, opt.rect.height() / 2 - 3, -6, -(opt.rect.height() / 2 - 3))
        path = QPainterPath()
        path.addRoundedRect(r, 3, 3)
        p.fillPath(path, QBrush(QColor(theme.current["border"])))
        if frac > 0:
            w = QRectF(r)
            w.setWidth(max(6.0, r.width() * min(frac, 1.0)))
            path2 = QPainterPath()
            path2.addRoundedRect(w, 3, 3)
            color = index.data(Qt.ItemDataRole.UserRole + 1) or icons.ACCENT
            p.fillPath(path2, QBrush(QColor(color)))
        p.restore()


class QueueView(QWidget):
    def __init__(self, queue: TransferQueue):
        super().__init__()
        self.queue = queue
        self.rows: dict[int, QTreeWidgetItem] = {}
        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels([tr("Fichier"), tr("Destination"), tr("Taille"), tr("Progression"),
                                   tr("Vitesse"), tr("État")])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setItemDelegateForColumn(PROG_COL, ProgressDelegate(self.tree))
        h = self.tree.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c, w in ((2, 90), (3, 150), (4, 90), (5, 140)):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
            h.resizeSection(c, w)
        h.setStretchLastSection(False)

        side = QVBoxLayout()
        side.setSpacing(2)
        for ico, tip, fn in (("stop", tr("Annuler la sélection"), self._cancel_sel),
                             ("retry", tr("Relancer la sélection"), self._retry_sel),
                             ("close", tr("Tout annuler"), queue.cancel_all),
                             ("clear", tr("Retirer les transferts terminés"), self.clear_finished)):
            b = QToolButton()
            b.setIcon(icons.icon(ico))
            b.setToolTip(tip)
            b.clicked.connect(fn)
            side.addWidget(b)
        side.addStretch(1)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.tree, 1)
        lay.addLayout(side)

        queue.item_added.connect(self._added)
        queue.item_changed.connect(self._changed)

    def _added(self, it: TransferItem):
        row = QTreeWidgetItem()
        row.setIcon(0, icons.icon("upload" if it.direction == "up" else "download",
                                  "#22B573" if it.direction == "up" else icons.ACCENT))
        row.setText(0, it.name)
        row.setToolTip(0, it.src)
        row.setText(1, it.dst)
        row.setToolTip(1, it.dst)
        row.setData(0, Qt.ItemDataRole.UserRole, it.id)
        row.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.setTextAlignment(4, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.rows[it.id] = row
        row._item = it
        self.tree.addTopLevelItem(row)
        self._changed(it)

    def _changed(self, it: TransferItem):
        row = self.rows.get(it.id)
        if row is None:
            return
        if it.is_dir:
            row.setText(2, tr("Dossier") if not it.files else tr("{n} élém.", n=it.files))
            row.setIcon(0, icons.file_icon("", True))
        else:
            row.setText(2, human_size(it.size) if it.size else "")
        frac = (it.done / it.size) if it.size and not it.is_dir else (1.0 if it.status == DONE else 0.0)
        row.setData(PROG_COL, Qt.ItemDataRole.UserRole, frac)
        row.setData(PROG_COL, Qt.ItemDataRole.UserRole + 1, STATUS_COLOR.get(it.status) if it.status != DONE else "#22B573")
        row.setText(4, (human_size(int(it.speed)) + "/s") if it.status == RUNNING and it.speed else "")
        txt = tr(STATUS_TXT[it.status])
        if it.status == RUNNING and it.size:
            pct = int(100 * it.done / it.size)
            txt = f"{pct} %"
            if it.speed > 0:
                rest = (it.size - it.done) / it.speed
                txt += f" · {_eta(rest)}"
        if it.status == ERROR:
            row.setToolTip(5, it.error)
            txt = f"{tr('Erreur')} : {it.error}"
        row.setText(5, txt)
        c = STATUS_COLOR.get(it.status)
        row.setForeground(5, QBrush(QColor(c)) if c else QBrush(QColor(theme.current["text"])))

    def _selected(self):
        return [r._item for r in self.tree.selectedItems()]

    def _cancel_sel(self):
        for it in self._selected():
            self.queue.cancel(it)

    def _retry_sel(self):
        for it in self._selected():
            self.queue.retry(it)

    def clear_finished(self):
        self.queue.clear_finished()
        for iid, row in list(self.rows.items()):
            if row._item.status not in (QUEUED, RUNNING):
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(row))
                del self.rows[iid]


def _eta(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec} s"
    if sec < 3600:
        return f"{sec // 60} min {sec % 60:02d}"
    return f"{sec // 3600} h {sec % 3600 // 60:02d}"


class LogView(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setStyleSheet("font-family: monospace; font-size: 9pt;")

    def add(self, level: str, msg: str):
        color = {"error": "#E5484D", "ok": "#22B573", "warn": "#D9A400"}.get(level, theme.current["muted"])
        ts = time.strftime("%H:%M:%S")
        safe = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.appendHtml(f'<span style="color:{theme.current["muted"]}">{ts}</span> '
                        f'<span style="color:{color}">{safe}</span>')
