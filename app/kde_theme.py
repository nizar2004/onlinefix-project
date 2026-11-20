"""KDE Plasma integration — colour scheme, accent colour and display scale.

A KDE application is expected to follow the user's colour scheme (dark or
light), the system accent colour and the display scale factor.  This
module reads those settings the same way Plasma applications do:

* ``~/.config/kdeglobals`` — ``[Colors:*]`` groups carry the resolved
  palette of the active colour scheme, ``[General] ColorScheme`` its
  name and ``[KDE] widgetStyle`` the widget style.
* the accent colour (Plasma 6: ``[General] AccentColorCustom`` or an
  ``AccentColor`` preset index).
* the display scale — ``Xft.dpi`` from the X resource database (96 dpi
  per 1.0×) or the ``scale`` reported by KWin for the outputs.

Nothing here is required: when the settings cannot be read the launcher
keeps its own reference palette at 1.0× scale.
"""
from __future__ import annotations

import configparser
import os
import re
from typing import Optional

CONF = os.path.expanduser("~/.config/kdeglobals")
KWIN_OUTPUTS = os.path.expanduser("~/.config/kwinoutputconfig.json")

#: Preset accent colours used by Plasma 6 (index → RGB), Breeze order.
PLASMA_ACCENTS = [
    "#3DAEE9",  # Breeze blue (default)
    "#ED7A47",
    "#D81B60",
    "#9B59B6",
    "#67BADD"[:7],
    "#1CDC9B"[:7],
    "#F67400",
    "#DA4453",
]


def _rgb(value: Optional[str]) -> Optional[str]:
    """``r,g,b`` → ``#rrggbb``."""
    if not value:
        return None
    parts = [p.strip() for p in value.split(",")]
    if len(parts) < 3:
        return None
    try:
        r, g, b = (max(0, min(255, int(float(p)))) for p in parts[:3])
    except ValueError:
        return None
    return f"#{r:02X}{g:02X}{b:02X}"


def _read_kdeglobals() -> dict[str, dict[str, str]]:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read(CONF, encoding="utf-8")
    except Exception:
        return {}
    out: dict[str, dict[str, str]] = {}
    for section in parser.sections():
        out[section] = dict(parser.items(section))
    return out


def _scale_from_xrdb() -> Optional[float]:
    try:
        import subprocess
        out = subprocess.run(["xrdb", "-query"], capture_output=True, text=True,
                             timeout=3).stdout
        for line in out.splitlines():
            if line.lower().startswith("xft.dpi"):
                dpi = float(line.split(":")[1].strip())
                if dpi > 10:
                    return dpi / 96.0
    except Exception:
        pass
    return None


def _scale_from_kwin() -> Optional[float]:
    try:
        import json
        with open(KWIN_OUTPUTS, encoding="utf-8") as fh:
            data = json.load(fh)

        def walk(node):
            if isinstance(node, dict):
                if "scale" in node and isinstance(node["scale"], (int, float)):
                    return float(node["scale"])
                for value in node.values():
                    found = walk(value)
                    if found:
                        return found
            elif isinstance(node, list):
                for value in node:
                    found = walk(value)
                    if found:
                        return found
            return None

        return walk(data)
    except Exception:
        return None


def read() -> dict:
    """Collect every KDE setting the launcher should honour."""
    ini = _read_kdeglobals()

    def color(group: str, key: str, sub: Optional[str] = None) -> Optional[str]:
        section = f"Colors:{group}" + (f"][{sub}" if sub else "")
        return _rgb(ini.get(section, {}).get(key))

    general = ini.get("General", {})
    kde = ini.get("KDE", {})

    scale = _scale_from_xrdb() or _scale_from_kwin() or 1.0
    scale = max(1.0, min(3.0, scale))

    # --- accent colour -----------------------------------------------------
    accent = _rgb(general.get("AccentColorCustom"))
    if accent is None:
        idx = general.get("AccentColor")
        if idx and idx.strip().isdigit():
            preset = PLASMA_ACCENTS[int(idx.strip()) % len(PLASMA_ACCENTS)]
            accent = preset

    palette = {
        # window chrome
        "window_bg":    color("Window", "BackgroundNormal") or color("View", "BackgroundNormal"),
        "window_fg":    color("Window", "ForegroundNormal"),
        # content views (slightly deeper than the window background)
        "view_bg":      color("View", "BackgroundNormal"),
        "view_alt":     color("View", "BackgroundAlternate"),
        # widgets: buttons, inputs
        "button_bg":    color("Button", "BackgroundNormal"),
        "button_fg":    color("Button", "ForegroundNormal"),
        "button_alt":   color("Button", "BackgroundAlternate"),
        # selection
        "select_bg":    color("Selection", "BackgroundNormal"),
        "select_fg":    color("Selection", "ForegroundNormal"),
        # states
        "focus":        color("Window", "DecorationFocus") or color("View", "DecorationFocus"),
        "hover":        color("Window", "DecorationHover") or color("View", "DecorationHover"),
        "negative":     color("Window", "ForegroundNegative"),
        "positive":     color("Window", "ForegroundPositive"),
        "neutral":      color("Window", "ForegroundNeutral"),
        "inactive":     color("Window", "ForegroundInactive"),
        "link":         color("Window", "ForegroundLink"),
        # header colours (used by KDE header bars)
        "header_bg":    color("Header", "BackgroundNormal"),
        "header_fg":    color("Header", "ForegroundNormal"),
    }

    return {
        "available": any(palette.values()),
        "scheme": general.get("ColorScheme", ""),
        "widget_style": kde.get("widgetStyle", ""),
        "font": general.get("font", ""),
        "scale": scale,
        "accent": accent,
        "palette": palette,
    }
