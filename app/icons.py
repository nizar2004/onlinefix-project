"""Icon set for the launcher — the reference launcher's exact SVG artwork.

The PNGs in ``assets/img/icons`` are rasterised from the very same inline
SVG paths the reference GTK launcher ships, rendered in white so they can
be tinted at runtime (the reference uses a single stroke colour,
``#C8CFDD``).  ``icon()`` returns a Tk ``PhotoImage`` of a requested size
in a requested colour; ``logo()`` returns the violet-gradient gamepad
brand mark.
"""
from __future__ import annotations

import os

from PIL import Image, ImageTk

__all__ = ["icon", "logo", "ICON_NAMES", "available"]

ICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "img", "icons")

#: Every icon that ships with the app.
ICON_NAMES = (
    "back", "check", "clock", "close", "debug", "download", "edit", "env",
    "external", "folder", "forward", "gamepad", "home", "library", "logo",
    "maximize", "minimize", "monitor", "pencil", "play", "plus", "refresh",
    "reset", "save", "search", "settings", "steam", "stop", "trash",
)

DEFAULT_COLOR = "#C8CFDD"

# name -> (Image, is_tintable)
_raw_cache: dict[str, Image.Image] = {}
_photo_cache: dict[tuple, ImageTk.PhotoImage] = {}


def available() -> list[str]:
    return list(ICON_NAMES)


def _load_raw(name: str) -> Image.Image | None:
    """Load the 128px white master PNG for ``name`` (cached)."""
    if name in _raw_cache:
        return _raw_cache[name]
    path = os.path.join(ICON_DIR, f"{name}.png")
    try:
        img = Image.open(path).convert("RGBA")
    except Exception:
        _raw_cache[name] = None
        return None
    _raw_cache[name] = img
    return img


def _hex_to_rgba(color: str):
    color = color.strip()
    if color.startswith("#"):
        color = color[1:]
        if len(color) == 3:
            color = "".join(c * 2 for c in color)
        if len(color) == 6:
            return (int(color[0:2], 16), int(color[2:4], 16),
                    int(color[4:6], 16), 255)
        if len(color) == 8:
            return (int(color[0:2], 16), int(color[2:4], 16),
                    int(color[4:6], 16), int(color[6:8], 16))
    named = {"white": (255, 255, 255, 255), "black": (0, 0, 0, 255),
             "red": (255, 0, 0, 255), "transparent": (0, 0, 0, 0)}
    return named.get(color.lower(), (255, 255, 255, 255))


def _tinted(img: Image.Image, color: str) -> Image.Image:
    """Recolour a white master image while keeping its alpha channel."""
    rgba = _hex_to_rgba(color)
    out = Image.new("RGBA", img.size, rgba)
    out.putalpha(img.getchannel("A"))
    return out


def icon(name: str, size: int = 16, color: str | None = None):
    """Return a ``PhotoImage`` of the named icon.

    ``size``  — logical pixel size (scaled by the KDE display factor).
    ``color`` — tint colour (defaults to the system label colour).
    The brand ``logo`` keeps its own gradient and ignores the tint.
    """
    size = _scaled(size)
    if color is None:
        from . import theme
        color = getattr(theme, "STROKE", DEFAULT_COLOR)
    key = (name, size, str(color))
    if key in _photo_cache:
        return _photo_cache[key]

    raw = _load_raw(name)
    if raw is None and name != "gamepad":
        raw = _load_raw("gamepad")
    if raw is None:
        raw = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    if name != "logo":
        raw = _tinted(raw, color)

    img = raw.resize((size, size), Image.LANCZOS)
    photo = ImageTk.PhotoImage(img)
    _photo_cache[key] = photo
    return photo


def _scaled(size: int) -> int:
    """Logical icon size → device pixels."""
    try:
        from . import theme
        return max(1, int(round(size * theme.SCALE)))
    except Exception:
        return max(1, int(size))


def logo(size: int = 24):
    """The violet gradient gamepad brand mark (keeps its colours)."""
    size = _scaled(size)
    key = ("__logo__", size, "")
    if key in _photo_cache:
        return _photo_cache[key]
    raw = _load_raw("logo")
    if raw is None:
        raw = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    photo = ImageTk.PhotoImage(raw.resize((size, size), Image.LANCZOS))
    _photo_cache[key] = photo
    return photo
