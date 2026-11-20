"""gameRemover port — an Adwaita alert style dialog.

"Remove X?" with two explicit confirmations and a destructive Remove
action. All removal logic is unchanged.
"""
from __future__ import annotations

import os
import shutil
import tkinter as tk

from .. import files_worker, i18n, icons
from ..process_util import xdg_user_dir
from ..theme import *  # noqa: F401,F403 — tokens
from .. import theme as T
from ..widgets import IconButton, RoundedButton

DIALOG_W, DIALOG_H = 440, 300  # logical px — scaled at build time


class GameRemover:
    def __init__(self, app, game_name: str):
        self.app = app
        self.game_name = game_name
        self.legacy_prefix = os.path.join(
            os.path.dirname(app.games.get("executable", game_name) or ""), "OFME Prefix")
        self.prefix_path = app.games.get("prefixPath", game_name) or ""
        self.main_path = app.games.get("mainPath", game_name) or ""

        self.win = tk.Toplevel(app.root)
        self.win.title("Game Removing")
        self.win.configure(bg=BACKDROP)
        self.win.resizable(False, False)
        self.win.transient(app.root)
        try:
            logo = icons.logo(64)
            self.win.iconphoto(True, logo)
            self._icon_ref = logo
        except Exception:
            pass

        self._build()
        self._load_state()
        self.win.bind("<Escape>", lambda e: self.hide())
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self._center()
        self.win.lift()
        self.win.focus_force()

    def _build(self):
        self.win.update_idletasks()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"{min(T.px(DIALOG_W), sw - T.px(24))}x{min(T.px(DIALOG_H), sh - T.px(24))}")
        card = tk.Frame(self.win, bg=WINDOW, highlightthickness=1,
                        highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=T.px(14), pady=T.px(14))

        tk.Label(card, text=f"Remove {self.game_name}?", bg=WINDOW, fg=FG,
                 font=T.FONT_SUBTITLE, anchor="w",
                 wraplength=360, justify="left").pack(anchor="w",
                                                      padx=22, pady=(20, 2))
        tk.Label(card,
                 text="The launcher entry and shortcuts will be removed.",
                 bg=WINDOW, fg=MUTED, font=T.FONT_BODY, anchor="w",
                 wraplength=360, justify="left").pack(anchor="w", padx=22)

        body = tk.Frame(card, bg=WINDOW)
        body.pack(fill="x", padx=22, pady=(10, 0))

        self.remove_prefix_var = tk.BooleanVar(value=False)
        self.remove_files_var = tk.BooleanVar(value=False)

        self.prefix_check = self._check_row(body,
                                            i18n._("GAMEREMOVER.PREFIXREMOVE"),
                                            self.remove_prefix_var)
        self.files_check = self._check_row(body,
                                           i18n._("GAMEREMOVER.DISKREMOVE"),
                                           self.remove_files_var)

        row = tk.Frame(card, bg=WINDOW)
        row.pack(fill="x", padx=22, pady=(16, 20))
        RoundedButton(row, width=130, height=38, text=i18n._("DIALOG.YES"),
                      command=self._yes, variant="destructive", radius=8
                      ).pack(side="right")
        RoundedButton(row, width=110, height=38, text=i18n._("DIALOG.NO"),
                      command=self.hide, radius=8).pack(side="right",
                                                        padx=(0, 10))

    def _check_row(self, parent, text: str, var: tk.BooleanVar):
        row = tk.Frame(parent, bg=WINDOW, cursor="hand2")
        row.pack(fill="x", pady=4)
        lbl = tk.Label(row, text=text, bg=WINDOW, fg=FG_SOFT,
                       font=T.FONT_BODY, anchor="w")
        lbl.pack(side="left", fill="x", expand=True)
        check = tk.Checkbutton(row, variable=var, bg=WINDOW,
                               activebackground=WINDOW, activeforeground=FG,
                               selectcolor=FIELD, fg=FG_SOFT,
                               highlightthickness=0, bd=0, cursor="hand2")
        check.pack(side="right", padx=(0, 2))
        for w in (row, lbl):
            w.bind("<Button-1>", lambda _e: check.toggle())
        return check

    def _center(self):
        self.win.update_idletasks()
        try:
            sw = self.win.winfo_screenwidth()
            sh = self.win.winfo_screenheight()
            self.win.geometry(f"+{(sw - T.px(DIALOG_W)) // 2}+{(sh - T.px(DIALOG_H)) // 2}")
        except Exception:
            pass

    def _load_state(self):
        legacy = os.path.isdir(self.legacy_prefix)
        prefix = os.path.isdir(self.prefix_path) if self.prefix_path else False

        if not prefix and not legacy:
            self.remove_prefix_var.set(False)
            self.prefix_check.configure(state="disabled")
        elif legacy or (self.prefix_path and self.prefix_path in self.main_path):
            self.remove_prefix_var.set(True)
            self.prefix_check.configure(state="disabled")
        else:
            self.remove_prefix_var.set(True)

        has_files = os.path.isdir(self.main_path)
        self.remove_files_var.set(False)
        if not has_files:
            self.files_check.configure(state="disabled")

    def _yes(self):
        game_name = self.game_name
        games = self.app.games

        if self.remove_prefix_var.get():
            prefix = self.prefix_path or self.legacy_prefix
            if prefix and os.path.isdir(prefix):
                shutil.rmtree(prefix, ignore_errors=True)

        if self.remove_files_var.get():
            game_path = self.main_path
            if not game_path:
                game_path = os.path.dirname(games.get("executable", game_name) or "")
            if game_path and os.path.isdir(game_path):
                shutil.rmtree(game_path, ignore_errors=True)

        icon = games.get("icon", game_name)
        banner = games.get("banner", game_name)
        for path in (
            os.path.join(xdg_user_dir("DESKTOP"), f"{game_name}.desktop"),
            os.path.join(os.path.expanduser("~"), ".local/share/applications",
                         f"{game_name}.desktop"),
            icon,
            banner,
        ):
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

        try:
            games.remove_section(game_name)
        except Exception:
            pass

        main = self.app.main_form
        if main is not None:
            try:
                main.remove_game(game_name)
            except Exception:
                pass

        self.hide()

    def hide(self):
        self.win.destroy()

    def show(self):
        self.win.deiconify()
