"""Localization, ported from Localization.php."""
from __future__ import annotations

import json
import os
from typing import Optional

from .assets import LOCALE_DIR

_strings: dict[str, str] = {}
_locale = "en"


def available() -> list[str]:
    try:
        return [os.path.splitext(f)[0] for f in os.listdir(LOCALE_DIR) if f.endswith(".json")]
    except OSError:
        return ["en"]


def init(locale: Optional[str] = None):
    global _strings, _locale
    if not locale:
        import locale as _locale_mod
        try:
            lang = (_locale_mod.getlocale()[0] or "en").split("_")[0].lower()
        except Exception:
            lang = "en"
    else:
        lang = locale.split("_")[0].lower()
    if lang not in available():
        lang = "en"
    _locale = lang
    path = os.path.join(LOCALE_DIR, f"{lang}.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            _strings = json.load(fh)
    except Exception:
        _strings = {}


def current_locale() -> str:
    return _locale


def _(key: str) -> str:
    return _strings.get(key, f"FAILED TO LOAD {key}")
