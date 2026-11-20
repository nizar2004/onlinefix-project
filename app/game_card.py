"""Game library card + tiling grid — mirrors the reference library.

A `GameTile` is the portrait cover card from the reference launcher:
a fixed 150x225 cover inside a padded rounded wrapper (white 4% fill,
14px radius, brighter on hover) with a bold 12.5px caption underneath.
Clicking a card opens the game's detail page.

`GameTileGrid` reflows columns automatically as its width changes
(2 minimum, 6 maximum, 14px column gap and 16px row gap — the same
FlowBox settings as the reference).
"""
from __future__ import annotations

import os
import tkinter as tk
from typing import Callable, Optional

from . import theme as T
from .theme import _mix as _mix_hex
from .widgets import _over, _rounded_rect

COVER_W, COVER_H = T.COVER_W, T.COVER_H
PAD = T.CARD_PAD
CAPTION_H = 24

__all__ = ["GameTile", "GameTileGrid", "GameCard", "GameCardGrid"]


class GameTile(tk.Frame):
    """A portrait cover card. Clicking activates (opens the detail page)."""

    WIDTH = COVER_W + PAD * 2          # 162 — .game-card padding included
    HEIGHT = COVER_H + PAD * 2 + CAPTION_H

    REST = _over(T.WINDOW, 0.04)       # rgba(255,255,255,0.04)
    HOVER = _over(T.WINDOW, 0.09)      # .game-card:hover
    SELECTED = _mix_hex(T.WINDOW, T.ACCENT, 0.25)   # .game-card:selected

    def __init__(self, master, title: str, cover=None,
                 on_activate: Optional[Callable] = None,
                 game_icon: str | None = None,
                 **kwargs):
        super().__init__(master, bg=self.REST, bd=0,
                         width=self.WIDTH, height=self.HEIGHT,
                         cursor="hand2", **kwargs)
        self.pack_propagate(False)
        self._title = title
        self._cover_img = cover
        self._on_activate = on_activate
        self._game_icon_path = game_icon
        self._hover = False

        # --- cover ----------------------------------------------------------
        self._cover = tk.Canvas(self, width=COVER_W, height=COVER_H,
                                bg=T.COVER_PLACEHOLDER,
                                highlightthickness=0, bd=0)
        self._cover.place(x=PAD, y=PAD)
        self._render_cover()

        # --- caption (single line, ellipsised like PANGO_ELLIPSIZE_END) -------
        self._caption = tk.Label(self, text=self._ellipsize(title),
                                 bg=self.REST, fg=T.FG,
                                 font=T.FONT_CAPTION, anchor="w")
        self._caption.place(x=PAD + 2, y=PAD + COVER_H + 1, width=COVER_W - 4,
                            height=CAPTION_H - 2)

        # "Running" badge — shown while the game is playing
        self._running_badge = tk.Label(
            self, text="●  Running", bg=T.SUCCESS_BG, fg=T.SUCCESS,
            font=T.FONT_PILL, padx=T.px(9), pady=T.px(3))
        self._running = False

        # small game icon over the cover art (Steam-capsule style)
        self._icon_badge = tk.Label(self, bg=T.COVER_PLACEHOLDER, bd=0)
        self._icon_badge.bind("<Enter>", self._on_enter, add="+")
        self._icon_badge.bind("<Leave>", self._on_leave, add="+")
        self._icon_badge.bind("<Button-1>", self._on_click, add="+")
        self._render_icon_badge()

        for w in (self, self._cover, self._caption):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_click)

    @staticmethod
    def _ellipsize(text: str, max_chars: int = 24) -> str:
        text = " ".join(text.split())
        if len(text) <= max_chars:
            return text
        return text[:max_chars - 1].rstrip() + "…"

    # -- cover ---------------------------------------------------------------
    def _render_cover(self):
        try:
            self._cover.delete("all")
            if self._cover_img is not None:
                self._cover.create_image(0, 0, anchor="nw",
                                         image=self._cover_img)
                self._cover.image = self._cover_img
            else:
                _rounded_rect(self._cover, 0, 0, COVER_W, COVER_H, 10,
                              fill=T.COVER_PLACEHOLDER, outline="")
                self._cover.create_image(COVER_W // 2, COVER_H // 2 - 10,
                                         image=self._placeholder_icon(),
                                         anchor="center")
        except Exception:
            pass

    _placeholder_icon_cache = None

    @classmethod
    def _placeholder_icon(cls):
        if cls._placeholder_icon_cache is None:
            try:
                from . import icons
                cls._placeholder_icon_cache = icons.icon("gamepad", 56,
                                                         color="#5A6170")
            except Exception:
                cls._placeholder_icon_cache = False
        return cls._placeholder_icon_cache or None

    def set_cover(self, image):
        self._cover_img = image
        self._render_cover()

    def set_icon(self, icon_path: str | None):
        """Refresh the small game-icon badge."""
        self._game_icon_path = icon_path
        self._render_icon_badge()

    def _render_icon_badge(self):
        """A small rounded game icon at the cover's bottom-left corner."""
        size = T.px(44)
        photo = None
        if self._game_icon_path and os.path.isfile(self._game_icon_path):
            try:
                from . import assets
                photo = assets.photo(self._game_icon_path, size=(size, size),
                                     radius=T.px(10), stretch=True,
                                     fallback="")
            except Exception:
                photo = None
        if photo is None:
            try:
                from . import icons
                photo = icons.icon("gamepad", 44, color="#8A93A5")
            except Exception:
                photo = None
        if photo is None:
            self._icon_badge.place_forget()
            return
        # subtle border behind the badge so it reads on any cover art
        self._icon_badge.configure(image=photo)
        self._icon_badge.image = photo
        self._icon_badge.configure(highlightthickness=T.px(2),
                                   highlightbackground=T.WINDOW)
        self._icon_badge.place(in_=self._cover, x=0, rely=1.0, y=T.px(0),
                               anchor="sw", width=size, height=size)

    # -- hover -----------------------------------------------------------------
    def _on_enter(self, _e=None):
        self._hover = True
        self._paint(self.HOVER)

    def _on_leave(self, _e=None):
        self._hover = False
        self._paint(self.REST)

    def _paint(self, bg: str):
        try:
            self.configure(bg=bg)
            self._caption.configure(bg=bg)
        except Exception:
            pass

    def set_selected(self, selected: bool):
        self._paint(self.SELECTED if selected else
                    (self.HOVER if self._hover else self.REST))

    def set_running(self, running: bool):
        """Show/hide the green “Running” badge on the cover."""
        self._running = bool(running)
        if self._running:
            self._running_badge.configure(bg=T.SUCCESS_BG, fg=T.SUCCESS)
            self._running_badge.place(in_=self._cover,
                                      relx=1.0, rely=0.0, x=-T.px(8),
                                      y=T.px(8), anchor="ne")
        else:
            self._running_badge.place_forget()

    # -- action ------------------------------------------------------------------
    def _on_click(self, _e=None):
        if callable(self._on_activate):
            self._on_activate()


class GameTileGrid(tk.Frame):
    """Tiles `GameTile`s into a responsive grid (2..6 columns, 14/16 gaps)."""

    COL_GAP = T.FLOW_COL_GAP
    ROW_GAP = T.FLOW_ROW_GAP

    def __init__(self, master, columns: int = 0, **kwargs):
        kwargs.setdefault("bg", T.WINDOW)
        super().__init__(master, **kwargs)
        self._min_columns = max(1, columns)
        self._columns = self._min_columns
        self._cards: list[GameTile] = []
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event=None):
        width = self.winfo_width()
        if width < 40:
            return
        cols = max(self._min_columns,
                   (width + self.COL_GAP) // (GameTile.WIDTH + self.COL_GAP))
        cols = min(cols, 6)
        if cols != self._columns:
            self._columns = int(cols)
            self.reflow()

    def reflow(self):
        for index, card in enumerate(self._cards):
            if card.winfo_ismapped() or card.winfo_manager():
                row, col = divmod(index, self._columns)
                card.grid_configure(row=row, column=col)

    def add(self, tile) -> object:
        row, col = divmod(len(self._cards), self._columns)
        tile.grid(row=row, column=col,
                  padx=(0, self.COL_GAP), pady=(0, self.ROW_GAP),
                  sticky="nw")
        self._cards.append(tile)
        return tile

    def remove(self, tile) -> None:
        if tile in self._cards:
            self._cards.remove(tile)
            self.reflow()

    def clear(self) -> None:
        for tile in self._cards:
            tile.destroy()
        self._cards.clear()


# Backwards-compatible aliases from the old module surface.
GameCard = GameTile
GameCardGrid = GameTileGrid
