"""Game detail page — mirrors the reference detail view.

An in-window page: back arrow + centred title in the header strip, a
250x375 portrait poster on the left, and a centred right column with the
title, status pills, info rows and the action / link buttons.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from .. import assets, icons
from ..process_util import open_path, open_url
from ..theme import *  # noqa: F401,F403 — tokens
from ..theme import font as _font
from .. import theme as T
from ..widgets import (HeaderBar, Pill, RoundedButton, ScrollFrame,
                       WindowControls, tooltip)

POSTER_W, POSTER_H = 250, 375  # logical px — scaled at build time


class GameDetailPage(tk.Frame):
    def __init__(self, window):
        super().__init__(window.content, bg=WINDOW)
        self.window = window
        self.app = window.app
        self.game_name: str = ""
        self._cover_img = None
        self._icon_refs: dict[str, tk.PhotoImage] = {}

        self._build_header()
        self._build_content()

    # ------------------------------------------------------------------ header
    def _build_header(self):
        self.header = HeaderBar(self, draggable=True)
        self.header.pack(fill="x")

        back = RoundedButton(self.header, width=34, height=34, radius=17,
                             image=self._icon("back", 18),
                             compound="graphic_only", variant="flat",
                             command=self.window.show_library)
        self.header.pack_start(back, padx=(8, 0))
        tooltip(back, "Back to library")

        self.title_label = self.header.set_title("")

        self.header.pack_end(WindowControls(
            self.header, bg=WINDOW,
            on_minimize=self.window.frameless.minimize,
            on_maximize=self.window.frameless.maximize,
            on_close=self.window._on_window_close))

    # ----------------------------------------------------------------- content
    def _build_content(self):
        scroll = ScrollFrame(self, bg=WINDOW)
        scroll.pack(fill="both", expand=True)
        inner = scroll.inner

        row = tk.Frame(inner, bg=WINDOW)
        row.pack(fill="x", padx=T.px(24), pady=T.px(24))

        # --- poster ----------------------------------------------------------
        self.poster = tk.Canvas(row, width=T.px(POSTER_W), height=T.px(POSTER_H),
                                bg=COVER_PLACEHOLDER, highlightthickness=0,
                                bd=0)
        self.poster.pack(side="left", anchor="n")

        # --- right column ------------------------------------------------------
        right = tk.Frame(row, bg=WINDOW)
        right.pack(side="left", fill="both", expand=True, padx=(T.px(28), 0))

        self.name_label = tk.Label(right, text="", bg=WINDOW, fg=FG,
                                   font=T.FONT_HERO, anchor="w",
                                   wraplength=520, justify="left")
        self.name_label.pack(anchor="w")

        self.pill_box = tk.Frame(right, bg=WINDOW)
        self.pill_box.pack(anchor="w", pady=(T.px(10), 0))
        self.pill_fix = Pill(self.pill_box, "", tone="accent")
        self.pill_fix.pack(side="left")
        self.pill_runner = Pill(self.pill_box, "", tone="muted")
        self.pill_runner.pack(side="left", padx=(6, 0))
        self.pill_running = Pill(self.pill_box, "Running", tone="success")
        self.pill_running.pack_forget()

        self.info_box = tk.Frame(right, bg=WINDOW)
        self.info_box.pack(anchor="w", fill="x", pady=(T.px(12), 0))

        actions = tk.Frame(right, bg=WINDOW)
        actions.pack(anchor="w", pady=(T.px(16), 0))
        self.play_btn = RoundedButton(
            actions, text="Play", command=self._on_play, variant="suggested",
            image=self._icon("play", 15, color="#FFFFFF"), compound="left",
            height=42, padx=16, font=T.FONT_PLAY)
        self.play_btn.pack(side="left")
        self.stop_btn = RoundedButton(
            actions, text="Stop", command=self._on_stop, variant="destructive",
            image=self._icon("stop", 15), compound="left",
            height=42, padx=16, font=T.FONT_PLAY)
        RoundedButton(actions, text="Debug", command=self._on_debug,
                      image=self._icon("debug", 15), compound="left",
                      height=42).pack(side="left", padx=(8, 0))
        RoundedButton(actions, text="Log", command=self._on_log,
                      image=self._icon("env", 15), compound="left",
                      height=42).pack(side="left", padx=(8, 0))

        links = tk.Frame(right, bg=WINDOW)
        links.pack(anchor="w", pady=(T.px(8), 0))
        RoundedButton(links, text="Settings", command=self._on_settings,
                      image=self._icon("edit", 15), compound="left",
                      height=42).pack(side="left")
        RoundedButton(links, text="Folder", command=self._on_folder,
                      image=self._icon("folder", 15), compound="left",
                      height=42).pack(side="left", padx=(8, 0))
        RoundedButton(links, text="Steam", command=self._on_steam,
                      image=self._icon("steam", 15), compound="left",
                      height=42).pack(side="left", padx=(8, 0))
        RoundedButton(links, text="ProtonDB", command=self._on_protondb,
                      image=self._icon("external", 15), compound="left",
                      height=42).pack(side="left", padx=(8, 0))
        RoundedButton(links, text="Remove", command=self._on_remove,
                      image=self._icon("trash", 15), compound="left",
                      variant="destructive", height=42
                      ).pack(side="left", padx=(8, 0))

    # ------------------------------------------------------------------ helpers
    def _icon(self, name: str, size: int = 16, color: str | None = None):
        key = (name, size, str(color))
        if key not in self._icon_refs:
            self._icon_refs[key] = icons.icon(name, size, color=color)
        return self._icon_refs[key]

    def _info_row(self, parent, icon_name: str, text: str):
        row = tk.Frame(parent, bg=WINDOW)
        row.pack(anchor="w", fill="x", pady=T.px(3))
        tk.Label(row, image=self._icon(icon_name, 16), bg=WINDOW
                 ).pack(side="left", padx=(0, T.px(8)))
        lbl = tk.Label(row, text=text, bg=WINDOW, fg=T.MUTED,
                       font=T.FONT_SM, anchor="w")
        lbl.pack(side="left", fill="x", expand=True)
        return lbl

    # ------------------------------------------------------------------ show
    def show(self, name: str):
        self.game_name = name
        games = self.app.games

        self.title_label.configure(text=name)
        self.name_label.configure(text=name)

        # poster
        banner = games.get("banner", name)
        try:
            self._cover_img = assets.cover_photo(
                banner, (T.px(POSTER_W), T.px(POSTER_H)), radius=T.px(18),
                fallback="noBanner.png")
            self.poster.delete("all")
            self.poster.create_image(0, 0, anchor="nw", image=self._cover_img)
        except Exception:
            self.poster.delete("all")

        # pills
        fix_path = games.get("fixPath", name)
        self.pill_fix.configure(text="OnlineFix" if fix_path else "No fix")
        proton = games.get("proton", name)
        self.pill_runner.configure(
            text=f"Proton{(' · ' + proton) if proton else ''}")

        # info rows
        for child in self.info_box.winfo_children():
            child.destroy()
        spent = games.get_int("timeSpent", name, 0)
        from ..widgets import format_playtime
        played = ("Played " + format_playtime(spent)) if spent else "Never played"
        self._info_row(self.info_box, "clock", played)
        executable = games.get("executable", name) or "—"
        self._info_row(self.info_box, "folder", executable)
        prefix = games.get("prefixPath", name) or ""
        if prefix:
            self._info_row(self.info_box, "env", f"Prefix: {prefix}")
        self._info_row(self.info_box, "monitor",
                       f"Runner: Proton{(' · ' + proton) if proton else ''}")

        self.refresh_state()

    def refresh_state(self):
        running = self.window.play_state == "stop" and \
            self.window.running_game == self.game_name
        if running:
            self.play_btn.pack_forget()
            self.stop_btn.pack(side="left")
            self.pill_running.pack(side="left", padx=(6, 0))
        else:
            self.stop_btn.pack_forget()
            self.play_btn.pack(side="left")
            self.pill_running.pack_forget()

    # ----------------------------------------------------------------- actions
    def _on_play(self, *_):
        self.window.launch_game(self.game_name, debug=False)

    def _on_stop(self, *_):
        self.window.stop_running_game()

    def _on_debug(self, *_):
        self.window.launch_game(self.game_name, debug=True)

    def _on_log(self, *_):
        self.window.open_log()
        self.window.log_page.set_game(self.game_name)

    def _on_settings(self, *_):
        self.window.open_game_settings(self.game_name)

    def _on_folder(self, *_):
        path = self.app.games.get("mainPath", self.game_name)
        if not path:
            executable = self.app.games.get("executable", self.game_name) or ""
            path = os.path.dirname(executable)
        open_path(path)

    def _on_steam(self, *_):
        steam_id = self.app.games.get("steamID", self.game_name)
        if steam_id:
            open_url(f"https://store.steampowered.com/app/{steam_id}")

    def _on_protondb(self, *_):
        steam_id = self.app.games.get("steamID", self.game_name)
        if steam_id:
            open_url(f"https://www.protondb.com/app/{steam_id}")

    def _on_remove(self, *_):
        self.window._delete_game(self.game_name)
