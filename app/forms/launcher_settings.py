"""OnlineFix launcher settings — the reference "Preferences" dialog.

A centred modal card on a dimmed backdrop: Folders (with Change
actions), Defaults (dropdowns), Behaviour (switches) and About. All
storage keys and behaviours are unchanged.
"""
from __future__ import annotations

import tkinter as tk

from .. import dialogs, files_worker, i18n, icons
from ..process_util import open_url
from ..runtime import GLOBALS
from ..theme import *  # noqa: F401,F403 — tokens
from ..theme import font as _font
from .. import theme as T
from ..widgets import (ActionRow, ComboRow, IconButton, PreferencesGroup,
                       RoundedButton, ScrollFrame, SwitchRow, toast)

class LauncherSettingsPage(tk.Frame):
    """Launcher preferences — an in-window page (no separate window)."""

    def __init__(self, window):
        super().__init__(window.content, bg=WINDOW)
        self.window = window
        self.app = window.app
        self.active = "general"
        self.win = _PageWin(self)
        self.pages = {}
        self.nav_buttons = {}

        self._build()

    def show(self):
        for page in self.window._iter_pages():
            page.pack_forget()
        self.pack(fill="both", expand=True)
        self.window._page = "settings"
        self.window._paint_nav("settings")

    def hide(self):
        self.window.show_library()

    # ------------------------------------------------------------------ shell
    def _build(self):
        from ..widgets import HeaderBar, WindowControls
        self.header = HeaderBar(self, draggable=True)
        self.header.pack(fill="x")
        back = IconButton(self.header, image=icons.icon("back", 18),
                          size=34, command=self.hide)
        self.header.pack_start(back, padx=(8, 0))
        self.title_label = self.header.set_title("Preferences")
        self.header.pack_end(WindowControls(
            self.header, bg=WINDOW,
            on_minimize=self.window.frameless.minimize,
            on_maximize=self.window.frameless.maximize,
            on_close=self.window._on_window_close))

        body = ScrollFrame(self, bg=WINDOW)
        body.pack(fill="both", expand=True)
        content = body.inner

        self._build_folders(content)
        self._build_defaults(content)
        self._build_behavior(content)
        self._build_about(content)

    def _build_folders(self, content):
        group = PreferencesGroup(content, title="Folders")
        group.pack(fill="x", padx=T.px(22), pady=(T.px(16), 0))
        rows = (
            ("installs", "Games folder",
             self.app.launcher.get("installsPath", "User Settings") or ""),
            ("downloads", "Downloads folder",
             self.app.launcher.get("downloadsPath", "User Settings") or ""),
            ("protons", "Proton versions",
             self.app.launcher_settings.get_base_path_for("protons")),
            ("prefixes", "Wine prefixes",
             self.app.launcher_settings.get_base_path_for("prefixes")),
        )
        for key, label, value in rows:
            row = ActionRow(group.card, title=label, subtitle=value or "—")
            row.add_suffix(RoundedButton(
                row.suffix_box, text="Change", variant="normal", height=30,
                padx=10, pady=3, font=T.FONT_SM, radius=6,
                image=icons.icon("pencil", 14), compound="left",
                command=lambda k=key: self._choose_path(k)))
            group.add(row)

    def _choose_path(self, key):
        self.app.launcher_settings.set_with_dir_chooser(f"{key}Path")

    def _build_defaults(self, content):
        group = PreferencesGroup(content, title="Defaults",
                                 description="Used when adding new games.")
        group.pack(fill="x", padx=T.px(22), pady=(T.px(18), 0))

        runner_row = ComboRow(group.card, title="Default runner",
                              values=["Proton", "Wine"],
                              selected=0 if (self.app.launcher.get(
                                  "defaultRunner", "User Settings")
                                  or "proton") == "proton" else 1,
                              command=self._on_runner)
        group.add(runner_row)

        protons = ["(newest installed)"] + files_worker.get_installed_protons()
        saved = self.app.launcher.get("defaultProton", "User Settings") or ""
        selected = protons.index(saved) if saved in protons else 0
        proton_row = ComboRow(group.card, title="Default Proton",
                              values=protons, selected=selected,
                              command=self._on_proton)
        group.add(proton_row)

        fix_row = ComboRow(group.card, title="Default fix",
                           values=["OnlineFix", "FreeTP", "Custom", "No fix"],
                           command=self._on_fix)
        group.add(fix_row)

    def _on_runner(self, value):
        self.app.launcher.set("defaultRunner",
                              "proton" if value == "Proton" else "wine",
                              "User Settings")

    def _on_proton(self, value):
        self.app.launcher.set(
            "defaultProton", "" if value.startswith("(") else value,
            "User Settings")

    def _on_fix(self, value):
        keys = {"OnlineFix": "onlinefix", "FreeTP": "freetp",
                "Custom": "custom", "No fix": "none"}
        self.app.launcher.set("defaultFixType", keys.get(value, "onlinefix"),
                              "User Settings")

    def _build_behavior(self, content):
        group = PreferencesGroup(content, title="Behaviour")
        group.pack(fill="x", padx=T.px(22), pady=(T.px(18), 0))

        group.add(SwitchRow(
            group.card, title=i18n._("LAUNCHERSETTINGS.LAUNCHER.FULLSCREEN"),
            selected=self.app.launcher.get_bool("fullscreen", "User Settings"),
            command=self._toggle_fullscreen))
        group.add(SwitchRow(
            group.card, title=i18n._("LAUNCHERSETTINGS.LAUNCHER.REQUESTSTEAM"),
            subtitle="Skip the \"is Steam running?\" check when starting games.",
            selected=self.app.launcher.get_bool("noSteamRequest", "User Settings"),
            command=lambda v: self.app.launcher.set("noSteamRequest", v,
                                                    "User Settings")))
        group.add(SwitchRow(
            group.card, title=i18n._("SETTINGSMODULE.USEWINED3D"),
            selected=self.app.launcher.get_bool("gamesUsesWined3d", "User Settings"),
            command=lambda v: self.app.launcher.set("gamesUsesWined3d", v,
                                                    "User Settings")))
        group.add(SwitchRow(
            group.card, title=i18n._("SETTINGSMODULE.NATIVEWAYLAND"),
            selected=self.app.launcher.get_bool("gamesUsesWayland", "User Settings"),
            command=lambda v: self.app.launcher.set("gamesUsesWayland", v,
                                                    "User Settings")))

    def _toggle_fullscreen(self, selected):
        self.app.launcher.set("fullscreen", selected, "User Settings")
        try:
            main = self.app.main_form
            if selected:
                main.frameless.maximize()
            else:
                main.frameless.maximize()  # toggles back
        except Exception:
            pass

    def _build_about(self, content):
        group = PreferencesGroup(content)
        group.pack(fill="x", padx=T.px(22), pady=(T.px(18), T.px(16)))
        about = RoundedButton(group.card, text="About OnlineFix Launcher",
                              command=self._about, height=34, variant="flat",
                              image=icons.icon("gamepad", 15), compound="left")
        about.pack(anchor="center", pady=10)
        tk.Label(group.card, text=f"Version {GLOBALS.get('version', '2.7.1')}",
                 bg=SURFACE, fg=DIM, font=T.FONT_TINY).pack(pady=(0, 10))

    def _about(self):
        dialogs.show_message(
            self.win,
            f"OnlineFix Linux Launcher\n\nVersion {GLOBALS.get('version', '2.7.1')}\n\n"
            "A Linux launcher for OnlineFix games, powered by Proton.",
            "About", kind="info")

    # ------------------------------------------------------------------ compat
    def switch_page(self, key: str, button_id: str = None):
        """Legacy no-op — everything is one scrollable page now."""
        return


class LauncherSettings(LauncherSettingsPage):
    """Legacy name."""


class _PageWin:
    """Light shim so page code can use ``self.win`` like a Toplevel."""

    def __init__(self, page: "LauncherSettingsPage"):
        self._page = page

    def title(self, text: str = None):
        if text is not None:
            self._page.window.win.title(f"{text} — OnlineFix")
        return self._page.window.win.title()

    def __getattr__(self, name):
        return getattr(self._page.window.win, name)
