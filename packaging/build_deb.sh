#!/bin/bash
# Build linscp_<version>_all.deb  —  usage: ./packaging/build_deb.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/linscp/__init__.py")"
OUT="$ROOT/dist"
STAGE="$(mktemp -d)"
PKG="$STAGE/linscp_${VERSION}_all"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$PKG/DEBIAN" "$PKG/usr/bin" "$PKG/usr/lib/linscp" "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/scalable/apps" "$PKG/usr/share/doc/linscp"
for s in 48 128 256; do mkdir -p "$PKG/usr/share/icons/hicolor/${s}x${s}/apps"; done

# application (without caches / tests)
rsync -a --exclude '__pycache__' --exclude '*.pyc' "$ROOT/linscp" "$PKG/usr/lib/linscp/"

cat > "$PKG/usr/bin/linscp" <<'EOF'
#!/bin/sh
# System python on purpose: PyQt6 / paramiko come from apt
export PYTHONPATH=/usr/lib/linscp${PYTHONPATH:+:$PYTHONPATH}
exec /usr/bin/python3 -m linscp "$@"
EOF
chmod 755 "$PKG/usr/bin/linscp"

cat > "$PKG/usr/share/applications/linscp.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=LinSCP
GenericName=SFTP / SCP / FTP client
GenericName[fr]=Client SFTP / SCP / FTP
Comment=Transfer files with SFTP, SCP, FTP and FTPS
Comment[fr]=Transférer des fichiers en SFTP, SCP, FTP et FTPS
Exec=linscp %u
Icon=linscp
Terminal=false
Categories=Network;FileTransfer;Utility;Qt;
Keywords=sftp;scp;ftp;ftps;ssh;winscp;transfer;
MimeType=x-scheme-handler/sftp;x-scheme-handler/scp;
StartupWMClass=LinSCP
EOF

cp "$ROOT/packaging/icons/linscp.svg" "$PKG/usr/share/icons/hicolor/scalable/apps/linscp.svg"
for s in 48 128 256; do cp "$ROOT/packaging/icons/linscp-$s.png" "$PKG/usr/share/icons/hicolor/${s}x${s}/apps/linscp.png"; done
cp "$ROOT/README.md" "$PKG/usr/share/doc/linscp/README.md"
cat > "$PKG/usr/share/doc/linscp/copyright" <<'EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: LinSCP
Source: https://github.com/rerem8433/LinSCP

Files: *
Copyright: 2026 Jérémy LAVET (ParadoxXx Squad)
License: GPL-3+
 On Debian systems, the full text of the GNU General Public License version 3
 can be found in /usr/share/common-licenses/GPL-3.
EOF

SIZE="$(du -sk "$PKG/usr" | cut -f1)"
cat > "$PKG/DEBIAN/control" <<EOF
Package: linscp
Version: $VERSION
Section: net
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-pyqt6, python3-pyqt6.qtsvg, python3-paramiko
Recommends: python3-keyring
Maintainer: ParadoxXx Squad <rerem8433@users.noreply.github.com>
Homepage: https://github.com/rerem8433/LinSCP
Description: Native SFTP / SCP / FTP / FTPS client for Linux
 LinSCP is a lightweight graphical file transfer client inspired by WinSCP,
 rewritten from scratch in Python and Qt 6: dual-pane or single-pane layout,
 site manager with passwords stored in the system keyring, parallel transfer
 queue with resume, light and dark themes, French and English interface.
EOF

cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
exit 0
EOF
cp "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"
chmod 755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"

find "$PKG" -type d -exec chmod 755 {} +
find "$PKG/usr/lib" "$PKG/usr/share" -type f -exec chmod 644 {} +
mkdir -p "$OUT"
dpkg-deb --root-owner-group --build "$PKG" "$OUT/linscp_${VERSION}_all.deb" >/dev/null
echo "$OUT/linscp_${VERSION}_all.deb"
