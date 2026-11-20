"""Reusable Tk widgets for the launcher — mirrors the reference UI.

The reference is a GTK4 / libadwaita application; this module recreates
its widget vocabulary in Tkinter with the same metrics, colours and
behaviour: 46px header bars, 34px buttons, boxed-list preference rows,
nav rows, switches, toasts.

``RoundedButton`` is intentionally API-compatible with previous
implementations: ``RoundedButton(parent, text=..., command=..., bg=...,
hover=..., fg=..., font=..., width=..., height=...)`` keeps working.
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Callable, Optional

from . import theme as T

__all__ = [
    "RoundedButton", "IconButton", "HeaderBar", "WindowControls",
    "NavRow", "SearchEntry", "StyledEntry", "Card", "Divider",
    "FieldLabel", "SectionTitle", "Badge", "Pill", "Spacer", "RoundedBox",
    "ScrollFrame", "StubCard", "ToggleRow", "Switch", "ActionRow",
    "EntryRow", "ComboRow", "SwitchRow", "PreferencesGroup", "StatusPage",
    "round_rect", "toast", "make_draggable",
]


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------
def _parent_bg(widget) -> str:
    """Best-effort resolution of a widget's background colour."""
    try:
        return widget.cget("bg")
    except Exception:
        return T.BG


def _rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    """Draw a smooth rounded rectangle on a canvas and return its item id."""
    r = max(0.01, r)
    points = [
        x1 + r, y1,
        x1 + r, y1,
        x2 - r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def round_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
    """Compatibility wrapper for the legacy canvas rounded-rectangle helper."""
    return _rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs)


def _over(hex_bg: str, alpha: float) -> str:
    """Composite white at ``alpha`` over ``hex_bg``."""
    r = int(hex_bg[1:3], 16)
    g = int(hex_bg[3:5], 16)
    b = int(hex_bg[5:7], 16)
    mix = lambda v: int(v + (255 - v) * alpha)
    return f"#{mix(r):02X}{mix(g):02X}{mix(b):02X}"


def make_draggable(widget, window: Optional[tk.Wm] = None):
    """Make a widget (and its children) drag the top-level window.

    Tk delivers events to the innermost widget, so every descendant gets
    the binding too — that is what makes a whole header bar draggable.
    """
    win = window or widget.winfo_toplevel()
    state = {"x": 0, "y": 0}

    def press(event):
        state["x"] = event.x_root - win.winfo_x()
        state["y"] = event.y_root - win.winfo_y()

    def move(event):
        try:
            win.geometry(f"+{event.x_root - state['x']}+{event.y_root - state['y']}")
        except Exception:
            pass

    def bind_tree(w):
        w.bind("<Button-1>", press, add="+")
        w.bind("<B1-Motion>", move, add="+")
        for child in w.winfo_children():
            bind_tree(child)

    bind_tree(widget)


# ---------------------------------------------------------------------------
# RoundedButton — Adwaita-style flat rounded button
# ---------------------------------------------------------------------------
class RoundedButton(tk.Canvas):
    """A flat, rounded, hover-aware button.

    Variants
    --------
    ``variant="normal"``      — dark #38383B surface (the quiet action).
    ``variant="suggested"``   — slate suggested action (Play, Add Game).
    ``variant="destructive"`` — red text on a dark red fill.
    ``variant="flat"``        — transparent, text-only (menu items).
    ``variant="light"``       — light button with dark text (Save, Next).

    Explicit ``bg`` / ``hover`` / ``fg`` still win over the variant.
    """

    _IGNORED = (
        "activebackground", "activeforeground", "relief", "bd",
        "borderwidth", "highlightbackground", "highlightcolor",
        "highlightthickness", "takefocus", "overrelief",
        "default", "underline", "wraplength", "justify", "anchor",
        "tooltip",
    )

    def __init__(self, master, text: str = "", command: Optional[Callable] = None,
                 bg: Optional[str] = None, hover: Optional[str] = None,
                 fg: Optional[str] = None, font=None,
                 width: Optional[int] = None, height: Optional[int] = None,
                 radius: Optional[int] = None,
                 variant: str = "normal",
                 padx: int = 12, pady: int = 6,
                 **kwargs):

        image = kwargs.pop("image", None)
        compound = kwargs.pop("compound", "none")
        icon_color = kwargs.pop("icon_color", None)
        pad_left = kwargs.pop("pad_left", 0)

        for key in self._IGNORED:
            kwargs.pop(key, None)

        state = kwargs.pop("state", "normal")
        self._enabled = state != "disabled"

        # --- resolve colours from the variant -------------------------------
        if variant == "suggested":
            bg = bg or T.PRIMARY
            hover = hover or T.PRIMARY_HOVER
            fg = fg or "#FFFFFF"
            icon_color = icon_color or "#FFFFFF"
        elif variant == "destructive":
            bg = bg or T.DANGER_BG
            hover = hover or T._mix(T.DANGER_BG, T.DANGER, 0.25)
            fg = fg or T.DANGER
            icon_color = icon_color or T.STROKE
        elif variant == "light":
            bg = bg or T.LIGHT
            hover = hover or T.LIGHT_HOVER
            fg = fg or T.LIGHT_FG
            icon_color = icon_color or T.LIGHT_FG
        elif variant == "flat":
            bg = bg or _parent_bg(master)
            hover = hover or _over(_parent_bg(master), 0.06)
            fg = fg or T.STROKE
            icon_color = icon_color or T.STROKE
        else:  # normal — quiet dark surface
            bg = bg or T.BUTTON
            hover = hover or T.BUTTON_HOVER
            fg = fg or "#FFFFFF"
            icon_color = icon_color or T.STROKE

        if not self._enabled:
            bg = T.SURFACE_2
            hover = T.SURFACE_2
            fg = T.DIM

        self._bg = bg
        self._hover = hover
        self._fg = fg
        self._icon_color = icon_color
        self._font = font or T.FONT_BUTTON
        self._command = command
        self._radius = T.px(radius) if radius is not None else T.px(8)

        # --- size -----------------------------------------------------------
        try:
            measure = tkfont.Font(root=master, font=self._font)
            text_w = measure.measure(text or " ")
            text_h = measure.metrics("linespace")
        except Exception:
            text_w, text_h = 8 * max(1, len(text or "")), 14

        img_space = 0
        if image is not None:
            try:
                img_space = image.width() + 7
            except Exception:
                img_space = 20

        graphic_only = image is not None and (compound == "graphic_only" or not text)
        padx, pady = T.px(padx), T.px(pady)
        if graphic_only:
            w = T.px(width) if width and width > 10 else (img_space + 12)
            h = T.px(height) if height and height > 10 else (img_space + 10)
        else:
            if width and width > 40:
                w = T.px(width)
            else:
                w = max(T.px(56), text_w + padx * 2 + (img_space if compound in ("left", "right") else 0))
            h = T.px(height) if height and height > 20 else max(T.BUTTON_H, text_h + pady * 2)

        super().__init__(master, width=w, height=h,
                         bg=_parent_bg(master),
                         highlightthickness=0, bd=0,
                         cursor="hand2" if self._enabled else "arrow",
                         **kwargs)

        self._shape = _rounded_rect(self, 1, 1, w - 1, h - 1,
                                    self._radius, fill=self._bg,
                                    outline=self._outline if hasattr(self, "_outline") else "")
        self._label = self.create_text(
            w // 2, h // 2, text=text, fill=self._fg, font=self._font,
        )
        self._label_x = w // 2

        if image is not None:
            if graphic_only:
                self.create_image(w // 2, h // 2, image=image, anchor="center")
            elif compound == "left":
                text_x = w // 2 + img_space // 2 + pad_left
                image_x = text_x - text_w - img_space // 2 + pad_left
                self.coords(self._label, text_x, h // 2)
                self.create_image(image_x, h // 2, image=image, anchor="center")
            elif compound == "top":
                self.coords(self._label, w // 2, h // 2 + (image.height() // 2 if image else 10))
                self.create_image(w // 2, h // 2 - text_h // 2 - 4,
                                  image=image, anchor="center")

        if self._enabled:
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<Button-1>", self._on_press)
            self.bind("<ButtonRelease-1>", self._on_release)

    # -- events -------------------------------------------------------------
    def _on_enter(self, _e=None):
        self.itemconfigure(self._shape, fill=self._hover)

    def _on_leave(self, _e=None):
        self.itemconfigure(self._shape, fill=self._bg)

    def _on_press(self, _e=None):
        self.itemconfigure(self._shape, fill=self._hover)
        return "break"

    def _on_release(self, _e=None):
        self.itemconfigure(self._shape, fill=self._hover)
        if callable(self._command):
            self._command()

    # -- public API ---------------------------------------------------------
    def set_text(self, text: str):
        self.itemconfigure(self._label, text=text)

    def set_command(self, command: Optional[Callable]):
        self._command = command

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)
        if not self._enabled:
            self.itemconfigure(self._shape, fill=T.SURFACE_2)
            self.itemconfigure(self._label, fill=T.DIM)
            self.configure(cursor="arrow")
            self.unbind("<Enter>")
            self.unbind("<Leave>")
            self.unbind("<Button-1>")
            self.unbind("<ButtonRelease-1>")
        else:
            self.itemconfigure(self._shape, fill=self._bg)
            self.itemconfigure(self._label, fill=self._fg)
            self.configure(cursor="hand2")
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<Button-1>", self._on_press)
            self.bind("<ButtonRelease-1>", self._on_release)

    def set_active(self, active: bool):
        """Segmented/chip state: an active button uses the accent tint."""
        if active:
            self.itemconfigure(self._shape, fill=T.SIDEBAR_ACTIVE)
            self.itemconfigure(self._label, fill=T.FG)
        else:
            self.itemconfigure(self._shape, fill=self._bg)
            self.itemconfigure(self._label, fill=self._fg)

    def set_image(self, image):
        for item in self.find_all():
            if self.type(item) == "image":
                self.delete(item)
        if image is not None:
            self.create_image(self.winfo_width() // 2, self.winfo_height() // 2,
                              image=image, anchor="center")


class IconButton(RoundedButton):
    """A square icon-only button (header bars, window controls)."""

    def __init__(self, master, image=None, size: int = 34, command=None,
                 variant: str = "flat", radius: Optional[int] = None, **kwargs):
        kwargs.pop("text", None)
        kwargs.setdefault("height", size)
        kwargs.setdefault("width", size)
        if radius is not None:
            kwargs.setdefault("radius", radius)
        super().__init__(master, text="", command=command, image=image,
                         compound="graphic_only", variant=variant, **kwargs)


# ---------------------------------------------------------------------------
# WindowControls — the round minimize / maximize / close buttons
# ---------------------------------------------------------------------------
class WindowControls(tk.Frame):
    """The three window buttons drawn by the reference header bar."""

    def __init__(self, master, bg: str, on_minimize=None, on_maximize=None,
                 on_close=None):
        super().__init__(master, bg=bg)
        self._bg = bg
        from . import icons

        def _btn(icon_name, glyph, command):
            img = icons.icon(icon_name, 16, color=T.STROKE) if icon_name else None
            if img is None:
                img = self._glyph_photo(glyph)
            b = IconButton(self, image=img, size=34, radius=17,
                           command=command, variant="normal")
            b.pack(side="left", padx=T.px(1))
            return b

        self.min_btn = _btn("minimize", "▾", on_minimize)
        self.max_btn = _btn("maximize", "▴", on_maximize)
        self.close_btn = _btn("close", "✕", on_close)
        # Breeze behaviour: the close button turns red on hover
        if self.close_btn._enabled:
            self.close_btn.unbind("<Enter>")
            self.close_btn.bind("<Enter>", lambda _e: self._close_hover(True))
            self.close_btn.bind("<Leave>", lambda _e: self._close_hover(False))

    def _close_hover(self, hovered: bool):
        from . import icons
        btn = self.close_btn
        if btn is None or not btn.winfo_exists():
            return
        if hovered:
            btn.itemconfigure(btn._shape, fill=T.DANGER)
            img = icons.icon("close", 16, color="#FFFFFF")
            btn.delete("image")
            for item in btn.find_all():
                if btn.type(item) == "image":
                    btn.delete(item)
            btn.create_image(btn.winfo_width() // 2, btn.winfo_height() // 2,
                             image=img, anchor="center")
            btn._close_img = img
        else:
            btn.itemconfigure(btn._shape, fill=btn._bg)
            img = icons.icon("close", 16, color=T.STROKE)
            for item in btn.find_all():
                if btn.type(item) == "image":
                    btn.delete(item)
            btn.create_image(btn.winfo_width() // 2, btn.winfo_height() // 2,
                             image=img, anchor="center")
            btn._close_img = img

    @staticmethod
    def _glyph_photo(glyph: str):
        from PIL import Image, ImageDraw, ImageTk
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.line((10, 13, 16, 19, 22, 13), fill=(200, 207, 221, 255), width=2, joint="curve")
        return ImageTk.PhotoImage(img)


# ---------------------------------------------------------------------------
# HeaderBar — the 46px Adwaita header strip
# ---------------------------------------------------------------------------
class HeaderBar(tk.Frame):
    """A 46px header bar: start widgets | title widget | end widgets."""

    def __init__(self, master, bg: Optional[str] = None, height: Optional[int] = None,
                 draggable: bool = False, **kwargs):
        bg = bg or T.WINDOW
        super().__init__(master, bg=bg, height=height or T.HEADER_H,
                         highlightthickness=0, bd=0, **kwargs)
        self.pack_propagate(False)
        self._bg = bg
        self.title_widget: Optional[tk.Widget] = None

        self.start_box = tk.Frame(self, bg=bg)
        self.start_box.pack(side="left", padx=(T.px(6), 0))
        self.end_box = tk.Frame(self, bg=bg)
        self.end_box.pack(side="right", padx=(0, T.px(6)))
        self.center_box = tk.Frame(self, bg=bg)
        self.center_box.pack(side="left", fill="both", expand=True)

        if draggable:
            for widget in (self, self.center_box):
                make_draggable(widget)

    def pack_start(self, widget, **kwargs):
        kwargs.setdefault("side", "left")
        kwargs.setdefault("padx", (4, 0))
        kwargs.setdefault("pady", 6)
        widget.pack(in_=self.start_box, **kwargs)

    def pack_end(self, widget, **kwargs):
        kwargs.setdefault("side", "right")
        kwargs.setdefault("padx", (0, 4))
        kwargs.setdefault("pady", 6)
        widget.pack(in_=self.end_box, **kwargs)

    def set_title_widget(self, widget):
        if self.title_widget is not None:
            self.title_widget.pack_forget()
        self.title_widget = widget
        if widget is not None:
            widget.pack(in_=self.center_box, fill="both", expand=True,
                        padx=T.px(8), pady=T.px(6))

    def set_title(self, text: str, font=None, fg=None):
        self.set_title_widget(None)
        lbl = tk.Label(self.center_box, text=text, bg=self._bg,
                       fg=fg or T.FG, font=font or T.FONT_SUBTITLE)
        lbl.place(relx=0.5, rely=0.5, anchor="center")
        self.title_widget = lbl
        return lbl


# ---------------------------------------------------------------------------
# SearchEntry — the pill search field of the reference header
# ---------------------------------------------------------------------------
class SearchEntry(tk.Frame):
    """A rounded search field with an embedded entry (Adw.SearchEntry)."""

    def __init__(self, master, placeholder: str = "Search your library…",
                 bg: Optional[str] = None, command: Optional[Callable] = None,
                 **kwargs):
        bg = bg or T.FIELD
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self._bg = bg
        self._command = command
        from . import icons
        self.icon_label = tk.Label(self, image=icons.icon("search", 15), bg=bg)
        self.icon_label.pack(side="left", padx=(T.px(12), T.px(2)))
        self.entry = StyledEntry(self, placeholder=placeholder, bg=bg,
                                 fg=T.FG, font=T.FONT_BODY,
                                 highlightthickness=0, insertbackground=T.FG,
                                 relief="flat", bd=0)
        self.entry.pack(side="left", fill="both", expand=True, padx=(0, T.px(4)),
                        pady=T.px(8))
        # clear ("✕") button — visible only while the field has text
        self.clear_label = tk.Label(self, text="✕", bg=bg, fg=T.MUTED,
                                    font=T.FONT_SM, cursor="hand2",
                                    padx=T.px(6))
        self.clear_label.bind("<Button-1>", self._clear)
        self.clear_label.bind("<Enter>",
                              lambda _e: self.clear_label.configure(fg=T.FG))
        self.clear_label.bind("<Leave>",
                              lambda _e: self.clear_label.configure(fg=T.MUTED))
        if command is not None:
            self.entry.bind("<KeyRelease>", lambda _e: command())
        self.entry.bind("<KeyRelease>", lambda _e: self._update_clear(), add="+")
        self.entry.bind("<FocusOut>", lambda _e: self.after(80, self._update_clear), add="+")
        self.bind("<Configure>", self._on_resize, add="+")

    def _clear(self, _e=None):
        self.set("")
        self._update_clear()
        if callable(self._command):
            self._command()
        self.entry.focus_set()

    def _update_clear(self):
        has_text = bool(self.entry.get()) and not getattr(
            self.entry, "_placeholder_active", False)
        if has_text:
            self.clear_label.pack(side="right", padx=(0, T.px(10)))
        else:
            self.clear_label.pack_forget()

    def _on_resize(self, _e=None):
        pass

    def get(self) -> str:
        return self.entry.get()

    def set(self, value: str):
        self.entry.set(value)

    def focus(self):
        self.entry.focus_set()


# ---------------------------------------------------------------------------
# NavRow — sidebar navigation row (Adw.ActionRow in .navigation-sidebar)
# ---------------------------------------------------------------------------
class NavRow(tk.Frame):
    def __init__(self, master, title: str, icon_name: str,
                 command: Optional[Callable] = None, selected: bool = False,
                 bg: Optional[str] = None, **kwargs):
        bg = bg or T.SIDEBAR
        super().__init__(master, bg=bg, height=T.NAV_ROW_H, cursor="hand2",
                         highlightthickness=0, bd=0, **kwargs)
        self.pack_propagate(False)
        self._bg = bg
        self._title = title
        self._icon_name = icon_name
        self._command = command
        self._selected = False
        self._hover = False
        self._icons = {}

        from . import icons
        self.icon_label = tk.Label(self, bg=bg, cursor="hand2")
        self.icon_label.pack(side="left", padx=(T.px(12), T.px(10)))
        self.title_label = tk.Label(self, text=title, bg=bg,
                                    fg=T.STROKE, font=T.FONT_BODY,
                                    anchor="w", cursor="hand2")
        self.title_label.pack(side="left", fill="x", expand=True)
        self.badge_label = tk.Label(self, text="", bg=bg, fg=T.MUTED,
                                    font=T.FONT_SM, anchor="e")
        self.badge_label.pack(side="right", padx=(0, T.px(14)))
        for widget in (self, self.icon_label, self.title_label):
            widget.bind("<Button-1>", self._click)
        for widget in (self, self.icon_label, self.title_label, self.badge_label):
            widget.bind("<Enter>", self._on_enter, add="+")
            widget.bind("<Leave>", self._on_leave, add="+")
        self.set_selected(selected)

    def _click(self, _e=None):
        if callable(self._command):
            self._command()

    def _on_enter(self, _e=None):
        self._hover = True
        self._paint()

    def _on_leave(self, _e=None):
        self._hover = False
        self._paint()

    def set_badge(self, text: str):
        """A quiet right-aligned counter (e.g. the number of games)."""
        self.badge_label.configure(text=text or "")

    def _paint(self):
        if self._selected:
            bg, fg = T.SIDEBAR_ACTIVE, T.FG
        elif self._hover:
            bg, fg = _over(self._bg, 0.05), T.FG_SOFT
        else:
            bg, fg = self._bg, T.MUTED
        for widget in (self, self.icon_label, self.title_label,
                       self.badge_label):
            try:
                widget.configure(bg=bg)
            except Exception:
                pass
        self.title_label.configure(fg=fg)
        self.badge_label.configure(fg=T.MUTED)

    def set_selected(self, selected: bool):
        self._selected = bool(selected)
        self._paint()
        from . import icons
        try:
            img = icons.icon(self._icon_name, 18, color=T.STROKE)
            self.icon_label.configure(image=img)
            self.icon_label.image = img
        except Exception:
            pass


# ---------------------------------------------------------------------------
# StyledEntry — dark field entry with a violet focus ring
# ---------------------------------------------------------------------------
class StyledEntry(tk.Entry):
    """A dark field entry with a violet focus ring and placeholder text."""

    def __init__(self, master, placeholder: str = "", **kwargs):
        kwargs.setdefault("bg", T.INPUT_BG)
        kwargs.setdefault("fg", T.FG)
        kwargs.setdefault("insertbackground", T.FG)
        kwargs.setdefault("font", T.FONT_BODY)
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("relief", "flat")
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("highlightbackground", T.BG)
        kwargs.setdefault("highlightcolor", T.ACCENT)
        super().__init__(master, **kwargs)

        self._placeholder = placeholder
        self._placeholder_active = False
        if placeholder:
            self._show_placeholder()
            self.bind("<FocusIn>", self._on_focus_in, add="+")
            self.bind("<FocusOut>", self._on_focus_out, add="+")

    def _show_placeholder(self):
        if tk.Entry.get(self):
            return
        self._placeholder_active = True
        tk.Entry.insert(self, 0, self._placeholder)
        self.configure(fg=T.DIM)

    def _on_focus_in(self, _e=None):
        if self._placeholder_active:
            self._placeholder_active = False
            tk.Entry.delete(self, 0, "end")
            self.configure(fg=T.FG)

    def _on_focus_out(self, _e=None):
        if not tk.Entry.get(self):
            self._show_placeholder()

    def get(self) -> str:
        if self._placeholder_active:
            return ""
        return tk.Entry.get(self)

    def set(self, value: str) -> None:
        if self._placeholder_active:
            self._placeholder_active = False
            tk.Entry.delete(self, 0, "end")
            self.configure(fg=T.FG)
        tk.Entry.delete(self, 0, "end")
        if value:
            tk.Entry.insert(self, 0, value)
        elif self._placeholder:
            self._on_focus_out()


# ---------------------------------------------------------------------------
# Card / Divider / labels / misc
# ---------------------------------------------------------------------------
class Card(tk.Frame):
    """A raised dark panel (boxed list). Add children to ``card.body``."""

    def __init__(self, master, padx: int = 0, pady: int = 0, bg=None, **kwargs):
        bg = bg or T.SURFACE
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self.body = tk.Frame(self, bg=bg)
        self.body.pack(fill="both", expand=True, padx=padx, pady=pady)


class Divider(tk.Frame):
    """A 1px hairline rule."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("bg", T.BG)
        kwargs.setdefault("height", 1)
        super().__init__(master, **kwargs)


class FieldLabel(tk.Label):
    """A muted, left-aligned label for form fields."""

    def __init__(self, master, text: str = "", **kwargs):
        kwargs.setdefault("bg", _parent_bg(master))
        kwargs.setdefault("fg", T.MUTED)
        kwargs.setdefault("font", T.FONT_SM)
        kwargs.setdefault("anchor", "w")
        super().__init__(master, text=text, **kwargs)


class SectionTitle(tk.Label):
    """A bold section heading."""

    def __init__(self, master, text: str = "", **kwargs):
        kwargs.setdefault("bg", _parent_bg(master))
        kwargs.setdefault("fg", T.FG)
        kwargs.setdefault("font", T.FONT_SECTION)
        kwargs.setdefault("anchor", "w")
        super().__init__(master, text=text, **kwargs)


class Pill(tk.Label):
    """A small rounded status label (Adwaita .pill)."""

    @staticmethod
    def _tones():
        return {
            "accent":  (T.ACCENT_DIM, T.ACCENT_SOFT),
            "muted":   (T.SURFACE_2, T.FG_SOFT),
            "success": (T.SUCCESS_BG, T.SUCCESS),
            "warning": (T.WARNING_BG, T.WARNING),
            "danger":  (T.DANGER_BG, T.DANGER),
        }

    def __init__(self, master, text: str = "", tone: str = "accent", **kwargs):
        tones = self._tones()
        bg, fg = tones.get(tone, tones["accent"])
        kwargs.setdefault("bg", bg)
        kwargs.setdefault("fg", fg)
        kwargs.setdefault("font", T.FONT_PILL)
        kwargs.setdefault("padx", T.px(10))
        kwargs.setdefault("pady", T.px(3))
        super().__init__(master, text=text, **kwargs)


class Badge(Pill):
    """Legacy alias of :class:`Pill`."""


class Spacer(tk.Frame):
    """An empty frame with a fixed height/width — used for breathing room."""

    def __init__(self, master, height: int = T.SP_SM, width: int = 0, **kwargs):
        kwargs.setdefault("bg", _parent_bg(master))
        super().__init__(master, height=height, width=width, **kwargs)


class RoundedBox(tk.Frame):
    """A fixed-size dark surface with an inner frame for controls."""

    def __init__(self, master, width=None, height=None, radius=10, bg=None, **kwargs):
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        super().__init__(master, bg=bg or T.PANEL, width=width, height=height, **kwargs)
        self.pack_propagate(False)
        self.inner = tk.Frame(self, bg=bg or T.PANEL)
        self.inner.pack(fill="both", expand=True)


class ScrollFrame(tk.Frame):
    """A vertical scrollable frame: themed scrollbar + mouse-wheel support."""

    def __init__(self, master, bg=None, **kwargs):
        super().__init__(master, bg=bg or T.BG, **kwargs)
        self.canvas = tk.Canvas(self, bg=bg or T.BG, highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical",
                                       command=self.canvas.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.inner = tk.Frame(self.canvas, bg=bg or T.BG)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.bind("<Enter>", self._bind_wheel)
        self.bind("<Leave>", self._unbind_wheel)

    # X11 delivers wheel turns as Button-4/5; Windows/macOS as MouseWheel.
    def _bind_wheel(self, _e=None):
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.bind_all("<Button-4>", self._on_wheel, add="+")
        self.bind_all("<Button-5>", self._on_wheel, add="+")

    def _unbind_wheel(self, _e=None):
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")

    def _on_wheel(self, event):
        try:
            step = T.px(60)
            if getattr(event, "num", None) == 4:
                self.canvas.yview_scroll(-step, "pixels")
            elif getattr(event, "num", None) == 5:
                self.canvas.yview_scroll(step, "pixels")
            else:
                delta = getattr(event, "delta", 0) or 0
                if delta:
                    self.canvas.yview_scroll(int(-delta / 120) * step,
                                             "pixels")
        except (tk.TclError, ValueError, TypeError):
            pass

    def _on_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)


class StubCard(tk.Frame):
    """Skeleton loading tile shown while a game is being added."""

    WIDTH = 162
    HEIGHT = 261

    def __init__(self, master, name="", status="", **kwargs):
        width, height = T.px(self.WIDTH), T.px(self.HEIGHT)
        super().__init__(master, bg=T.CARD, width=width, height=height,
                         highlightthickness=0, bd=0, **kwargs)
        self.pack_propagate(False)
        inner = tk.Frame(self, bg=T.CARD)
        inner.pack(fill="both", expand=True, padx=6, pady=6)
        cover = tk.Frame(inner, bg=T.COVER_PLACEHOLDER)
        cover.pack(fill="both", expand=True)
        tk.Label(cover, text="···", bg=T.COVER_PLACEHOLDER, fg=T.DIM,
                 font=T.FONT_HERO).place(relx=0.5, rely=0.5, anchor="center")
        self._name_lbl = tk.Label(self, text=name or "Game", bg=T.CARD,
                                  fg=T.FG, font=T.FONT_CAPTION)
        self._name_lbl.pack(fill="x", padx=6, pady=(5, 3))
        self._status_lbl = tk.Label(self, text=status, bg=T.CARD, fg=T.MUTED,
                                    font=T.FONT_TINY, wraplength=T.px(146))
        self._status_lbl.pack(fill="x", padx=6, pady=(0, 4))


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------
class Switch(tk.Canvas):
    """A standalone modern switch (Adw.SwitchRow knob)."""

    TRACK_W = 46
    TRACK_H = 26

    def __init__(self, master, command=None, variable=None,
                 selected=False, bg=None, **kwargs):
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        self._bg = bg if bg is not None else _parent_bg(master)
        kwargs.setdefault("bg", self._bg)
        self._track_w, self._track_h = T.px(self.TRACK_W), T.px(self.TRACK_H)
        super().__init__(master, width=self._track_w, height=self._track_h,
                         cursor="hand2", **kwargs)
        self._command = command
        self._enabled = True
        self.variable = variable or tk.BooleanVar(master=self, value=selected)
        self.check = self
        self._redraw()
        self.bind("<Button-1>", lambda _e: self._flip())

    def _redraw(self):
        self.delete("all")
        on = bool(self.variable.get())
        if not self._enabled:
            track, knob = T.SURFACE_2, T.DIM
        elif on:
            track, knob = T.PRIMARY, "#FFFFFF"
        else:
            track, knob = T.SIDEBAR_ACTIVE, "#C9CDD3"
        w, h = self._track_w, self._track_h
        _rounded_rect(self, 1, 1, w - 1, h - 1, h // 2, fill=track, outline=track)
        knob_x = w - h // 2 - 3 if on else h // 2 + 3
        knob_r = h // 2 - 3
        cy = h // 2
        self.create_oval(knob_x - knob_r, cy - knob_r, knob_x + knob_r,
                         cy + knob_r, fill=knob, outline="")

    def _flip(self):
        if not self._enabled:
            return
        self.variable.set(not self.variable.get())
        self._redraw()
        if callable(self._command):
            self._command(self.get_selected())

    def get_selected(self):
        return bool(self.variable.get())

    def set_selected(self, selected):
        self.variable.set(bool(selected))
        self._redraw()

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if self._enabled else "arrow")
        self._redraw()


class ToggleRow(tk.Frame):
    """A settings row with a modern switch (label + switch)."""

    def __init__(self, master, text="", command=None, variable=None,
                 selected=False, bg=None, height=None, pad=14, **kwargs):
        super().__init__(master, bg=bg or T.SURFACE, **kwargs)
        bg = bg or T.SURFACE
        self._command = command
        self._enabled = True
        self.selected = bool(selected)
        self.variable = variable or tk.BooleanVar(master=self, value=selected)

        self._bg = bg
        self._label = tk.Label(self, text=text, bg=bg, fg=T.FG,
                               font=T.FONT_BODY, anchor="w", cursor="hand2")
        self._label.pack(side="left", fill="x", expand=True, padx=(T.px(pad), T.px(pad)))

        self._switch = Switch(self, command=command, variable=self.variable,
                              selected=selected, bg=bg)
        self._switch.pack(side="right", padx=(0, T.px(pad)))
        self.check = self._switch

        for widget in (self, self._label):
            widget.bind("<Button-1>", lambda _e: self._switch._flip())

    def _changed(self):
        if callable(self._command):
            self._command(self.get_selected())

    def get_selected(self):
        return bool(self.variable.get())

    def set_selected(self, selected):
        self.variable.set(bool(selected))
        self.selected = bool(selected)
        self._switch._redraw()

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self._switch.set_enabled(enabled)
        self._label.configure(fg=T.FG if self._enabled else T.DIM)


# ---------------------------------------------------------------------------
# Boxed-list rows (Adw.ActionRow / EntryRow / ComboRow / SwitchRow)
# ---------------------------------------------------------------------------
class ActionRow(tk.Frame):
    """A boxed-list row: title (+subtitle) on the left, actions on the right."""

    def __init__(self, master, title: str = "", subtitle: str = "",
                 command: Optional[Callable] = None, bg=None, **kwargs):
        bg = bg or T.SURFACE
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self._bg = bg
        self._box = tk.Frame(self, bg=bg)
        self._box.pack(side="left", fill="both", expand=True, padx=T.px(14), pady=T.px(9))
        self.title_label = tk.Label(self._box, text=title, bg=bg, fg=T.FG,
                                    font=T.FONT_BODY, anchor="w")
        self.title_label.pack(anchor="w")
        self.subtitle_label = None
        if subtitle:
            self.subtitle_label = tk.Label(
                self._box, text=subtitle, bg=bg, fg=T.MUTED, font=T.FONT_SM,
                anchor="w", wraplength=T.px(520), justify="left")
            self.subtitle_label.pack(anchor="w", pady=(1, 0))
        self.suffix_box = tk.Frame(self, bg=bg)
        self.suffix_box.pack(side="right", padx=T.px(8))
        self._hover = False
        for widget in (self, self._box, self.title_label):
            widget.bind("<Enter>", self._on_enter, add="+")
            widget.bind("<Leave>", self._on_leave, add="+")
        if command is not None:
            for widget in (self, self._box, self.title_label):
                widget.bind("<Button-1>", lambda _e: command())
                widget.configure(cursor="hand2" if widget is self else widget.cget("cursor"))

    def _on_enter(self, _e=None):
        self._hover = True
        self._paint_hover()

    def _on_leave(self, _e=None):
        self._hover = False
        self._paint_hover()

    def _paint_hover(self):
        bg = _over(self._bg, 0.05) if self._hover else self._bg
        try:
            self.configure(bg=bg)
            self._box.configure(bg=bg)
            self.title_label.configure(bg=bg)
            self.suffix_box.configure(bg=bg)
            if self.subtitle_label is not None:
                self.subtitle_label.configure(bg=bg)
        except Exception:
            pass

    def set_subtitle(self, subtitle: str):
        if self.subtitle_label is not None:
            self.subtitle_label.configure(text=subtitle)

    def add_suffix(self, widget, **kwargs):
        kwargs.setdefault("side", "right")
        kwargs.setdefault("padx", (6, 0))
        widget.pack(in_=self.suffix_box, **kwargs)
        return widget

    def add_prefix(self, widget, **kwargs):
        kwargs.setdefault("side", "left")
        kwargs.setdefault("padx", (0, 10))
        widget.pack(in_=self._box, before=self.title_label, **kwargs)
        return widget


class EntryRow(tk.Frame):
    """A boxed-list row with an embedded entry (Adw.EntryRow)."""

    def __init__(self, master, title: str = "", text: str = "",
                 placeholder: str = "", bg=None, width: int = 30, **kwargs):
        bg = bg or T.SURFACE
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self._bg = bg
        box = tk.Frame(self, bg=bg)
        box.pack(fill="both", expand=True, padx=T.px(14), pady=T.px(8))
        self.title_label = tk.Label(box, text=title, bg=bg, fg=T.MUTED,
                                    font=T.FONT_SM, anchor="w")
        self.title_label.pack(anchor="w")
        self.entry = tk.Entry(box, bg=bg, fg=T.FG, insertbackground=T.FG,
                              relief="flat", bd=0, font=T.FONT_BODY,
                              highlightthickness=0, width=width)
        self.entry.pack(anchor="w", fill="x", pady=(2, 0), ipady=3)
        if text:
            self.entry.insert(0, text)
        self.suffix_box = tk.Frame(self, bg=bg)
        self.suffix_box.pack(side="right", padx=T.px(8))

    def get(self):
        return self.entry.get()

    def set(self, text: str):
        self.entry.delete(0, "end")
        self.entry.insert(0, text)

    def add_suffix(self, widget, **kwargs):
        kwargs.setdefault("side", "right")
        kwargs.setdefault("padx", (6, 0))
        widget.pack(in_=self.suffix_box, **kwargs)
        return widget


class ComboRow(tk.Frame):
    """A boxed-list row with a dropdown (Adw.ComboRow)."""

    def __init__(self, master, title: str = "", values: Optional[list] = None,
                 selected: int = 0, command=None, bg=None, **kwargs):
        bg = bg or T.SURFACE
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self._bg = bg
        self._command = command
        box = tk.Frame(self, bg=bg)
        box.pack(side="left", fill="both", expand=True, padx=T.px(14), pady=T.px(8))
        self.title_label = tk.Label(box, text=title, bg=bg, fg=T.FG,
                                    font=T.FONT_BODY, anchor="w")
        self.title_label.pack(anchor="w")
        self.variable = tk.StringVar(
            value=(values[selected] if values and 0 <= selected < len(values) else ""))
        self.combo = ttk.Combobox(box, textvariable=self.variable,
                                  values=values or [], state="readonly",
                                  style="Dark.TCombobox", font=T.FONT_SM,
                                  width=22)
        self.combo.pack(anchor="w", pady=(2, 0))
        self.combo.bind("<<ComboboxSelected>>", self._changed)

    def _changed(self, _e=None):
        if callable(self._command):
            self._command(self.variable.get())

    def set_values(self, values, keep=True):
        current = self.variable.get()
        self.combo.configure(values=values)
        if keep and current in values:
            self.variable.set(current)
        elif values:
            self.variable.set(values[0])


class SwitchRow(tk.Frame):
    """A boxed-list row with a switch (Adw.SwitchRow)."""

    def __init__(self, master, title: str = "", subtitle: str = "",
                 selected: bool = False, command=None, bg=None, **kwargs):
        bg = bg or T.SURFACE
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self._bg = bg
        self._command = command
        box = tk.Frame(self, bg=bg)
        box.pack(side="left", fill="both", expand=True, padx=T.px(14), pady=T.px(9))
        self.title_label = tk.Label(box, text=title, bg=bg, fg=T.FG,
                                    font=T.FONT_BODY, anchor="w")
        self.title_label.pack(anchor="w")
        self.subtitle_label = None
        if subtitle:
            self.subtitle_label = tk.Label(box, text=subtitle, bg=bg,
                                           fg=T.MUTED, font=T.FONT_SM,
                                           anchor="w", wraplength=T.px(440),
                                           justify="left")
            self.subtitle_label.pack(anchor="w", pady=(1, 0))
        self.switch = Switch(self, command=command, selected=selected, bg=bg)
        self.switch.pack(side="right", padx=(0, T.px(14)))
        self.variable = self.switch.variable
        self.check = self.switch
        # clicking anywhere on the row toggles (Adw.SwitchRow behaviour)
        for widget in (self, box, self.title_label):
            widget.bind("<Button-1>", lambda _e: self._toggle())
            widget.configure(cursor="hand2")
        if self.subtitle_label is not None:
            self.subtitle_label.bind("<Button-1>",
                                     lambda _e: self._toggle())

    def _toggle(self):
        self.switch._flip()

    def get_active(self):
        return self.switch.get_selected()

    def set_active(self, selected: bool):
        self.switch.set_selected(selected)


class PreferencesGroup(tk.Frame):
    """A titled group of boxed-list rows (Adw.PreferencesGroup)."""

    def __init__(self, master, title: str = "", description: str = "",
                 bg: Optional[str] = None, **kwargs):
        bg = bg or T.WINDOW
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self._bg = bg
        if title:
            tk.Label(self, text=title, bg=bg, fg=T.FG, font=T.FONT_SECTION,
                     anchor="w").pack(anchor="w", pady=(0, 6))
        if description:
            tk.Label(self, text=description, bg=bg, fg=T.MUTED,
                     font=T.FONT_SM, anchor="w").pack(anchor="w", pady=(0, 6))
        self.card = tk.Frame(self, bg=T.SURFACE, highlightthickness=0, bd=0)
        self.card.pack(fill="x")
        self.rows = 0

    def add(self, widget):
        if self.rows:
            tk.Frame(self.card, bg=T.WINDOW, height=1).pack(fill="x")
        widget.pack(in_=self.card, fill="x")
        self.rows += 1
        return widget


class StatusPage(tk.Frame):
    """Adwaita's centred status page: big paintable, title, description."""

    def __init__(self, master, title: str = "", description: str = "",
                 paintable=None, bg: Optional[str] = None, **kwargs):
        bg = bg or T.WINDOW
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self._bg = bg
        self._content = tk.Frame(self, bg=bg)
        self._content.place(relx=0.5, rely=0.5, anchor="center")
        if paintable is not None:
            lbl = tk.Label(self._content, image=paintable, bg=bg)
            lbl.image = paintable
            lbl.pack(pady=(0, T.px(14)))
        self.title_label = tk.Label(self._content, text=title, bg=bg, fg=T.FG,
                                    font=T.FONT_HERO)
        self.title_label.pack()
        self.description_label = tk.Label(self._content, text=description,
                                          bg=bg, fg=T.MUTED, font=T.FONT_BODY,
                                          justify="center")
        self.description_label.pack(pady=(T.px(6), 0))
        self.child = tk.Frame(self._content, bg=bg)
        self.child.pack(pady=(T.px(16), 0))

    def set_title(self, title: str):
        self.title_label.configure(text=title)

    def set_description(self, description: str):
        self.description_label.configure(text=description)


def format_playtime(seconds: int) -> str:
    """Human playtime: days, hours and minutes (e.g. "2 d 5 h", "3 h 20 min",
    "45 min", "Never played")."""
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0:
        return "Never played"
    if seconds < 60:
        return "Less than a minute"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours < 24:
        if minutes:
            return f"{hours} h {minutes} min"
        return f"{hours} h"
    days, hours = divmod(hours, 24)
    if hours:
        return f"{days} d {hours} h"
    return f"{days} d"


class Tooltip:
    """A small delayed tooltip (KDE/Breeze style) for icon-only controls."""

    DELAY = 650

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self._job = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self._job = self.widget.after(self.DELAY, self._show)

    def _cancel(self):
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _show(self):
        if self._tip is not None or not self.widget.winfo_exists():
            return
        tip = tk.Toplevel(self.widget)
        tip.overrideredirect(True)
        tip.configure(bg=T.BORDER)
        try:
            tip.attributes("-topmost", True)
        except Exception:
            pass
        tk.Label(tip, text=self.text, bg=T.CARD, fg=T.FG_SOFT,
                 font=T.FONT_SM, padx=T.px(10), pady=T.px(5),
                 justify="left").pack(padx=1, pady=1)
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + T.px(6)
        tip.update_idletasks()
        tip.geometry(f"+{max(0, x - tip.winfo_width() // 2)}+{max(0, y)}")
        self._tip = tip

    def _hide(self, _e=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


def tooltip(widget, text: str):
    """Attach a KDE-style tooltip to ``widget``."""
    return Tooltip(widget, text)


def toast(parent, text, duration=3000):
    """Compatibility wrapper around the non-blocking toast notification."""
    from .toast import show_toast
    show_toast(parent, text, duration=duration)
