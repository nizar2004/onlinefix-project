"""Environment variables — an in-window page (no separate window).

The variable/value table uses the shared dark ttk style; add and save
are round floating buttons in the bottom-right corner. All editing and
save logic is unchanged.
"""
from __future__ import annotations

import os
import re
import tkinter as tk
from tkinter import ttk
from typing import Optional

from .. import dialogs, i18n, icons
from .. import theme as T
from ..theme import *  # noqa: F401,F403 — tokens
from ..theme import font as _font
from ..widgets import HeaderBar, IconButton, RoundedButton, tooltip

# Environment entries are stored in the INI file separated by four backslashes
# and the key is separated from the value by "====" (see envViewer.php).
ENV_SEPARATOR = "\\" * 4
ENV_KEY_SEPARATOR = "===="

BLACKLIST = {"WINEDLLOVERRIDES", "PROTON_ENABLE_WAYLAND", "PROTON_USE_WINED3D"}


def parse_environment_array(game: str) -> dict[str, str]:
    """Port of envViewer::parseEnvironmentArray."""
    from .. import runtime

    app = runtime.get_app()
    environment = app.games.get("environment", game) if app else None
    if not environment:
        return {}

    parsed: dict[str, str] = {}
    # Older configs use two backslashes, newer ones four - accept both.
    entries = re.split(r"\\{2,}", environment)
    if len(entries) == 1:
        parts = environment.split(ENV_KEY_SEPARATOR)
        if len(parts) >= 2:
            parsed[parts[0]] = parts[1]
        return parsed

    for entry in entries:
        if not entry:
            continue
        parts = entry.split(ENV_KEY_SEPARATOR)
        if len(parts) < 2:
            continue
        parsed[parts[0]] = parts[1]
    return parsed


def is_blacklisted_env(name: str) -> bool:
    return name in BLACKLIST


class EnvPage(tk.Frame):
    def __init__(self, window, game_name: str, on_back=None):
        super().__init__(window.content, bg=WINDOW)
        self.window = window
        self.app = window.app
        self.game_name = game_name
        self._on_back_cb = on_back
        self._save_dirty = False
        self._icon_refs: dict[str, tk.PhotoImage] = {}

        self._build_header()
        self._build_table()
        self.load_by_game(game_name)

    # ------------------------------------------------------------------ header
    def _build_header(self):
        self.header = HeaderBar(self, draggable=True)
        self.header.pack(fill="x")

        back = IconButton(self.header, image=self._icon("back", 18),
                          size=34, command=self._back)
        self.header.pack_start(back, padx=(8, 0))
        tooltip(back, "Back")

        self.title_label = self.header.set_title(f"{self.game_name} — Environment")

        from ..widgets import WindowControls
        self.header.pack_end(WindowControls(
            self.header, bg=WINDOW,
            on_minimize=self.window.frameless.minimize,
            on_maximize=self.window.frameless.maximize,
            on_close=self.window._on_window_close))

    def _icon(self, name, size=16, color=None):
        key = (name, size, str(color))
        if key not in self._icon_refs:
            self._icon_refs[key] = icons.icon(name, size, color=color)
        return self._icon_refs[key]

    # ------------------------------------------------------------------- table
    def _build_table(self):
        self.table = ttk.Treeview(
            self, columns=("variable", "value"), show="headings",
            style="Treeview", selectmode="browse",
        )
        self.table.heading("variable", text=i18n._("ENVEDITOR.VARIABLE"), anchor="w")
        self.table.heading("value", text=i18n._("ENVEDITOR.VALUE"), anchor="w")
        self.table.column("variable", width=T.px(250), minwidth=T.px(80),
                          stretch=True, anchor="w")
        self.table.column("value", width=T.px(250), minwidth=T.px(80),
                          stretch=True, anchor="w")
        self.table.place(x=0, y=T.HEADER_H, relwidth=1.0,
                         relheight=1.0, height=-T.HEADER_H)

        self.placeholder = tk.Label(
            self, text=i18n._("ENVVIEWER.NOENVS"), bg=CARD, fg=MUTED,
            font=T.font(12, True),
        )
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self._placeholder_visible = True

        self.table.bind("<Double-1>", self._edit_selected)
        self.table.bind("<Return>", self._edit_selected)
        self.table.bind("<Button-3>", self._context_menu)
        self.table.bind("<Delete>", lambda e: self._remove_selected())

        # floating round action buttons, bottom right
        self.add_button = RoundedButton(
            self, width=48, height=48, radius=24,
            image=self._icon("plus", 20, color=FG),
            compound="graphic_only", bg=FIELD, hover=FIELD_HOVER,
            command=self._add)
        self.add_button.place(relx=1.0, rely=1.0, x=-T.px(14), y=-T.px(14),
                              anchor="se", width=T.px(48), height=T.px(48))
        tooltip(self.add_button, "Add variable")
        self.save_button = RoundedButton(
            self, width=48, height=48, radius=24,
            image=self._icon("check", 20, color="#FFFFFF"),
            compound="graphic_only", bg=PRIMARY, hover=PRIMARY_HOVER,
            command=self._save)
        self.save_button.place(relx=1.0, rely=1.0, x=-T.px(14), y=-T.px(70),
                               anchor="se", width=T.px(48), height=T.px(48))
        tooltip(self.save_button, "Save variables")
        self.save_button.set_enabled(False)

    # ------------------------------------------------------------------- data
    def load_by_game(self, game: str):
        self.table.delete(*self.table.get_children())
        for variable, value in parse_environment_array(game).items():
            self.table.insert("", "end", values=(variable, value))
        self._update_placeholder()

    def _update_placeholder(self):
        has_rows = bool(self.table.get_children())
        if has_rows and self._placeholder_visible:
            self.placeholder.place_forget()
            self._placeholder_visible = False
        elif not has_rows and not self._placeholder_visible:
            self.placeholder.place(relx=0.5, rely=0.5, anchor="center")
            self._placeholder_visible = True

    def _mark_dirty(self, dirty: bool):
        self._save_dirty = dirty
        self.save_button.set_enabled(dirty)

    # ------------------------------------------------------------------ events
    def _back(self):
        if self._save_dirty:
            self._save()
        if callable(self._on_back_cb):
            self._on_back_cb()
        else:
            self.window.show_library()

    def _selected_item(self) -> Optional[str]:
        selection = self.table.selection()
        return selection[0] if selection else None

    def _edit_selected(self, event=None):
        item = self._selected_item()
        if not item:
            return
        if event is not None and hasattr(event, "x_root") and event.x_root:
            x, y = event.x_root, event.y_root
        else:
            x = self.window.win.winfo_rootx() + self.window.win.winfo_width() // 2
            y = self.window.win.winfo_rooty() + self.window.win.winfo_height() // 2
        values = self.table.item(item, "values")
        EnvEditor(self, values[0], values[1], x, y)

    def _add(self):
        EnvEditor(self, "", "",
                  self.window.win.winfo_rootx() + self.window.win.winfo_width() // 2,
                  self.window.win.winfo_rooty() + self.window.win.winfo_height() // 2)

    def _context_menu(self, event):
        item = self.table.identify_row(event.y)
        if item:
            self.table.selection_set(item)
            menu = tk.Menu(self.window.win, tearoff=0)
            menu.add_command(label=i18n._("REMOVE"), command=self._remove_selected)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

    def _remove_selected(self):
        item = self._selected_item()
        if item:
            self.table.delete(item)
            self._mark_dirty(True)
            self._update_placeholder()

    def apply_value(self, variable: str, value: str):
        """Called by EnvEditor when the variable / value pair is confirmed."""
        existing = None
        for item in self.table.get_children():
            if self.table.item(item, "values")[0] == variable:
                existing = item
                break
        if existing:
            self.table.item(existing, values=(variable, value))
        else:
            self.table.insert("", "end", values=(variable, value))
        self._mark_dirty(True)
        self._update_placeholder()

    def _save(self):
        parts = []
        for item in self.table.get_children():
            variable, value = self.table.item(item, "values")
            parts.append(f"{variable}{ENV_KEY_SEPARATOR}{value}")
        self.app.games.set("environment", ENV_SEPARATOR.join(parts), self.game_name)
        self._mark_dirty(False)
        from ..widgets import toast
        toast(self.window.win, "Environment saved")

    # ------------------------------------------------------------------ compat
    @property
    def win(self):
        """Legacy attribute — pages live in the main window now."""
        return self.window.win

    def show(self):
        for page in self.window._iter_pages():
            page.pack_forget()
        self.pack(fill="both", expand=True)
        self.window._page = "env"


class EnvEditor:
    """Small popup that edits a single environment variable (envEditor.fxml)."""

    def __init__(self, viewer: EnvPage, variable: str, value: str, x: int, y: int):
        self.viewer = viewer
        self.win = tk.Toplevel(viewer.window.win)
        self.win.configure(bg=SIDEBAR, highlightthickness=1,
                           highlightbackground=BORDER)
        self.win.geometry(f"{T.px(300)}x{T.px(214)}")
        self.win.resizable(False, False)
        self.win.transient(viewer.window.win)
        self.win.overrideredirect(True)

        frame = tk.Frame(self.win, bg=SIDEBAR, padx=T.px(16), pady=T.px(14))
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=i18n._("ENVEDITOR.VARIABLE"), bg=SIDEBAR,
                 fg=MUTED, font=T.font(10, True), anchor="w"
                 ).pack(fill="x", pady=(0, T.px(3)))
        self.env_entry = tk.Entry(frame, bg=FIELD, fg=FG,
                                  insertbackground=FG,
                                  font=T.font(12), relief="flat",
                                  highlightthickness=1,
                                  highlightbackground=WINDOW,
                                  highlightcolor=ACCENT)
        self.env_entry.pack(fill="x", ipady=T.px(6))
        self.env_entry.insert(0, variable)

        tk.Label(frame, text=i18n._("ENVEDITOR.VALUE"), bg=SIDEBAR,
                 fg=MUTED, font=T.font(10, True), anchor="w"
                 ).pack(fill="x", pady=(T.px(10), T.px(3)))
        self.value_entry = tk.Entry(frame, bg=FIELD, fg=FG,
                                    insertbackground=FG,
                                    font=T.font(12), relief="flat",
                                    highlightthickness=1,
                                    highlightbackground=WINDOW,
                                    highlightcolor=ACCENT)
        self.value_entry.pack(fill="x", ipady=T.px(6))
        self.value_entry.insert(0, value)

        RoundedButton(frame, width=150, height=36, text=i18n._("SAVE"),
                      command=self._save, variant="suggested",
                      font=T.font(11, True), radius=8).pack(pady=(T.px(14), 0))

        self.env_entry.bind("<Return>", lambda e: self._save())
        self.value_entry.bind("<Return>", lambda e: self._save())
        self.env_entry.bind("<KeyRelease>", self._env_key)
        self.value_entry.bind("<Control-v>", self._paste)
        self.env_entry.bind("<Control-v>", self._paste)
        self.win.bind("<Escape>", lambda e: self._close())
        self.win.bind("<FocusOut>", lambda e: self.win.after(120, self._maybe_close))

        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        px = max(0, min(int(x) - T.px(150), screen_w - T.px(310)))
        py = max(0, min(int(y), screen_h - T.px(224)))
        self.win.geometry(f"{T.px(300)}x{T.px(214)}+{px}+{py}")
        self.win.lift()
        self.env_entry.focus_set()
        self.win.grab_set()

    def _maybe_close(self):
        try:
            if self.win.focus_get() is None:
                self._close()
        except Exception:
            self._close()

    def _env_key(self, event):
        if event.keysym == "equal" or event.char == "=":
            text = self.env_entry.get().replace("=", "")
            self.env_entry.delete(0, "end")
            self.env_entry.insert(0, text)
            self.value_entry.focus_set()
        elif event.keysym == "Return":
            self._save()

    def _paste(self, event=None):
        try:
            text = self.win.clipboard_get()
        except Exception:
            return
        widget = self.win.focus_get()
        if widget is self.env_entry and "=" in text:
            name, value = text.split("=", 1)
            self.env_entry.delete(0, "end")
            self.env_entry.insert(0, name)
            self.value_entry.delete(0, "end")
            self.value_entry.insert(0, value)
            self.value_entry.focus_set()
            return "break"
        return None

    def _save(self):
        variable = self.env_entry.get().strip()
        value = self.value_entry.get()
        if not variable:
            dialogs.show_message(self.viewer.window.win,
                                 i18n._("ENVEDITOR.NOVARIABLE"), "ERROR")
            return
        if variable == "LD_PRELOAD" and self.viewer.app.games.get_bool(
                "steamOverlay", self.viewer.game_name):
            dialogs.show_message(self.viewer.window.win,
                                 i18n._("ENVEDITOR.STEAMOVERLAY"), "ERROR")
            return
        if is_blacklisted_env(variable):
            dialogs.show_message(self.viewer.window.win,
                                 i18n._("ENVEDITOR.BLACKLISTED"), "ERROR")
            return
        self.viewer.apply_value(variable, value)
        self._close()

    def _close(self):
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()


# Backwards-compatible name used by older call sites.
EnvViewer = EnvPage
