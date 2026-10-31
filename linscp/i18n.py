"""Tiny i18n: source strings are French; EN holds the English translations."""
from __future__ import annotations

import locale
import os

from .config import settings
from .i18n_en import EN

_lang = None


def lang() -> str:
    global _lang
    if _lang is None:
        _lang = settings.get("language") or ""
        if not _lang:
            loc = os.environ.get("LANGUAGE") or os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") \
                or os.environ.get("LANG") or (locale.getlocale()[0] or "")
            _lang = "fr" if loc.lower().startswith("fr") else "en"
    return _lang


def tr(_text: str, **kw) -> str:
    out = EN.get(_text, _text) if lang() == "en" else _text
    return out.format(**kw) if kw else out
