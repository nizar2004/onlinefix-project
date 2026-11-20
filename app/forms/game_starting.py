"""gameStarting port — a flat dark splash in the reference style.

Logo, game name and a slim indeterminate progress line on a rounded
dark card. Launched from a shortcut; hides itself after a few seconds.
"""
from __future__ import annotations

import os
import threading
import tkinter as tk

from .. import assets, files_worker, i18n, icons, runtime
from ..runtime import GLOBALS, ui_later
from .. import theme as T
from ..theme import ACCENT, FG, MUTED, WINDOW, BORDER, FIELD, BACKDROP
from ..theme import font as _font
from ..widgets import _rounded_rect

WIDTH = 440
HEIGHT = 240  # logical px — scaled at build time


class GameStarting:
    def __init__(self, app, game_name: str):
        self.app = app
        self.game_name = game_name

        self.win = tk.Toplevel(app.root)
        self.win.title(game_name)
        self.win.configure(bg=BACKDROP)
        self.win.geometry(f"{T.px(WIDTH)}x{T.px(HEIGHT)}")
        self.win.resizable(False, False)
        self.win.overrideredirect(True)
        try:
            logo = icons.logo(64)
            self.win.iconphoto(True, logo)
            self._icon_ref = logo
        except Exception:
            pass

        self.W, self.H = T.px(WIDTH), T.px(HEIGHT)
        self.canvas = tk.Canvas(self.win, width=self.W, height=self.H,
                                bg=BACKDROP, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        # rounded dark card
        _rounded_rect(self.canvas, 2, 2, self.W - 2, self.H - 2, T.px(18),
                      fill=WINDOW, outline=BORDER)

        # logo
        try:
            self._logo = icons.logo(56)
            self.canvas.create_image(self.W // 2, T.px(72), image=self._logo)
        except Exception:
            pass

        # game name + status
        self.canvas.create_text(
            self.W // 2, T.px(136), text=game_name, fill=FG,
            font=T.font(17, True), width=self.W - T.px(80), justify="center",
        )
        self.canvas.create_text(
            self.W // 2, T.px(166),
            text=i18n._("GAMESTARTER.STARTING") % "",
            fill=MUTED, font=T.font(11), width=self.W - T.px(80),
            justify="center",
        )

        # slim indeterminate progress line
        self._bar_y = self.H - T.px(46)
        self._bar_x = 60
        self.canvas.create_rectangle(T.px(60), self._bar_y, self.W - T.px(60),
                                     self._bar_y + T.px(3), fill=FIELD,
                                     outline="")
        self._bar = self.canvas.create_rectangle(T.px(60), self._bar_y,
                                                 T.px(140), self._bar_y + T.px(3),
                                                 fill=ACCENT, outline="")
        self._bar_job = None
        self._animate_bar()

        self._center()
        self.win.lift()
        self.win.attributes("-topmost", True)
        self.win.after(150, self._start)

    def _animate_bar(self):
        try:
            self._bar_x += T.px(8)
            if self._bar_x > self.W - T.px(140):
                self._bar_x = T.px(60)
            self.canvas.coords(self._bar, self._bar_x, self._bar_y,
                               self._bar_x + T.px(80), self._bar_y + T.px(3))
            self._bar_job = self.win.after(30, self._animate_bar)
        except Exception:
            pass

    def _center(self):
        self.win.update_idletasks()
        x = (self.win.winfo_screenwidth() - self.W) // 2
        y = (self.win.winfo_screenheight() - self.H) // 2
        self.win.geometry(f"{self.W}x{self.H}+{x}+{y}")

    def _start(self):
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        spec = files_worker.generate_process(self.game_name)
        if spec is None:
            ui_later(self.app.shutdown)
            return

        def hide():
            try:
                self.win.withdraw()
            except Exception:
                pass

        ui_later(self.win.after, 5000, hide)
        files_worker.run(spec, self.game_name)
        ui_later(self.app.shutdown)

    def hide(self):
        try:
            if self._bar_job:
                self.win.after_cancel(self._bar_job)
        except Exception:
            pass
        try:
            self.win.withdraw()
        except Exception:
            pass

    def show(self):
        self.win.deiconify()
