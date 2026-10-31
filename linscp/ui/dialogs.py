"""Small dialogs: host-key trust, file exists, permissions, password, about."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QVBoxLayout)

from .. import __version__
from ..i18n import tr
from . import icons
from .models import human_size


def _header(lay, ico, title, color=None):
    row = QHBoxLayout()
    il = QLabel()
    il.setPixmap(icons.icon(ico, color).pixmap(30, 30))
    row.addWidget(il, 0, Qt.AlignmentFlag.AlignTop)
    t = QLabel(title)
    t.setProperty("title", True)
    t.setWordWrap(True)
    row.addWidget(t, 1)
    lay.addLayout(row)


def ask_trust(parent, kind, host, fp, changed) -> bool:
    d = QDialog(parent)
    d.setWindowTitle(tr("Vérification du serveur"))
    lay = QVBoxLayout(d)
    lay.setSpacing(12)
    if changed:
        _header(lay, "alert", tr("La clé du serveur a changé !"), "#E5484D")
        msg = tr("L'empreinte de {h} ne correspond plus à celle enregistrée. Cela peut venir d'une "
                 "réinstallation du serveur… ou d'une attaque de type « man-in-the-middle ».", h=host)
    else:
        _header(lay, "lock", tr("Premier contact avec ce serveur"))
        what = tr("clé d'hôte SSH") if kind == "ssh" else tr("certificat TLS")
        msg = tr("LinSCP ne connaît pas encore la {w} de {h}. Vérifiez l'empreinte avant de continuer.",
                 w=what, h=host)
    m = QLabel(msg)
    m.setWordWrap(True)
    lay.addWidget(m)
    f = QLineEdit(fp)
    f.setReadOnly(True)
    f.setStyleSheet("font-family: monospace;")
    f.setMinimumWidth(460)
    lay.addWidget(f)
    bb = QDialogButtonBox()
    ok = bb.addButton(tr("Faire confiance et continuer"), QDialogButtonBox.ButtonRole.AcceptRole)
    ok.setProperty("accent", True)
    bb.addButton(tr("Annuler"), QDialogButtonBox.ButtonRole.RejectRole)
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)
    return d.exec() == QDialog.DialogCode.Accepted


class ExistsDialog(QDialog):
    def __init__(self, parent, item, local_size, remote_size, can_resume):
        super().__init__(parent)
        self.setWindowTitle(tr("Le fichier existe déjà"))
        self.action = "skip"
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        _header(lay, "alert", tr("« {n} » existe déjà", n=item.name), "#D9A400")
        if item.direction == "down":
            src, dst = tr("distant"), tr("local")
            ss, ds = remote_size, local_size
        else:
            src, dst = tr("local"), tr("distant")
            ss, ds = local_size, remote_size
        info = QLabel(tr("Source ({a}) : {s}\nDestination ({b}) : {d}", a=src, s=human_size(ss), b=dst,
                         d=human_size(ds)))
        info.setProperty("muted", True)
        lay.addWidget(info)
        self.all = QCheckBox(tr("Appliquer à tous les fichiers suivants"))
        lay.addWidget(self.all)
        row = QHBoxLayout()
        row.addStretch(1)
        for key, label in (("skip", tr("Ignorer")), ("resume", tr("Reprendre")), ("overwrite", tr("Écraser"))):
            b = QPushButton(label)
            if key == "resume":
                b.setEnabled(can_resume and ds < ss)
                b.setToolTip(tr("Compléter un transfert interrompu"))
            if key == "overwrite":
                b.setProperty("accent", True)
                b.setDefault(True)
            b.clicked.connect(lambda _, k=key: self._pick(k))
            row.addWidget(b)
        lay.addLayout(row)

    def _pick(self, k):
        self.action = k
        self.accept()


class PermissionsDialog(QDialog):
    def __init__(self, parent, mode, name, has_dir):
        super().__init__(parent)
        self.setWindowTitle(tr("Permissions"))
        lay = QVBoxLayout(self)
        _header(lay, "lock", name)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        self.boxes = {}
        for c, t in enumerate((tr("Lecture"), tr("Écriture"), tr("Exécution")), 1):
            h = QLabel(t)
            h.setProperty("muted", True)
            grid.addWidget(h, 0, c, Qt.AlignmentFlag.AlignCenter)
        for r, (who, shift) in enumerate(((tr("Propriétaire"), 6), (tr("Groupe"), 3), (tr("Autres"), 0)), 1):
            grid.addWidget(QLabel(who), r, 0)
            for c, bit in enumerate((4, 2, 1), 1):
                cb = QCheckBox()
                cb.setChecked(bool(mode & (bit << shift)))
                cb.toggled.connect(self._sync_octal)
                self.boxes[(shift, bit)] = cb
                grid.addWidget(cb, r, c, Qt.AlignmentFlag.AlignCenter)
        lay.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Octal :")))
        self.octal = QLineEdit()
        self.octal.setMaximumWidth(80)
        self.octal.setInputMask("9999")
        self.octal.textEdited.connect(self._sync_boxes)
        row.addWidget(self.octal)
        row.addStretch(1)
        lay.addLayout(row)
        self.rec = QCheckBox(tr("Appliquer aussi au contenu des dossiers"))
        self.rec.setVisible(has_dir)
        lay.addWidget(self.rec)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._sync_octal()

    def mode(self) -> int:
        m = 0
        for (shift, bit), cb in self.boxes.items():
            if cb.isChecked():
                m |= bit << shift
        return m

    def recursive(self):
        return self.rec.isChecked()

    def _sync_octal(self, *a):
        self.octal.setText(f"{self.mode():04o}")

    def _sync_boxes(self, t):
        try:
            m = int(t.strip() or "0", 8)
        except ValueError:
            return
        for (shift, bit), cb in self.boxes.items():
            cb.blockSignals(True)
            cb.setChecked(bool(m & (bit << shift)))
            cb.blockSignals(False)


def ask_password(parent, site, passphrase=False):
    d = QDialog(parent)
    d.setWindowTitle(tr("Authentification"))
    lay = QVBoxLayout(d)
    _header(lay, "key", site.label())
    lab = QLabel(tr("Phrase de passe de la clé :") if passphrase else
                 tr("Mot de passe pour {u}@{h} :", u=site.user, h=site.host))
    lay.addWidget(lab)
    e = QLineEdit()
    e.setEchoMode(QLineEdit.EchoMode.Password)
    e.setMinimumWidth(320)
    lay.addWidget(e)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)
    if d.exec() == QDialog.DialogCode.Accepted:
        return e.text()
    return None


class AboutDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("À propos de LinSCP"))
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(84, 84))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)
        t = QLabel(f"LinSCP {__version__}")
        t.setProperty("title", True)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        for s in (tr("Client SFTP, SCP et FTP/FTPS natif pour Linux"),
                  tr("Inspiré de WinSCP · réécrit en Python + Qt 6"),
                  "© ParadoxXx Squad"):
            l = QLabel(s)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setProperty("muted", True)
            lay.addWidget(l)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
