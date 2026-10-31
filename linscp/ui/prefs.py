"""Preferences."""
from __future__ import annotations

from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
                             QLabel, QVBoxLayout)

from ..config import settings
from ..i18n import tr
from . import icons


class PrefsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Préférences"))
        self.setWindowIcon(icons.icon("settings"))
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)

        g1 = QGroupBox(tr("Interface"))
        f1 = QFormLayout(g1)
        self.lang = QComboBox()
        for code, label in (("", tr("Langue du système")), ("fr", "Français"), ("en", "English")):
            self.lang.addItem(label, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(settings.get("language", ""))))
        self.layout_ = QComboBox()
        self.layout_.addItem(icons.icon("dual"), tr("Double panneau (local + distant)"), "dual")
        self.layout_.addItem(icons.icon("single"), tr("Panneau simple (distant seul)"), "single")
        self.layout_.setCurrentIndex(max(0, self.layout_.findData(settings.get("layout", "dual"))))
        self.theme = QComboBox()
        for code, label in (("system", tr("Suivre le système")), ("light", tr("Clair")), ("dark", tr("Sombre"))):
            self.theme.addItem(label, code)
        self.theme.setCurrentIndex(max(0, self.theme.findData(settings.get("theme", "system"))))
        self.hidden = QCheckBox(tr("Afficher les fichiers cachés"))
        self.hidden.setChecked(bool(settings.get("show_hidden")))
        self.confirm = QCheckBox(tr("Confirmer avant de supprimer"))
        self.confirm.setChecked(bool(settings.get("confirm_delete", True)))
        f1.addRow(tr("Langue"), self.lang)
        f1.addRow(tr("Disposition"), self.layout_)
        f1.addRow(tr("Thème"), self.theme)
        f1.addRow("", self.hidden)
        f1.addRow("", self.confirm)
        lay.addWidget(g1)

        g2 = QGroupBox(tr("Transferts"))
        f2 = QFormLayout(g2)
        self.parallel = QComboBox()
        for n in range(1, 7):
            self.parallel.addItem(str(n), n)
        self.parallel.setCurrentIndex(max(0, min(5, int(settings.get("parallel", 2)) - 1)))
        self.exists = QComboBox()
        for code, label in (("ask", tr("Demander")), ("overwrite", tr("Écraser")),
                            ("resume", tr("Reprendre si possible")), ("skip", tr("Ignorer"))):
            self.exists.addItem(label, code)
        self.exists.setCurrentIndex(max(0, self.exists.findData(settings.get("on_exists", "ask"))))
        self.ptime = QCheckBox(tr("Conserver la date de modification"))
        self.ptime.setChecked(bool(settings.get("preserve_time", True)))
        f2.addRow(tr("Transferts simultanés"), self.parallel)
        f2.addRow(tr("Si le fichier existe"), self.exists)
        f2.addRow("", self.ptime)
        lay.addWidget(g2)

        self.note = QLabel(tr("Le changement de langue s'applique au prochain démarrage."))
        self.note.setProperty("muted", True)
        self.note.setVisible(False)
        self.lang.currentIndexChanged.connect(lambda: self.note.setVisible(True))
        lay.addWidget(self.note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _ok(self):
        settings.update(language=self.lang.currentData(), layout=self.layout_.currentData(),
                        theme=self.theme.currentData(), show_hidden=self.hidden.isChecked(),
                        confirm_delete=self.confirm.isChecked(), parallel=self.parallel.currentData(),
                        on_exists=self.exists.currentData(), preserve_time=self.ptime.isChecked())
        settings.save()
        self.accept()
