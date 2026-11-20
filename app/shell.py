"""Redesigned application shell — Midnight edition: sidebar + content area.

Drop-in container for the entire app. Pack existing form frames into
``shell.content`` and they will inherit the new look automatically.

    from app import bootstrap, shell
    bootstrap(root)
    app = shell.AppShell(root)
    app.pack(fill="both", expand=True)
    app.sidebar.add("Library", icons.icon("library", 18), on_library)
    app.sidebar.add("Settings", icons.icon("settings", 18), on_settings)
    app.sidebar.set_active(0)

Design notes
------------
* The dark sidebar is the only persistent chrome — everything else lives
  in the content area, which each "page" is free to lay out.
* Active nav state = violet pill + accent icon. No underlines.
* The header is a plain title + subtitle. The ``actions`` frame on the
  right is where a screen puts its primary button.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from . import icons
from . import theme as T

__all__ = ["AppShell", "Sidebar", "NavItem", "Header"]


# ---------------------------------------------------------------------------
# NavItem
# ---------------------------------------------------------------------------
class NavItem(tk.Frame):
    """A single sidebar row. Click → command. Active state = violet pill."""

    def __init__(self, master, label: str, image=None,
                 command: Optional[Callable] = None):
        super().__init__(master, bg=T.BG_SOFT, cursor="hand2")
        self._command = command
        self._active = False
        self._image = image
        self._label_text = label

        self._row = tk.Frame(self, bg=T.BG_SOFT)
        self._row.pack(fill="both", expand=True)

        self._icon = tk.Label(self._row, bg=T.BG_SOFT, fg=T.MUTED)
        if image is not None:
            self._icon.configure(image=image)
        self._icon.pack(side="left", padx=(10, 12), pady=10)

        self._label = tk.Label(self._row, text=label, bg=T.BG_SOFT, fg=T.MUTED,
                               font=T.FONT_BUTTON, anchor="w")
        self._label.pack(side="left", fill="x", expand=True)

        for w in (self, self._row, self._icon, self._label):
            w.bind("<Button-1>", self._on_click)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)

    # -- events -------------------------------------------------------------
    def _on_click(self, _e=None):
        if callable(self._command):
            self._command()

    def _on_enter(self, _e=None):
        if not self._active:
            self._paint(bg=T.SURFACE, fg=T.FG)

    def _on_leave(self, _e=None):
        if not self._active:
            self._paint(bg=T.BG_SOFT, fg=T.MUTED)

    # -- internals ----------------------------------------------------------
    def _paint(self, bg: str, fg: str):
        self.configure(bg=bg)
        self._row.configure(bg=bg)
        self._icon.configure(bg=bg, fg=fg)
        self._label.configure(bg=bg, fg=fg)

    # -- public API ---------------------------------------------------------
    def set_active(self, active: bool):
        self._active = bool(active)
        bg = T.ACCENT_DIM if active else T.BG_SOFT
        fg = T.ACCENT_SOFT if active else T.MUTED
        self._paint(bg=bg, fg=fg)
        try:
            if self._image is None:
                return
            # re-tint the icon for the new state
            size = self._image.width()
            from . import icons as _icons
            name = getattr(self, "_icon_name", None)
            if name:
                self._icon.configure(image=_icons.icon(name, size, color=fg))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
class Sidebar(tk.Frame):
    """Fixed-width left rail: brand block + nav items + flexible spacer.

    ``add()`` returns the NavItem so callers can keep a reference if they
    want to update the label later (e.g. add a game count).
    """

    WIDTH = 216

    def __init__(self, master, title: str = "OnlineFix",
                 subtitle: str = "LINUX LAUNCHER"):
        super().__init__(master, bg=T.BG_SOFT, width=self.WIDTH)
        self.pack_propagate(False)
        tk.Frame(master, bg=T.BORDER, width=1).pack(side="left", fill="y") \
            if False else None

        # brand
        brand = tk.Frame(self, bg=T.BG_SOFT)
        brand.pack(fill="x", padx=20, pady=(26, 22))
        try:
            logo = icons.logo(38)
            tk.Label(brand, image=logo, bg=T.BG_SOFT).pack(side="left")
            self._logo = logo
        except Exception:
            pass
        name_box = tk.Frame(brand, bg=T.BG_SOFT)
        name_box.pack(side="left", padx=(12, 0))
        tk.Label(name_box, text=title, bg=T.BG_SOFT, fg=T.FG,
                 font=T.FONT_SUBTITLE, anchor="w").pack(fill="x")
        if subtitle:
            tk.Label(name_box, text=subtitle, bg=T.BG_SOFT, fg=T.DIM,
                     font=T.font(9, "bold"), anchor="w").pack(fill="x")

        # nav list
        self._items: list[NavItem] = []
        self._container = tk.Frame(self, bg=T.BG_SOFT)
        self._container.pack(fill="x")

        # flexible filler — anything docked to the bottom goes above this
        self.bottom = tk.Frame(self, bg=T.BG_SOFT)
        self.bottom.pack(side="bottom", fill="x", pady=(0, 16))
        tk.Frame(self, bg=T.BG_SOFT).pack(fill="both", expand=True)

    def add(self, label: str, image=None, icon_name: str = "",
            command: Optional[Callable] = None) -> NavItem:
        item = NavItem(self._container, label=label, image=image,
                       command=command)
        if icon_name:
            item._icon_name = icon_name
        item.pack(fill="x", padx=12, pady=2)
        self._items.append(item)
        return item

    def set_active(self, index: int) -> None:
        for i, item in enumerate(self._items):
            item.set_active(i == index)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
class Header(tk.Frame):
    """Hero title + subtitle + an empty ``actions`` slot on the right."""

    def __init__(self, master, title: str = "", subtitle: str = ""):
        super().__init__(master, bg=T.BG)
        inner = tk.Frame(self, bg=T.BG)
        inner.pack(fill="x", padx=36, pady=(28, 16))

        # left column: text
        left = tk.Frame(inner, bg=T.BG)
        left.pack(side="left", fill="x", expand=True)

        self._title = tk.Label(left, text=title, bg=T.BG, fg=T.FG,
                               font=T.FONT_TITLE, anchor="w")
        self._title.pack(fill="x")
        self._subtitle = tk.Label(left, text=subtitle, bg=T.BG, fg=T.MUTED,
                                  font=T.FONT_SM, anchor="w")
        self._subtitle.pack(fill="x", pady=(4, 0))

        # right column: caller-owned action area
        self.actions = tk.Frame(inner, bg=T.BG)
        self.actions.pack(side="right", fill="y")

    def set(self, title: str, subtitle: str = "") -> None:
        self._title.configure(text=title)
        self._subtitle.configure(text=subtitle)


# ---------------------------------------------------------------------------
# AppShell
# ---------------------------------------------------------------------------
class AppShell(tk.Frame):
    """Full-window layout. Use ``self.content`` as the page container."""

    def __init__(self, master, title: str = "OnlineFix",
                 subtitle: str = "LINUX LAUNCHER"):
        super().__init__(master, bg=T.BG)
        try:
            master.configure(bg=T.BG)
        except Exception:
            pass

        # --- left rail ------------------------------------------------------
        self.sidebar = Sidebar(self, title=title, subtitle=subtitle)
        self.sidebar.pack(side="left", fill="y")
        tk.Frame(self, bg=T.BORDER, width=1).pack(side="left", fill="y")

        # --- right column ---------------------------------------------------
        right = tk.Frame(self, bg=T.BG)
        right.pack(side="left", fill="both", expand=True)

        self.header = Header(right)
        self.header.pack(fill="x")

        self.content = tk.Frame(right, bg=T.BG)
        self.content.pack(fill="both", expand=True, padx=36, pady=(0, 20))

        # status strip pinned to the bottom of the right column
        self.status = tk.Label(right, text="", bg=T.BG, fg=T.DIM,
                               font=T.FONT_SM, anchor="w", padx=36, pady=8)
        self.status.pack(fill="x", side="bottom")

    # -- convenience ---------------------------------------------------------
    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def set_header(self, title: str, subtitle: str = "") -> None:
        self.header.set(title, subtitle)
