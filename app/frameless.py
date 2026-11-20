"""Frameless window shell — the reference launcher draws its own chrome.

GTK4 apps draw the header bar *inside* the window (client-side
decorations), so there is no system title bar. This module gives Tk the
same behaviour: no WM decorations, an invisible resize gutter on every
edge, drag-to-move on the header bar and round window controls.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from . import theme as T

GUTTER = 6


class FramelessWindow:
    """Attach frameless behaviour (move + resize) to a Tk root window."""

    def __init__(self, root: tk.Wm, min_w: int = 720, min_h: int = 480,
                 bg: Optional[str] = None):
        self.root = root
        self.min_w = min_w
        self.min_h = min_h
        self.bg = bg or T.WINDOW
        self._maximized = False
        self._prev_geo: Optional[tuple[int, int, int, int]] = None

        try:
            root.overrideredirect(True)
        except Exception:
            pass

        self._build_gutters()
        self._install_signals()

    # ------------------------------------------------------------------ gutters
    def _build_gutters(self):
        root = self.root
        cursors = {
            "n": "top_side", "s": "bottom_side", "w": "left_side",
            "e": "right_side", "nw": "top_left_corner", "ne": "top_right_corner",
            "sw": "bottom_left_corner", "se": "bottom_right_corner",
        }
        self._gutters: dict[str, tk.Frame] = {}
        specs = {
            "n":  dict(relx=0, rely=0, relwidth=1, height=GUTTER, bordermode="outside"),
            "s":  dict(relx=0, rely=1, relwidth=1, height=GUTTER, y=-GUTTER, bordermode="outside"),
            "w":  dict(relx=0, rely=0, width=GUTTER, relheight=1, bordermode="outside"),
            "e":  dict(relx=1, rely=0, width=GUTTER, relheight=1, x=-GUTTER, bordermode="outside"),
            "nw": dict(relx=0, rely=0, width=GUTTER * 2, height=GUTTER * 2, bordermode="outside"),
            "ne": dict(relx=1, rely=0, width=GUTTER * 2, height=GUTTER * 2, x=-GUTTER * 2, bordermode="outside"),
            "sw": dict(relx=0, rely=1, width=GUTTER * 2, height=GUTTER * 2, y=-GUTTER * 2, bordermode="outside"),
            "se": dict(relx=1, rely=1, width=GUTTER * 2, height=GUTTER * 2, x=-GUTTER * 2, y=-GUTTER * 2, bordermode="outside"),
        }
        for edge, spec in specs.items():
            frame = tk.Frame(root, bg=self.bg, highlightthickness=0, bd=0)
            frame.place(**spec)
            frame.configure(cursor=cursors[edge])
            frame.bind("<ButtonPress-1>", lambda e, s=edge: self._resize_start(e, s))
            frame.bind("<B1-Motion>", lambda e, s=edge: self._resize_motion(e, s))
            self._gutters[edge] = frame

    def _resize_start(self, event, edge: str):
        self._maximized = False
        self._start = (event.x_root, event.y_root,
                       self.root.winfo_x(), self.root.winfo_y(),
                       self.root.winfo_width(), self.root.winfo_height())
        self._edge = edge

    def _resize_motion(self, event, edge: str):
        x0, y0, wx, wy, ww, wh = self._start
        dx = event.x_root - x0
        dy = event.y_root - y0
        new_x, new_y, new_w, new_h = wx, wy, ww, wh
        if "e" in edge:
            new_w = max(self.min_w, ww + dx)
        if "s" in edge:
            new_h = max(self.min_h, wh + dy)
        if "w" in edge:
            new_w = max(self.min_w, ww - dx)
            if new_w != ww:
                new_x = wx + (ww - new_w)
        if "n" in edge:
            new_h = max(self.min_h, wh - dy)
            if new_h != wh:
                new_y = wy + (wh - new_h)
        try:
            self.root.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")
        except Exception:
            pass

    # ------------------------------------------------------------------ controls
    def minimize(self):
        try:
            self.root.withdraw()
        except Exception:
            pass

    def maximize(self):
        if self._maximized and self._prev_geo:
            w, h, x, y = self._prev_geo
            try:
                self.root.geometry(f"{w}x{h}+{x}+{y}")
            except Exception:
                pass
            self._maximized = False
            return
        try:
            self._prev_geo = (self.root.winfo_width(), self.root.winfo_height(),
                              self.root.winfo_x(), self.root.winfo_y())
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"{sw}x{sh}+0+0")
            self._maximized = True
        except Exception:
            pass

    @property
    def maximized(self) -> bool:
        return self._maximized

    # ------------------------------------------------------------------ signals
    def _install_signals(self):
        """SIGUSR1 from a second launcher process restores the window."""
        import signal

        def handler(_signum, _frame):
            try:
                self.root.after(0, self.restore)
            except Exception:
                pass

        try:
            signal.signal(signal.SIGUSR1, handler)
        except (ValueError, OSError):
            pass

    def restore(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass
