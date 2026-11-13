"""Site manager."""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                             QToolButton, QVBoxLayout, QWidget)

from ..i18n import tr
from ..protocols import PROTOCOL_LABELS, PROTOCOLS, Site
from ..sites import HAVE_KEYRING, SiteStore, get_password
from . import icons


def proto_label(p):
    return tr(PROTOCOL_LABELS[p])


class SiteManager(QDialog):
    def __init__(self, parent, store: SiteStore, select: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Gestionnaire de sites"))
        self.setWindowIcon(icons.icon("sites"))
        self.resize(780, 500)
        self.store = store
        self.result_site = None
        self.result_sid = None
        self.cur = None            # sid being edited (None = new unsaved)
        self._loading = False
        self._dirty = False

        # left: list ---------------------------------------------------------
        left = QVBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Rechercher…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        left.addWidget(self.search)
        self.list = QListWidget()
        self.list.setMinimumWidth(230)
        self.list.currentItemChanged.connect(self._on_select)
        self.list.itemDoubleClicked.connect(lambda _: self._connect())
        left.addWidget(self.list, 1)
        lb = QHBoxLayout()
        for ico, tip, fn in (("plus", tr("Nouveau site"), self._new), ("copy", tr("Dupliquer"), self._dup),
                             ("delete", tr("Supprimer"), self._delete)):
            b = QToolButton()
            b.setIcon(icons.icon(ico))
            b.setToolTip(tip)
            b.clicked.connect(fn)
            lb.addWidget(b)
        lb.addStretch(1)
        left.addLayout(lb)

        # right: form --------------------------------------------------------
        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.f_name = QLineEdit()
        self.f_name.setPlaceholderText(tr("Ex. : NAS du salon"))
        self.f_proto = QComboBox()
        for p in PROTOCOLS:
            self.f_proto.addItem(proto_label(p), p)
        self.f_host = QLineEdit()
        self.f_host.setPlaceholderText("192.168.1.10")
        # plain text field (like the quick-connect bar): empty = protocol's default port,
        # shown as placeholder. A QSpinBox silently refused digits typed after its value.
        self.f_port = QLineEdit()
        self.f_port.setValidator(QIntValidator(1, 65535, self.f_port))
        self.f_port.setFixedWidth(80)
        self.f_port.setToolTip(tr("Port (vide = port par défaut)"))
        hp = QHBoxLayout()
        hp.addWidget(self.f_host, 1)
        hp.addWidget(QLabel(tr("Port")))
        hp.addWidget(self.f_port)
        self.f_user = QLineEdit()
        self.f_auth = QComboBox()
        self.f_auth.addItem(tr("Mot de passe"), "password")
        self.f_auth.addItem(tr("Clé SSH"), "key")
        self.f_pass = QLineEdit()
        self.f_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.f_save = QCheckBox(tr("Mémoriser dans le trousseau du système"))
        if not HAVE_KEYRING:
            self.f_save.setEnabled(False)
            self.f_save.setToolTip(tr("Aucun trousseau (Secret Service) disponible : le mot de passe sera demandé à chaque connexion."))
        self.f_key = QLineEdit()
        self.f_key.setPlaceholderText(tr("Vide = clés de ~/.ssh et agent SSH"))
        kb = QToolButton()
        kb.setText("…")
        kb.clicked.connect(self._pick_key)
        kh = QHBoxLayout()
        kh.addWidget(self.f_key, 1)
        kh.addWidget(kb)
        self.key_row = QWidget()
        self.key_row.setLayout(kh)
        kh.setContentsMargins(0, 0, 0, 0)
        self.f_rdir = QLineEdit()
        self.f_rdir.setPlaceholderText(tr("Vide = dossier personnel"))
        self.f_ldir = QLineEdit()
        self.f_ldir.setPlaceholderText(tr("Vide = dernier dossier utilisé"))
        lbtn = QToolButton()
        lbtn.setText("…")
        lbtn.clicked.connect(self._pick_ldir)
        lh = QHBoxLayout()
        lh.setContentsMargins(0, 0, 0, 0)
        lh.addWidget(self.f_ldir, 1)
        lh.addWidget(lbtn)
        self.f_passive = QCheckBox(tr("Mode passif (recommandé)"))
        self.f_passive.setChecked(True)

        self.l_auth = QLabel(tr("Authentification"))
        self.l_pass = QLabel(tr("Mot de passe"))
        self.l_key = QLabel(tr("Fichier de clé"))
        self.l_passive = QLabel("FTP")
        form.addRow(tr("Nom"), self.f_name)
        form.addRow(tr("Protocole"), self.f_proto)
        form.addRow(tr("Hôte"), hp)
        form.addRow(tr("Utilisateur"), self.f_user)
        form.addRow(self.l_auth, self.f_auth)
        form.addRow(self.l_key, self.key_row)
        form.addRow(self.l_pass, self.f_pass)
        form.addRow("", self.f_save)
        form.addRow(tr("Dossier distant"), self.f_rdir)
        form.addRow(tr("Dossier local"), lh)
        form.addRow(self.l_passive, self.f_passive)

        for w in (self.f_name, self.f_host, self.f_user, self.f_pass, self.f_key, self.f_rdir, self.f_ldir):
            w.textEdited.connect(self._touch)
        self.f_port.textEdited.connect(self._touch)
        self.f_save.toggled.connect(self._touch)
        self.f_passive.toggled.connect(self._touch)
        self.f_proto.currentIndexChanged.connect(self._proto_changed)
        self.f_auth.currentIndexChanged.connect(self._auth_changed)

        # buttons ------------------------------------------------------------
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.b_save = QPushButton(icons.icon("save"), tr("Enregistrer"))
        self.b_save.clicked.connect(self._save)
        self.b_conn = QPushButton(icons.icon("connect", "#FFFFFF"), tr("Connexion"))
        self.b_conn.setProperty("accent", True)
        self.b_conn.setDefault(True)
        self.b_conn.clicked.connect(self._connect)
        close = QPushButton(tr("Fermer"))
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        bottom.addWidget(self.b_save)
        bottom.addWidget(self.b_conn)

        right = QVBoxLayout()
        right.addWidget(card)
        right.addStretch(1)
        right.addLayout(bottom)
        root = QHBoxLayout(self)
        root.setSpacing(14)
        root.addLayout(left)
        root.addLayout(right, 1)

        self._reload(select)
        if self.list.count() == 0:
            self._new()

    # ---------------------------------------------------------------- list
    def _reload(self, select=None):
        self.list.blockSignals(True)
        self.list.clear()
        for sid, s in self.store.ordered():
            it = QListWidgetItem(icons.icon("server"), s.label())
            it.setData(Qt.ItemDataRole.UserRole, sid)
            it.setToolTip(f"{proto_label(s.protocol)} · {s.user + '@' if s.user else ''}{s.host}:{s.effective_port()}")
            self.list.addItem(it)
        self.list.blockSignals(False)
        target = select or self.cur
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == target:
                self.list.setCurrentRow(i)
                return
        if self.list.count():
            self.list.setCurrentRow(0)

    def _filter(self, t):
        t = t.lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(t) and t not in it.text().lower() and t not in it.toolTip().lower())

    def _on_select(self, item, prev):
        if self._dirty and prev is not None and self.cur:
            if QMessageBox.question(self, tr("Gestionnaire de sites"),
                                    tr("Enregistrer les modifications de « {n} » ?", n=prev.text())) \
                    == QMessageBox.StandardButton.Yes:
                self._save(reload=False)
        if item is None:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        self.cur = sid
        s = self.store.sites[sid]
        pw = get_password(sid) if s.save_password else ""
        self._fill(s, pw)

    def _fill(self, s: Site, pw=""):
        self._loading = True
        self.f_name.setText(s.name)
        self.f_proto.setCurrentIndex(max(0, PROTOCOLS.index(s.protocol) if s.protocol in PROTOCOLS else 0))
        self.f_host.setText(s.host)
        self.f_port.setText(str(s.port) if s.port and s.port != s.default_port() else "")
        self.f_user.setText(s.user)
        self.f_auth.setCurrentIndex(1 if s.auth == "key" else 0)
        self.f_pass.setText(pw)
        self.f_save.setChecked(s.save_password and HAVE_KEYRING)
        self.f_key.setText(s.key_file)
        self.f_rdir.setText(s.remote_dir)
        self.f_ldir.setText(s.local_dir)
        self.f_passive.setChecked(s.passive)
        self._loading = False
        self._dirty = False
        self._update_rows()

    def _touch(self, *a):
        if not self._loading:
            self._dirty = True

    def _proto_changed(self, *a):
        if not self._loading:
            old = Site(protocol=getattr(self, "_last_proto", "sftp")).default_port()
            if self.f_port.text().strip() == str(old):
                self.f_port.clear()
            self._touch()
        self._last_proto = self.f_proto.currentData()
        self._update_rows()

    def _auth_changed(self, *a):
        self._touch()
        self._update_rows()

    def _update_rows(self):
        p = self.f_proto.currentData()
        self._last_proto = p
        self.f_port.setPlaceholderText(str(Site(protocol=p).default_port()))
        ssh = p in ("sftp", "scp")
        key = ssh and self.f_auth.currentData() == "key"
        for w in (self.l_auth, self.f_auth):
            w.setVisible(ssh)
        for w in (self.l_key, self.key_row):
            w.setVisible(key)
        self.l_pass.setText(tr("Phrase de passe") if key else tr("Mot de passe"))
        for w in (self.l_passive, self.f_passive):
            w.setVisible(not ssh)

    def _site_from_form(self) -> Site:
        s = Site(name=self.f_name.text().strip(), protocol=self.f_proto.currentData(),
                 host=self.f_host.text().strip(), user=self.f_user.text().strip(),
                 auth=self.f_auth.currentData() if self.f_proto.currentData() in ("sftp", "scp") else "password",
                 key_file=self.f_key.text().strip(), remote_dir=self.f_rdir.text().strip(),
                 local_dir=self.f_ldir.text().strip(), passive=self.f_passive.isChecked(),
                 save_password=self.f_save.isChecked())
        port = int(self.f_port.text().strip() or 0)
        s.port = 0 if port == s.default_port() else port
        s.password = self.f_pass.text()
        return s

    # -------------------------------------------------------------- actions
    def _new(self):
        self.list.blockSignals(True)
        self.list.clearSelection()
        self.list.setCurrentRow(-1)
        self.list.blockSignals(False)
        self.cur = None
        self._fill(Site())
        self.f_name.setFocus()

    def _dup(self):
        if not self.cur:
            return
        s = self._site_from_form()
        s.name = (s.name or s.label()) + " " + tr("(copie)")
        self.cur = None
        self.cur = self.store.put(s)
        self._dirty = False
        self._reload(self.cur)

    def _delete(self):
        if not self.cur:
            return
        s = self.store.sites.get(self.cur)
        if QMessageBox.question(self, tr("Supprimer"), tr("Supprimer le site « {n} » ?", n=s.label())) \
                != QMessageBox.StandardButton.Yes:
            return
        self.store.delete(self.cur)
        self.cur = None
        self._dirty = False
        self._reload()
        if self.list.count() == 0:
            self._new()

    def _validate(self, s):
        if not s.host:
            QMessageBox.warning(self, tr("Gestionnaire de sites"), tr("Indiquez l'adresse du serveur."))
            self.f_host.setFocus()
            return False
        return True

    def _save(self, reload=True):
        s = self._site_from_form()
        if not self._validate(s):
            return None
        self.cur = self.store.put(s, self.cur)
        self._dirty = False
        if reload:
            self._reload(self.cur)
        return s

    def _connect(self):
        s = self._site_from_form()
        if not self._validate(s):
            return
        if self._dirty or self.cur is None:
            self._save()
        self.result_site = s
        self.result_sid = self.cur
        self.accept()

    def _pick_key(self):
        p, _ = QFileDialog.getOpenFileName(self, tr("Choisir une clé privée"), os.path.expanduser("~/.ssh"))
        if p:
            self.f_key.setText(p)
            self._touch()

    def _pick_ldir(self):
        p = QFileDialog.getExistingDirectory(self, tr("Dossier local"), self.f_ldir.text() or os.path.expanduser("~"))
        if p:
            self.f_ldir.setText(p)
            self._touch()
