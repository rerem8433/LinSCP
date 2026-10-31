"""LinSCP icon set — original line icons (24×24, rounded strokes), recoloured at runtime for light/dark themes."""
from __future__ import annotations

import os

from PyQt6.QtCore import QByteArray, QRectF, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

ACCENT = "#3D7EFF"

_S = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" ' \
     'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'

LINE = {
    "connect": '<path d="M9 7V3M15 7V3"/><path d="M6 7h12v4a6 6 0 0 1-12 0z"/><path d="M12 17v4"/>',
    "disconnect": '<path d="M9 7V3M15 7V3"/><path d="M6 7h12v4a6 6 0 0 1-12 0z"/><path d="M12 17v4"/><path d="M3 3l18 18"/>',
    "sites": '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/>'
             '<path d="M7 7.5h.01M7 16.5h.01M11 7.5h6M11 16.5h6"/>',
    "up": '<path d="M12 19V5"/><path d="M6 11l6-6 6 6"/>',
    "home": '<path d="M4 11l8-7 8 7"/><path d="M6 9.5V20h12V9.5"/><path d="M10 20v-5h4v5"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 20v-4h-4"/>',
    "new-folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 10v6M9 13h6"/>',
    "delete": '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/><path d="M9 7V4h6v3"/>',
    "rename": '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "upload": '<path d="M12 15V4"/><path d="M7 9l5-5 5 5"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    "download": '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "queue": '<path d="M8 6h12M8 12h12M8 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "dual": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/>',
    "single": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "check": '<path d="M5 12l5 5 9-10"/>',
    "alert": '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17h.01"/>',
    "retry": '<path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.5"/><path d="M4 4v4.5h4.5"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "clear": '<path d="M5 6h14M5 12h9M5 18h5"/><path d="M15 15l5 5M20 15l-5 5"/>',
    "transfer": '<path d="M4 8h14"/><path d="M14 4l4 4-4 4"/><path d="M20 16H6"/><path d="M10 12l-4 4 4 4"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3M14 9l2 2"/>',
    "terminal": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M12 15h5"/>',
    "computer": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "server": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8M8 11h8"/><path d="M12 17h.01"/>',
    "open": '<path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
    "save": '<path d="M5 4h11l3 3v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z"/><path d="M8 4v5h7V4M8 20v-6h8v6"/>',
    "language": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18"/>',
}

FILE_COLORS = {
    "folder": ACCENT,
    "image": "#22B573", "video": "#E0457B", "audio": "#F28C28", "archive": "#D9A400",
    "code": "#8B5CF6", "text": "#7C8796", "apk": "#3DDC84", "pdf": "#E5484D",
    "disk": "#5E7391", "doc": "#2F6FDB", "sheet": "#1E9E5A", "file": "#9AA4B2",
}

EXT = {}
for _k, _v in {
    "image": "png jpg jpeg gif bmp webp svg ico tif tiff heic avif",
    "video": "mp4 mkv avi mov webm m4v ts m2ts wmv flv mpg mpeg 3gp",
    "audio": "mp3 flac wav ogg opus m4a aac wma",
    "archive": "zip 7z rar tar gz tgz bz2 xz zst lz4 lzma cab deb rpm",
    "code": "py sh bash js ts c h cpp hpp java kt go rs rb php pl lua json xml yml yaml toml ini conf cfg html css sql",
    "text": "txt md log csv nfo rst",
    "apk": "apk apks xapk aab",
    "pdf": "pdf",
    "disk": "img iso bin raw qcow2 vmdk vdi ova dtb",
    "doc": "doc docx odt rtf",
    "sheet": "xls xlsx ods",
}.items():
    for _e in _v.split():
        EXT[_e] = _k


def file_kind(name: str) -> str:
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    return EXT.get(ext, "file")


def _folder_svg(color: str, link: bool) -> str:
    body = (f'<path d="M2.5 6.5a2 2 0 0 1 2-2h4.2l2 2h8.8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-15a2 2 0 0 1-2-2z" '
            f'fill="{color}" stroke="none" opacity="0.55"/>'
            f'<path d="M2.5 9.5h19v8a2 2 0 0 1-2 2h-15a2 2 0 0 1-2-2z" fill="{color}" stroke="none"/>')
    if link:
        body += _link_badge()
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'


def _file_svg(color: str, base: str, link: bool) -> str:
    body = (f'<path d="M14 2.8H7A2.2 2.2 0 0 0 4.8 5v14A2.2 2.2 0 0 0 7 21.2h10a2.2 2.2 0 0 0 2.2-2.2V8z" '
            f'fill="{base}" stroke="{color}" stroke-width="1.5" stroke-linejoin="round"/>'
            f'<path d="M14 2.8V8h5.2" fill="none" stroke="{color}" stroke-width="1.5" stroke-linejoin="round"/>')
    if color != FILE_COLORS["file"]:
        body += f'<rect x="7.3" y="13" width="9.4" height="4.6" rx="1.4" fill="{color}"/>'
    if link:
        body += _link_badge()
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'


def _link_badge() -> str:
    return ('<circle cx="6" cy="18" r="4.6" fill="#FFFFFF" stroke="#5E6B7D" stroke-width="1"/>'
            '<path d="M4.3 19.6l3.2-3.2M5.2 16.4h2.3v2.3" fill="none" stroke="#2B3440" stroke-width="1.3" '
            'stroke-linecap="round" stroke-linejoin="round"/>')


APP_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#3D7EFF"/><stop offset="1" stop-color="#7B4DFF"/></linearGradient></defs>'
    '<rect x="4" y="4" width="56" height="56" rx="15" fill="url(#g)"/>'
    '<g fill="none" stroke="#FFFFFF" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M17 25h27"/><path d="M37 17l8 8-8 8"/>'
    '<path d="M47 39H20"/><path d="M27 31l-8 8 8 8"/></g></svg>'
)

_cache: dict = {}
_text_color = "#2B3440"


def set_text_color(color: str):
    global _text_color
    if color != _text_color:
        _text_color = color
        _cache.clear()


def _render(svg: str, sizes=(16, 20, 24, 32, 48)) -> QIcon:
    r = QSvgRenderer(QByteArray(svg.encode()))
    icon = QIcon()
    for s in sizes:
        for dpr in (1, 2):
            pm = QPixmap(QSize(s * dpr, s * dpr))
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            r.render(p, QRectF(0, 0, s * dpr, s * dpr))
            p.end()
            pm.setDevicePixelRatio(dpr)
            icon.addPixmap(pm)
    return icon


def icon(name: str, color: str | None = None) -> QIcon:
    key = ("line", name, color or _text_color)
    if key not in _cache:
        _cache[key] = _render(_S.format(c=color or _text_color, body=LINE[name]))
    return _cache[key]


def file_icon(name: str, is_dir: bool, is_link: bool = False, dark: bool = False) -> QIcon:
    kind = "folder" if is_dir else file_kind(name)
    key = ("file", kind, is_link, dark)
    if key not in _cache:
        if is_dir:
            svg = _folder_svg(FILE_COLORS["folder"], is_link)
        else:
            svg = _file_svg(FILE_COLORS[kind], "#2A313B" if dark else "#FFFFFF", is_link)
        _cache[key] = _render(svg)
    return _cache[key]


def app_icon() -> QIcon:
    if "app" not in _cache:
        _cache["app"] = _render(APP_SVG, sizes=(16, 24, 32, 48, 64, 128, 256))
    return _cache["app"]
