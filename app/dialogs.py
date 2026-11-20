"""Modal dialogs — Adwaita alert style.

Dark centred cards with a bold title, quiet body text and flat actions
(slate suggested / red destructive / normal).
"""
from __future__ import annotations

import tkinter as tk
from typing import Optional

from . import icons, theme
from .widgets import IconButton, RoundedButton


def _center(win: tk.Toplevel, parent):
    win.update_idletasks()
    try:
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
    except Exception:
        px = py = 0
        pw = ph = 0
    w, h = win.winfo_width(), win.winfo_height()
    x = px + (pw - w) // 2 if pw else (win.winfo_screenwidth() - w) // 2
    y = py + (ph - h) // 2 if ph else (win.winfo_screenheight() - h) // 2
    win.geometry(f"+{max(0, x)}+{max(0, y)}")


def _shell(parent, title: str):
    """Build the shared dark alert card with a bold heading."""
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=theme.BACKDROP)
    win.transient(parent)
    win.resizable(False, False)

    frame = tk.Frame(win, bg=theme.WINDOW, highlightthickness=1,
                     highlightbackground=theme.BORDER, padx=theme.px(24),
                     pady=theme.px(20))
    frame.pack(fill="both", expand=True, padx=theme.px(14), pady=theme.px(14))
    tk.Label(frame, text=title, bg=theme.WINDOW, fg=theme.FG,
             font=theme.FONT_SUBTITLE, anchor="w",
             wraplength=theme.px(400), justify="left").pack(anchor="w")
    return win, frame


def show_message(parent, text: str, title: str = "ERROR",
                 kind: str = "error") -> None:
    win, frame = _shell(parent, title)
    tk.Label(frame, text=text, bg=theme.WINDOW, fg=theme.FG_SOFT,
             font=theme.FONT_BODY, wraplength=theme.px(400),
             justify="left").pack(anchor="w", pady=(10, 18))
    row = tk.Frame(frame, bg=theme.WINDOW)
    row.pack(fill="x")
    RoundedButton(row, width=110, height=36, text="OK", command=win.destroy,
                  variant="suggested", radius=8).pack(side="right")
    win.grab_set()
    _center(win, parent)
    win.wait_window()


def confirm(parent, text: str, title: str = "Confirm") -> bool:
    result = {"value": False}
    win, frame = _shell(parent, title)

    def yes():
        result["value"] = True
        win.destroy()

    tk.Label(frame, text=text, bg=theme.WINDOW, fg=theme.FG_SOFT,
             font=theme.FONT_BODY, wraplength=theme.px(400),
             justify="left").pack(anchor="w", pady=(10, 18))
    row = tk.Frame(frame, bg=theme.WINDOW)
    row.pack(fill="x")
    RoundedButton(row, width=110, height=36, text="Yes", command=yes,
                  variant="suggested", radius=8).pack(side="right", padx=(10, 0))
    RoundedButton(row, width=110, height=36, text="No", command=win.destroy,
                  variant="normal", radius=8).pack(side="right")
    win.grab_set()
    _center(win, parent)
    win.wait_window()
    return result["value"]


def ask_string(parent, prompt: str, initial: Optional[str] = None,
               title: str = "Input") -> Optional[str]:
    result = {"value": None}
    win, frame = _shell(parent, title)

    tk.Label(frame, text=prompt, bg=theme.WINDOW, fg=theme.FG_SOFT,
             font=theme.FONT_BODY, wraplength=theme.px(400),
             justify="left").pack(anchor="w", pady=(10, 12))
    entry = tk.Entry(frame, bg=theme.FIELD, fg=theme.FG,
                     insertbackground=theme.FG, font=theme.FONT_BODY,
                     relief="flat", highlightthickness=1,
                     highlightbackground=theme.WINDOW,
                     highlightcolor=theme.ACCENT)
    entry.pack(fill="x", ipady=7)
    if initial:
        entry.insert(0, initial)
    entry.focus_set()

    def ok(_event=None):
        result["value"] = entry.get()
        win.destroy()

    entry.bind("<Return>", ok)
    row = tk.Frame(frame, bg=theme.WINDOW)
    row.pack(fill="x", pady=(16, 0))
    RoundedButton(row, width=110, height=36, text="OK", command=ok,
                  variant="suggested", radius=8).pack(side="right", padx=(10, 0))
    RoundedButton(row, width=110, height=36, text="Cancel",
                  command=win.destroy, variant="normal",
                  radius=8).pack(side="right")
    win.grab_set()
    _center(win, parent)
    win.wait_window()
    return result["value"]
