"""Entry point."""
from __future__ import annotations

import sys


def main():
    from PyQt6.QtWidgets import QApplication

    import os
    from . import APP_NAME, __version__
    if os.environ.get("LINSCP_DEBUG"):
        print(f"[linscp] LinSCP {__version__} — mode diagnostic", flush=True)
    from .config import settings
    from .ui import icons, theme

    QApplication.setApplicationName(APP_NAME)
    QApplication.setDesktopFileName("linscp")
    app = QApplication(sys.argv)
    theme.apply(app, settings.get("theme", "system"))
    app.setWindowIcon(icons.app_icon())
    from .bridge import bridge
    bridge()   # created in the GUI thread
    from .ui.mainwindow import MainWindow
    w = MainWindow()
    w.show()
    # linscp sftp://user@host/path  → quick connect
    args = [a for a in sys.argv[1:] if "://" in a]
    if args:
        w.q_host.setText(args[0])
        w.quick_connect()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
