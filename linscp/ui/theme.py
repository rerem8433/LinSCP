"""Light / dark theme on top of Qt's Fusion style."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from . import icons

LIGHT = dict(bg="#F5F7FA", base="#FFFFFF", alt="#F8FAFC", text="#1F2733", muted="#6B7685",
             border="#DCE1E8", hover="#EAF0FF", sel=icons.ACCENT, seltext="#FFFFFF", header="#F0F3F7",
             button="#FFFFFF")
DARK = dict(bg="#1B1F26", base="#22272F", alt="#262C35", text="#E6E9EE", muted="#9AA4B2",
            border="#343B46", hover="#2C3A55", sel=icons.ACCENT, seltext="#FFFFFF", header="#262C35",
            button="#2A303A")

current = LIGHT
is_dark = False


def _system_dark(app: QApplication) -> bool:
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def apply(app: QApplication, mode: str = "system"):
    global current, is_dark
    app.setStyle("Fusion")
    is_dark = _system_dark(app) if mode == "system" else mode == "dark"
    c = DARK if is_dark else LIGHT
    current = c
    pal = QPalette()
    R = QPalette.ColorRole
    for role, key in ((R.Window, "bg"), (R.Base, "base"), (R.AlternateBase, "alt"), (R.Text, "text"),
                      (R.WindowText, "text"), (R.Button, "button"), (R.ButtonText, "text"),
                      (R.Highlight, "sel"), (R.HighlightedText, "seltext"), (R.ToolTipBase, "base"),
                      (R.ToolTipText, "text"), (R.PlaceholderText, "muted")):
        pal.setColor(role, QColor(c[key]))
    pal.setColor(QPalette.ColorGroup.Disabled, R.Text, QColor(c["muted"]))
    pal.setColor(QPalette.ColorGroup.Disabled, R.ButtonText, QColor(c["muted"]))
    pal.setColor(QPalette.ColorGroup.Disabled, R.WindowText, QColor(c["muted"]))
    pal.setColor(R.Link, QColor(icons.ACCENT))
    app.setPalette(pal)
    icons.set_text_color(c["text"])
    app.setStyleSheet(STYLE.format(**c))


STYLE = """
* {{ font-size: 10pt; }}
QMainWindow, QDialog {{ background: {bg}; }}
QToolBar {{ background: {bg}; border: none; padding: 4px 6px; spacing: 2px; }}
QToolBar::separator {{ background: {border}; width: 1px; margin: 6px 6px; }}
QToolButton {{ border: 1px solid transparent; border-radius: 7px; padding: 5px; color: {text}; }}
QToolButton:hover {{ background: {hover}; }}
QToolButton:pressed, QToolButton:checked {{ background: {hover}; border-color: {border}; }}
QToolButton:disabled {{ color: {muted}; }}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{
    background: {base}; border: 1px solid {border}; border-radius: 7px; padding: 5px 8px;
    selection-background-color: {sel}; selection-color: {seltext}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {sel}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QPushButton {{ background: {button}; border: 1px solid {border}; border-radius: 7px; padding: 6px 14px; }}
QPushButton:hover {{ background: {hover}; }}
QPushButton:default, QPushButton[accent="true"] {{ background: {sel}; color: {seltext}; border-color: {sel}; }}
QPushButton:default:hover, QPushButton[accent="true"]:hover {{ background: #5A92FF; }}
QPushButton:disabled {{ color: {muted}; }}
QTreeView, QListWidget, QTreeWidget, QTableView {{
    background: {base}; alternate-background-color: {alt}; border: 1px solid {border}; border-radius: 9px;
    outline: none; }}
QTreeView::item, QTreeWidget::item {{ padding: 3px 2px; border: none; }}
QTreeView::item:hover, QListWidget::item:hover, QTreeWidget::item:hover {{ background: {hover}; }}
QTreeView::item:selected, QListWidget::item:selected, QTreeWidget::item:selected {{
    background: {sel}; color: {seltext}; }}
QTreeView::item:selected:!active {{ background: {hover}; color: {text}; }}
QListWidget::item {{ padding: 7px 6px; border-radius: 6px; }}
QHeaderView::section {{ background: {header}; color: {muted}; border: none; border-bottom: 1px solid {border};
    padding: 5px 8px; font-weight: 600; }}
QHeaderView {{ background: {header}; border-top-left-radius: 9px; border-top-right-radius: 9px; }}
QTabWidget::pane {{ border: none; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{ background: transparent; border: none; padding: 7px 14px; margin-right: 2px;
    border-top-left-radius: 8px; border-top-right-radius: 8px; color: {muted}; }}
QTabBar::tab:selected {{ background: {base}; color: {text}; }}
QTabBar::tab:hover:!selected {{ background: {hover}; }}
QSplitter::handle {{ background: transparent; }}
QStatusBar {{ background: {bg}; color: {muted}; }}
QStatusBar::item {{ border: none; }}
QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background: {bg}; padding: 6px 10px; }}
QMenu {{ background: {base}; border: 1px solid {border}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 10px; border-radius: 5px; }}
QMenu::item:selected {{ background: {hover}; color: {text}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 6px; }}
QMenuBar {{ background: {bg}; }}
QMenuBar::item:selected {{ background: {hover}; border-radius: 5px; }}
QProgressBar {{ background: {alt}; border: none; border-radius: 4px; height: 8px; text-align: center;
    color: transparent; }}
QProgressBar::chunk {{ background: {sel}; border-radius: 4px; }}
QGroupBox {{ border: 1px solid {border}; border-radius: 9px; margin-top: 14px; padding: 10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {muted}; font-weight: 600; }}
QLabel[muted="true"] {{ color: {muted}; }}
QLabel[title="true"] {{ font-size: 12pt; font-weight: 600; }}
QFrame#panelHeader {{ background: transparent; }}
QFrame#card {{ background: {base}; border: 1px solid {border}; border-radius: 12px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
"""
