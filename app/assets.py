"""Asset loading helpers (images, icons, rounded corners, blurred backgrounds)."""
from __future__ import annotations

import os
from typing import Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from . import theme

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(BASE_DIR, "assets")
IMG = os.path.join(ASSETS, "img")
LOCALE_DIR = os.path.join(BASE_DIR, "locale")

_photo_cache: dict[tuple, ImageTk.PhotoImage] = {}


def asset(*parts: str) -> str:
    return os.path.join(ASSETS, *parts)


def image_path(name: str) -> str:
    return os.path.join(IMG, name)


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    scale = 4
    w, h = size[0] * scale, size[1] * scale
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius * scale, fill=255)
    return mask.resize(size, Image.LANCZOS)


def _resize(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return img.resize(size, Image.LANCZOS)


def photo(
    path: Optional[str],
    size: Optional[tuple[int, int]] = None,
    radius: int = 0,
    blur: int = 0,
    brightness: float = 1.0,
    fallback: str = "noImage.png",
    stretch: bool = True,
) -> ImageTk.PhotoImage:
    """Load a file (or a bundled fallback) as a PhotoImage.

    Results are cached; PhotoImage objects must be kept alive by the caller or
    by this module, which the cache takes care of.
    """
    if not path or not os.path.isfile(path):
        path = image_path(fallback)
    key = (path, size, radius, blur, round(brightness, 2), stretch)
    if key in _photo_cache:
        return _photo_cache[key]

    try:
        img = Image.open(path).convert("RGBA")
    except Exception:
        img = Image.open(image_path("noImage.png")).convert("RGBA")

    if size:
        if stretch:
            img = _resize(img, size)
        else:
            img.thumbnail(size, Image.LANCZOS)
            canvas = Image.new("RGBA", size, (0, 0, 0, 0))
            canvas.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2), img)
            img = canvas

    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)

    if radius and size:
        img.putalpha(_rounded_mask(size, radius))

    out = ImageTk.PhotoImage(img)
    _photo_cache[key] = out
    return out


def background_photo(path: Optional[str], size: tuple[int, int]) -> ImageTk.PhotoImage:
    """Blurred and dimmed banner used behind the game grid."""
    return photo(path, size=size, blur=28, brightness=0.38, fallback="noBanner.png")


def cover_photo(
    path: Optional[str],
    size: tuple[int, int],
    radius: int = 0,
    fallback: str = "noBanner.png",
) -> ImageTk.PhotoImage:
    """Load an image cropped to exactly fill ``size`` (like CSS/GTK COVER).

    The source is center-cropped to the target aspect ratio, then scaled —
    portrait game covers stay edge-to-edge with no distortion. A dark
    placeholder with nothing on it is used when the file is missing; draw
    your own icon on top of it.
    """
    if not path or not os.path.isfile(path):
        path = image_path(fallback)
    key = ("cover", path, size, radius)
    if key in _photo_cache:
        return _photo_cache[key]

    try:
        img = Image.open(path).convert("RGB")
    except Exception:
        img = Image.open(image_path("noImage.png")).convert("RGB")

    tw, th = size
    sw, sh = img.size
    target_ratio = tw / th
    src_ratio = sw / sh
    if src_ratio > target_ratio:
        new_w = int(sh * target_ratio)
        x0 = (sw - new_w) // 2
        img = img.crop((x0, 0, x0 + new_w, sh))
    else:
        new_h = int(sw / target_ratio)
        y0 = (sh - new_h) // 2
        img = img.crop((0, y0, sw, y0 + new_h))
    img = img.resize((tw, th), Image.LANCZOS).convert("RGBA")

    if radius:
        img.putalpha(_rounded_mask(size, radius))

    out = ImageTk.PhotoImage(img)
    _photo_cache[key] = out
    return out


def ico_photo(path: Optional[str], size: int = 34) -> ImageTk.PhotoImage:
    return photo(path, size=(size, size), fallback="noImage.png")
