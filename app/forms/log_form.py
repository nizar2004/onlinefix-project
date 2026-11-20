"""Log — an in-window console page (no separate window).

Game output streams into this page, reachable from the detail page's
Log button. The page lives inside the main window and keeps its
contents between visits.
"""
from __future__ import annotations

import os
import time
import tkinter as tk

from .. import i18n, icons
from ..process_util import open_path, open_url, xdg_user_dir
from ..theme import *  # noqa: F401,F403 — tokens
from .. import theme as T
from ..theme import font as _font
from ..widgets import HeaderBar, IconButton, RoundedButton, tooltip


class LogPage(tk.Frame):
    def __init__(self, window):
        super().__init__(window.content, bg=WINDOW)
        self.window = window
        self.app = window.app
        self.game_name = ""

        self._build_header()
        self._build_console()

    # ------------------------------------------------------------------ header
    def _build_header(self):
        self.header = HeaderBar(self, draggable=True)
        self.header.pack(fill="x")

        back = IconButton(self.header, image=icons.icon("back", 18),
                          size=34, command=self.window.show_library)
        self.header.pack_start(back, padx=(8, 0))
        tooltip(back, "Back to library")

        self.title_label = self.header.set_title("Log")

        self.header.pack_end(WindowControlsCompat(self))

        RoundedButton(self.header, text="Clear", height=34, radius=8,
                      variant="normal",
                      image=self._icon("trash", 15), compound="left",
                      command=self._clear
                      ).pack(in_=self.header.end_box, side="right",
                             padx=(0, T.px(8)), pady=T.px(6))
        RoundedButton(self.header, text="Telegram", height=34, radius=8,
                      variant="normal", font=T.FONT_SM,
                      image=self._icon("external", 15), compound="left",
                      command=lambda: open_url("https://t.me/queinucentral_chat")
                      ).pack(in_=self.header.end_box, side="right",
                             padx=(0, T.px(8)), pady=T.px(6))
        RoundedButton(self.header, text=i18n._("SAVE"), height=34, radius=8,
                      variant="suggested",
                      image=self._icon("check", 15, color="#FFFFFF"),
                      compound="left", command=self._save
                      ).pack(in_=self.header.end_box, side="right",
                             padx=(0, T.px(10)), pady=T.px(6))

    def _icon(self, name, size=16, color=None):
        return icons.icon(name, size, color=color)

    # ----------------------------------------------------------------- console
    def _build_console(self):
        console = tk.Frame(self, bg=WINDOW, highlightthickness=0)
        console.pack(fill="both", expand=True, padx=T.px(14),
                     pady=(0, T.px(14)))
        self.text_area = tk.Text(
            console, bg=WINDOW, fg=T.FG_SOFT, insertbackground=FG,
            relief="flat", bd=0, wrap="word", font=T.font(11, mono=True),
            padx=T.px(12), pady=T.px(10),
            selectbackground=ACCENT_DIM, selectforeground=ACCENT_SOFT,
        )
        scroll = tk.Scrollbar(console, command=self.text_area.yview,
                              bg=SIDEBAR, troughcolor=WINDOW, bd=0,
                              highlightthickness=0, activebackground=DIM,
                              width=T.px(10))
        self.text_area.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text_area.pack(side="left", fill="both", expand=True)

    # ------------------------------------------------------------------- data
    def set_game(self, name: str):
        self.game_name = name
        try:
            self.title_label.configure(text=f"Log — {name}" if name else "Log")
        except Exception:
            pass

    def prepend_text(self, text: str):
        self.text_area.insert("1.0", text)

    def append_text(self, text: str):
        self.text_area.insert("end", text)
        self.text_area.see("end")

    def _clear(self):
        self.text_area.delete("1.0", "end")

    def _save(self):
        documents = xdg_user_dir("DOCUMENTS")
        folder = os.path.join(documents, "OnlineFix Logs")
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            return
        stamp = time.strftime("%Y-%m-%d %H:%M")
        name = f"{self.game_name or 'game'} {stamp}.log"
        try:
            with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
                fh.write(self.text_area.get("1.0", "end-1c"))
        except OSError:
            return
        open_path(folder)
        from ..widgets import toast
        toast(self.window.win, f"Log saved to {folder}")

    # ------------------------------------------------------------------ compat
    def show(self):
        """Legacy API — the page is part of the main window now."""
        if self.window._page == "detail" and \
                self.window.current_game and not self.game_name:
            self.set_game(self.window.current_game)
        for page in self.window._iter_pages():
            page.pack_forget()
        self.pack(fill="both", expand=True)
        self.window._page = "log"

    def hide(self):
        self.window.show_library()


class WindowControlsCompat(tk.Frame):
    """Window controls bound to the main window (shared by pages)."""

    def __init__(self, page):
        super().__init__(page.header, bg=page.header._bg)
        from ..widgets import WindowControls
        win = page.window
        WindowControls(self, bg=page.header._bg,
                       on_minimize=win.frameless.minimize,
                       on_maximize=win.frameless.maximize,
                       on_close=win._on_window_close).pack()
        self.pack(in_=page.header.end_box, side="right", padx=(0, 0),
                  pady=T.px(6))
