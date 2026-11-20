"""newGameConfigurator port — the reference "Add a Game" wizard.

A centred modal with three pages: pick the game folder, select the main
file, confirm details. All of the original scan / RAR / FreeTP logic is
preserved (SKIP_PATTERNS, auto-select, prefix defaults, clean-after-add).
"""
from __future__ import annotations

import os
import posixpath
import re
import shutil
import threading
import tkinter as tk
from tkinter import filedialog
from typing import Optional

from .. import assets, dialogs, files_worker, fix_parser, ftp_installer, i18n, icons, runtime
from ..rar_extractor import RarExtractor
from ..runtime import ui_later
from ..theme import *  # noqa: F401,F403 — tokens
from ..theme import font as _font
from .. import theme as T
from ..widgets import Card, RoundedButton, ScrollFrame, Switch, toast

DIALOG_W, DIALOG_H = 560, 540  # logical px — scaled at build time

SKIP_LIST = [
    r"^vcredist.*\.exe$",
    r"^vc_redist.*\.exe$",
    r"^dxsetup\.exe$",
    r"^directx.*setup.*\.exe$",
    r"^dxwebsetup\.exe$",
    r"^dotnet.*setup.*\.exe$",
    r"^ndp[A-Za-z0-9._-]*(?=.*-KB\d+)(?=.*-(?:x86|x64))(?=.*-AllOS)(?=.*-ENU)[A-Za-z0-9._-]*\.exe$",
    r"^install.*\.exe$",
    r"^uninstall.*\.exe$",
    r"^unins[0-9]+\.exe$",
    r"^updater.*\.exe$",
    r"^patch.*\.exe$",
    r"^steam\.exe$",
    r"^origin.*\.exe$",
    r"^uplay.*\.exe$",
    r"^epicgames.*\.exe$",
    r"^gog.*\.exe$",
    r"^unitycrashhandler.*\.exe$",
    r"^unitybugreporter.*\.exe$",
    r"^winpixeventruntime.*\.exe$",
    r"^monodistribution.*\.exe$",
    r"^ue4.*prereq.*\.exe$",
    r"^crashreportclient.*\.exe$",
    r"^bugreporter.*\.exe$",
    r"^sandbox.*\.exe$",
    r"^editor.*\.exe$",
    r"^config.*\.exe$",
    r"^settings.*\.exe$",
    r"^options.*\.exe$",
    r"^benchmark.*\.exe$",
    r"^profil(er|ing).*\.exe$",
    r"^crashpad_handler\.exe$",
    r"^(?!.*\.(exe|vbs|bat|rar)$)",
]
SKIP_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in SKIP_LIST]

AUTO_SELECT_NAMES = ("eosauthlauncher.exe", "launcher.exe")


class NewGameConfigurator:
    def __init__(self, app):
        self.app = app
        self.game_params: dict = {
            "path": None,
            "mainFile": None,
            "originalFile": None,
            "canInstall": False,
            "unpackedPath": None,
            "skipConfig": False,
            "openedFromAria": False,
        }
        self._freed = False
        self._candidates: list[list] = []
        self._candidate_rows: list[tk.Frame] = []
        self._selected_index: Optional[int] = None
        self._name_guard = False
        self._install_path_locked = False
        self._clean_enabled = True
        self._scanned_files: list[str] | None = None
        self.pages: dict[str, tk.Frame] = {}

        self.win = tk.Toplevel(app.root)
        self.win.title(i18n._("NEWGAMECONFIG.HEADER"))
        self.win.configure(bg="#0C0C0F")
        self.win.transient(app.root)
        self.win.resizable(False, False)
        try:
            logo = icons.logo(64)
            self.win.iconphoto(True, logo)
            self._icon_ref = logo
        except Exception:
            pass

        self._build_shell()
        self._build_folder_page()
        self._build_exe_page()
        self._build_params_page()
        self._show_page("folder")

        self.win.bind("<Escape>", lambda e: self.close())
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self._center()
        self.win.lift()
        self.win.focus_force()

    # ------------------------------------------------------------- shell
    def _build_shell(self):
        self.win.update_idletasks()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"{min(T.px(DIALOG_W), sw - T.px(24))}x{min(T.px(DIALOG_H), sh - T.px(24))}")
        card = tk.Frame(self.win, bg=WINDOW, highlightthickness=1,
                        highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=T.px(14), pady=T.px(14))
        self.card = card

        header = tk.Frame(card, bg=WINDOW, height=T.HEADER_H)
        header.pack(fill="x")
        header.pack_propagate(False)
        self.header_title = tk.Label(header, text=i18n._("NEWGAMECONFIG.HEADER"),
                                     bg=WINDOW, fg=FG, font=T.FONT_SUBTITLE)
        self.header_title.place(relx=0.5, rely=0.5, anchor="center")
        close = RoundedButton(header, width=34, height=34, radius=17,
                              image=icons.icon("close", 16),
                              compound="graphic_only", command=self.close)
        close.place(relx=1.0, rely=0.5, x=-8, anchor="e")

        self.stack = tk.Frame(card, bg=WINDOW)
        self.stack.pack(fill="both", expand=True, padx=T.px(18))

        # bottom bar: Back | Next
        bottom = tk.Frame(card, bg=WINDOW, height=58)
        bottom.pack(fill="x", padx=T.px(14), pady=(2, T.px(12)))
        bottom.pack_propagate(False)
        self.back_btn = RoundedButton(bottom, text=i18n._("CANCEL"),
                                      height=36, radius=8, variant="normal",
                                      image=icons.icon("close", 14),
                                      compound="right",
                                      command=self._on_back)
        fwd_img = icons.icon("forward", 15, color="#FFFFFF")
        self._next_img = fwd_img
        self.next_btn = RoundedButton(bottom, text="Next", height=36,
                                      radius=8, variant="suggested",
                                      image=fwd_img, compound="right",
                                      command=self._on_next)
        self.next_btn.pack(side="right")

    def _center(self):
        self.win.update_idletasks()
        try:
            sw = self.win.winfo_screenwidth()
            sh = self.win.winfo_screenheight()
            self.win.geometry(f"+{(sw - T.px(DIALOG_W)) // 2}+{(sh - T.px(DIALOG_H)) // 2}")
        except Exception:
            pass

    def _focus_name(self):
        """Put the cursor in the game-name field of the details page."""
        try:
            page = self.pages.get("params")
            if page is not None:
                for child in page.winfo_children():
                    if isinstance(child, tk.Entry):
                        child.focus_set()
                        child.icursor("end")
                        break
        except Exception:
            pass

    def _show_page(self, name: str):
        for child in self.stack.winfo_children():
            child.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        self._page = name
        # header + buttons per page
        titles = {"folder": i18n._("NEWGAMECONFIG.HEADER"),
                  "exe": i18n._("NEWGAMECONFIG.SELECTMAIN"),
                  "params": i18n._("NEWGAMECONFIG.HEADER")}
        self.header_title.configure(text=titles.get(name, ""))
        self.back_btn.pack_forget()
        self.next_btn.pack_forget()
        if name == "folder":
            # the reference hides Back on the first page
            self.next_btn.set_text("Next")
            self.next_btn.pack(side="right")
        elif name == "exe":
            self.back_btn.set_text(i18n._("CANCEL"))
            self.back_btn.pack(side="left")
            self.next_btn.set_text("Next")
            self.next_btn.pack(side="right")
        else:
            self.back_btn.set_text("Back")
            self.back_btn.pack(side="left")
            self.next_btn.set_text(i18n._("ADD"))
            self.next_btn.pack(side="right")
            self.win.after(60, self._focus_name)

    # ------------------------------------------------------------- page 1
    def _build_folder_page(self):
        page = tk.Frame(self.stack, bg=WINDOW)
        self.pages["folder"] = page

        icon_lbl = tk.Label(page, bg=WINDOW)
        try:
            folder_img = icons.icon("folder", 96, color="#ACB2BE")
            icon_lbl.configure(image=folder_img)
            self._folder_icon_img = folder_img
        except Exception:
            pass
        icon_lbl.pack(pady=(T.px(48), T.px(20)))

        tk.Label(page, text="Choose a game folder", bg=WINDOW, fg=FG,
                 font=T.FONT_HERO).pack()
        tk.Label(page, text="Pick the folder that contains the game.\n"
                            "The launcher will scan it for executables.",
                 bg=WINDOW, fg=MUTED, font=T.FONT_BODY, justify="center"
                 ).pack(pady=(T.px(10), 0))

        self.folder_label = tk.Label(page, text="No folder selected",
                                     bg=WINDOW, fg=DIM, font=T.FONT_SM)
        self.folder_label.pack(pady=(T.px(22), 0))

        RoundedButton(page, text="Choose Folder", variant="suggested",
                      height=38, radius=RADIUS_PILL, padx=24,
                      command=self._on_choose_folder).pack(pady=(T.px(12), 0))

    def _on_choose_folder(self):
        path = filedialog.askdirectory(parent=self.win,
                                       title=i18n._("ADDGAME.FILECHOOSER"))
        if not path:
            return
        self.game_params["path"] = path
        self.folder_label.configure(text=path, fg=FG_SOFT)
        self.folder_label.configure(wraplength=420)
        self.next_btn.set_enabled(False)
        self.folder_label.configure(text=f"{path}\nScanning…", fg=DIM)

        def worker():
            files = files_worker.scan_dir(path)
            def done():
                self._scanned_files = files
                self.next_btn.set_enabled(True)
                if not files:
                    self.folder_label.configure(
                        text=f"{path}\nNo executables found.", fg=DIM)
                else:
                    self.folder_label.configure(text=path, fg=FG_SOFT)
            ui_later(done)
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------- page 2
    def _build_exe_page(self):
        page = tk.Frame(self.stack, bg=SURFACE)
        self.pages["exe"] = page

        tk.Label(page, text=i18n._("NEWGAMECONFIG.SELECTMAIN"), bg=SURFACE,
                 fg=FG, font=T.FONT_SECTION, anchor="w").pack(anchor="w",
                                                            pady=(6, 10))
        card = Card(page)
        card.pack(fill="both", expand=True)
        self.candidate_list = ScrollFrame(card.body, bg=SURFACE)
        self.candidate_list.pack(fill="both", expand=True)

    def _fill_candidates(self, candidates: list[list]):
        for child in self.candidate_list.inner.winfo_children():
            child.destroy()
        self._candidates = candidates
        self._candidate_rows = []
        self._selected_index = None
        for index, candidate in enumerate(candidates):
            row = tk.Frame(self.candidate_list.inner, bg=SURFACE,
                           cursor="hand2")
            row.pack(fill="x", pady=2)
            name = tk.Label(row, text=candidate[0], bg=SURFACE, fg=FG,
                            font=T.font(12, True), anchor="w")
            name.pack(fill="x", padx=12, pady=(6, 0))
            folder = tk.Label(row, text=candidate[1] or "/", bg=SURFACE,
                              fg=MUTED, font=T.font(10), anchor="w")
            folder.pack(fill="x", padx=12, pady=(0, 6))
            for widget in (row, name, folder):
                widget.bind("<Button-1>", lambda e, i=index: self._select_row(i))
                widget.bind("<Double-1>", lambda e, i=index: self._select_row(i, go=True))
            if index:
                tk.Frame(self.candidate_list.inner, bg=WINDOW,
                         height=1).pack(fill="x")
            self._candidate_rows.append(row)

    def _select_row(self, index: int, go: bool = False):
        self._selected_index = index
        for i, row in enumerate(self._candidate_rows):
            bg = ACCENT_DIM if i == index else SURFACE
            row.configure(bg=bg, highlightthickness=1 if i == index else 0,
                          highlightbackground=ACCENT)
            children = row.winfo_children()
            if children:
                children[0].configure(bg=bg,
                                      fg=ACCENT_SOFT if i == index else FG)
                for child in children[1:]:
                    child.configure(bg=bg,
                                    fg=ACCENT_SOFT if i == index else MUTED)
        if go:
            self._select_current()

    def _select_current(self):
        if self._selected_index is None:
            toast(self.win, i18n._("NOTHING.SELECTED"))
            return
        self._select_candidate(self._candidates[self._selected_index])

    # ------------------------------------------------------------- page 3
    def _build_params_page(self):
        page = tk.Frame(self.stack, bg=SURFACE)
        self.pages["params"] = page

        # game name ---------------------------------------------------------
        tk.Label(page, text=i18n._("NEWGAMECONFIG.NAME"), bg=SURFACE, fg=MUTED,
                 font=T.FONT_TINY, anchor="w").pack(anchor="w")
        self.game_name_var = tk.StringVar()
        name_entry = tk.Entry(page, textvariable=self.game_name_var,
                              bg=FIELD, fg=FG, insertbackground=FG,
                              relief="flat", bd=0, font=T.font(13),
                              highlightthickness=1,
                              highlightbackground=WINDOW,
                              highlightcolor=ACCENT)
        name_entry.pack(fill="x", ipady=8, pady=(4, 0))
        self.game_name_var.trace_add("write", self._game_name_changed)

        # paths ---------------------------------------------------------------
        tk.Label(page, text="Locations", bg=SURFACE, fg=FG,
                 font=T.FONT_SECTION, anchor="w").pack(anchor="w", pady=(18, 8))
        card = Card(page)
        card.pack(fill="x")
        box = tk.Frame(card.body, bg=SURFACE)
        box.pack(fill="x")

        self.game_path_var = tk.StringVar()
        self._path_row(box, i18n._("NEWGAMECONFIG.GAMEPATH"),
                       self.game_path_var, 0, self._choose_game_path)

        self.ftp_installer_var = tk.StringVar()
        self.ftp_row = self._path_row(box, i18n._("NEWGAMECONFIG.FREETP"),
                                      self.ftp_installer_var, 1,
                                      self._choose_ftp_installer)
        self.ftp_installer_var.trace_add("write", lambda *a: self._refresh_install_mode())

        self.prefix_var = tk.StringVar()
        self._path_row(box, i18n._("NEWGAMECONFIG.PREFIXPATH"),
                       self.prefix_var, 2, self._choose_prefix)

        # clean after add -------------------------------------------------------
        clean_card = Card(page)
        clean_card.pack(fill="x", pady=(14, 0))
        clean_box = tk.Frame(clean_card.body, bg=SURFACE)
        clean_box.pack(fill="x")
        tk.Label(clean_box, text=i18n._("NEWGAMECONFIG.CLEANAFTERADD"),
                 bg=SURFACE, fg=FG, font=T.FONT_BODY, anchor="w"
                 ).pack(side="left", padx=14, pady=10)
        self.clean_after_add = Switch(clean_box, selected=True, bg=SURFACE)
        self.clean_after_add.pack(side="right", padx=12)

    def _path_row(self, parent, label: str, var: tk.StringVar, index: int, command):
        row = tk.Frame(parent, bg=SURFACE, cursor="hand2")
        row.pack(fill="x")
        box = tk.Frame(row, bg=SURFACE)
        box.pack(side="left", fill="both", expand=True, padx=14, pady=8)
        lbl = tk.Label(box, text=label, bg=SURFACE, fg=MUTED,
                       font=T.font(10), anchor="w")
        lbl.pack(anchor="w")
        entry = tk.Entry(box, textvariable=var, bg=SURFACE, fg=FG,
                         relief="flat", bd=0, font=T.font(11),
                         readonlybackground=CARD, state="readonly",
                         highlightthickness=0)
        entry.pack(anchor="w", fill="x")
        for widget in (row, lbl, entry):
            widget.bind("<Button-1>", lambda e: command())
        if index > 0:
            tk.Frame(parent, bg=WINDOW, height=1).pack(fill="x")
        return row

    # ------------------------------------------------------------- helpers
    def is_free(self) -> bool:
        return self._freed

    def _free(self):
        self._freed = True
        try:
            self.win.destroy()
        except Exception:
            pass

    def hide(self):
        self._free()

    def close(self):
        if self._freed:
            return
        opened_from_aria = bool(self.game_params.get("openedFromAria"))
        if opened_from_aria:
            if dialogs.confirm(self.win, i18n._("NEWGAMECONFIG.ARESURE")):
                original = self.game_params.get("originalFile")
                if original:
                    shutil.rmtree(os.path.dirname(original), ignore_errors=True)
                self._free()
        elif self.game_params.get("skipConfig"):
            prefix = self.prefix_var.get()
            if prefix:
                shutil.rmtree(prefix, ignore_errors=True)
            self._free()
        else:
            self._free()

    def _refresh_install_mode(self):
        install = bool(self.ftp_installer_var.get())
        if install:
            self.ftp_row.configure(cursor="hand2")

    # ------------------------------------------------------------- scanning
    @staticmethod
    def check_are_can_listed(file: str) -> bool:
        name = os.path.basename(file)
        for pattern in SKIP_PATTERNS:
            if pattern.search(name):
                return False
        return True

    @staticmethod
    def check_are_install_possible(file: str) -> bool:
        ext = os.path.splitext(file)[1].lower().lstrip(".")
        if ext == "rar":
            return True
        if ext == "exe":
            parent = os.path.dirname(file)
            try:
                return any(f.lower().endswith(".ftp") for f in os.listdir(parent))
            except OSError:
                return False
        return False

    @staticmethod
    def detect_base_path(files: list[str]) -> str:
        candidate = ""
        best = None
        for file in files:
            parent = posixpath.dirname(file.replace("\\", "/"))
            count = parent.count("/")
            if best is None or count < best:
                best = count
                candidate = parent
        return candidate

    @staticmethod
    def _is_file(file: str, files: Optional[list[str]] = None) -> bool:
        if files is None:
            return os.path.isfile(file)
        needle = file.lower()
        return needle in (f.replace("\\", "/").lower() for f in files)

    @classmethod
    def check_are_auto_select_possible(cls, file: str,
                                       rar_files: Optional[list[str]] = None) -> bool:
        name = os.path.basename(file).lower()
        if name not in AUTO_SELECT_NAMES:
            return False
        if name == "launcher.exe":
            return cls._is_file(
                posixpath.dirname(file.replace("\\", "/")) + "/onlinefix.json",
                rar_files,
            )
        return True

    def prepare_for_game(self, files: list[str], path: Optional[str] = None):
        """Populate candidates from a scan (kept for API compatibility)."""
        self.game_params["path"] = path
        self.game_params["unpackedPath"] = None
        if path is None:
            self.game_params["unpackedPath"] = self.detect_base_path(files)

        if self.game_params.get("openedFromAria"):
            self._clean_enabled = False
            self.clean_after_add.set_selected(True)

        candidates: list[list] = []
        candidate_names: list[str] = []

        for file in files:
            if not self.check_are_can_listed(file):
                continue

            file = file.replace("\\", "/")
            ext = os.path.splitext(file)[1].lower().lstrip(".")

            if ext == "rar":
                if os.path.basename(os.path.dirname(file)) == "Fix Repair":
                    continue
                if ".part" in file:
                    no_part = file[:file.rfind(".part")] + ".rar"
                    if os.path.basename(no_part) not in candidate_names:
                        file = no_part
                    else:
                        continue

            file_name = os.path.basename(file)
            if path:
                parent_rel = os.path.dirname(file).replace(path, "", 1) + "/"
            else:
                parent_rel = (os.path.dirname(file) or "") + "/"
            candidates.append([file_name, parent_rel,
                               self.check_are_install_possible(file)])
            candidate_names.append(file_name)

            rar_source = files if self.game_params.get("originalFile") is not None else None
            if self.check_are_auto_select_possible(file, rar_source):
                self._select_candidate(candidates[-1])
                return

        count = len(candidates)
        if count == 0:
            dialogs.show_message(self.win, i18n._("NOTHING.FOUND"), "ERROR")
            self._free()
        elif count == 1:
            runtime.log_info("Only one file, so auto-select")
            self._select_candidate(candidates[0])
        else:
            self._fill_candidates(candidates)
            self._show_page("exe")

    # ---------------------------------------------------------- navigation
    def _on_back(self):
        if self._page == "exe":
            self._show_page("folder")
        elif self._page == "params":
            self._show_page("exe")
        else:
            self.close()

    def _on_next(self):
        if self._page == "folder":
            if not self._scanned_files or not self.game_params.get("path"):
                return
            self.prepare_for_game(self._scanned_files,
                                  self.game_params.get("path"))
        elif self._page == "exe":
            self._select_current()
        elif self._page == "params":
            self._add_game()

    # ---------------------------------------------------------- selection
    def _select_candidate(self, candidate: list):
        can_install = bool(candidate[2])
        base = self.game_params.get("path") or ""
        path = f"{base}{candidate[1]}{candidate[0]}"

        name_no_ext = os.path.splitext(candidate[0])[0]
        ext = os.path.splitext(candidate[0])[1].lower().lstrip(".")
        is_launcher = "launcher" in name_no_ext.lower()

        if can_install and ext == "rar":
            self.game_params["originalFile"] = path
            self.parse_from_rar(path)
            return

        self.game_params["mainFile"] = path
        self.game_params["canInstall"] = can_install

        default_install = self.app.launcher.get("installsPath", "User Settings")
        if not can_install or ext != "exe":
            self.game_path_var.set(self.game_params.get("path") or default_install or "")
            self.ftp_installer_var.set("")
        elif default_install and ext == "exe" and can_install:
            parent_name = os.path.basename(os.path.dirname(path))
            self.game_path_var.set(f"{default_install}/{parent_name}")

        if self.game_params.get("skipConfig"):
            self._add_game()
            return

        if ext == "exe" and not is_launcher and not can_install:
            name = name_no_ext
        else:
            name = os.path.basename(os.path.dirname(path)) or name_no_ext
            name_no_ext = name
        self.game_name_var.set(name)

        if self.game_params.get("path") and not can_install:
            self._install_path_locked = True
            self._clean_enabled = False
            self.clean_after_add.set_selected(False)

        prefixes = self.app.launcher_settings.get_base_path_for("prefixes")
        self.prefix_var.set(f"{prefixes}/{name_no_ext}")

        self._show_page("params")

    def parse_from_rar(self, file: str):
        def worker():
            extractor = RarExtractor()
            try:
                files = extractor.get_rar_content(file)
            except Exception as exc:
                files = extractor.retry_with_ensure_error(str(exc), file)
                if files is None:
                    ui_later(self._free)
                    return
            parsed = []
            for name in files or []:
                name = name.replace("\\", "/").lstrip("/")
                parsed.append("/" + name)
            if not parsed:
                def empty():
                    dialogs.show_message(self.win, i18n._("NEWGAMECONFIG.EMPTYRAR"), "ERROR")
                    self._free()
                ui_later(empty)
                return
            ui_later(lambda: self.prepare_for_game(parsed))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------- editing
    def _game_name_changed(self, *_args):
        if self._name_guard:
            return
        name = self.game_name_var.get()
        default_install = self.app.launcher.get("installsPath", "User Settings")
        prefixes = self.app.launcher_settings.get_base_path_for("prefixes")
        prefix = self.prefix_var.get()
        if prefix and os.path.dirname(prefix) == prefixes:
            self.prefix_var.set(f"{prefixes}/{name}")
        if not os.path.isdir(self.game_path_var.get() or ""):
            self.game_path_var.set(f"{default_install}/{name}" if default_install else name)

    def _choose_game_path(self):
        if self._install_path_locked:
            return
        path = filedialog.askdirectory(parent=self.win,
                                       title=i18n._("ADDGAME.FILECHOOSER"))
        if not path:
            return
        if not self.ftp_installer_var.get() and os.path.isdir(path) and os.listdir(path):
            dialogs.show_message(self.win, i18n._("NEWGAMECONFIG.PATH.NONEMPTY"), "ERROR")
            return
        self.game_path_var.set(path)

    def _choose_prefix(self):
        path = filedialog.askdirectory(parent=self.win)
        if not path:
            return
        if os.path.isdir(path) and os.listdir(path):
            dialogs.show_message(self.win, i18n._("NEWGAMECONFIG.PREFIX.PATHNONEMPTY"),
                                 "WARNING")
        self.prefix_var.set(path)

    def _choose_ftp_installer(self):
        path = filedialog.askopenfilename(
            parent=self.win, title=i18n._("NEWGAMECONFIG.FREETP.FILECHOOSER"),
            filetypes=[(i18n._("NEWGAMECONFIG.FREETP.FILECHOOSER"), "*.exe")])
        if path:
            self.ftp_installer_var.set(path)
            self.ftp_row.configure(cursor="hand2")

    def _refresh_add_state(self):
        self.next_btn.set_enabled(True)

    # ---------------------------------------------------------------- add
    def _check_are_add_possible(self):
        if not self.game_name_var.get() or not self.game_path_var.get() or not self.prefix_var.get():
            return i18n._("NEWGAMECONFIG.FIELDSEMPTY")
        if self.app.games.has_section(self.game_name_var.get()):
            return i18n._("MAINFORM.GAMEEXISTS")
        return True

    def _add_game(self):
        params = self.game_params
        if not params.get("skipConfig"):
            check = self._check_are_add_possible()
            if check is not True:
                dialogs.show_message(self.win, check, "ERROR")
                return

        game_name = self.game_name_var.get()
        game_path = self.game_path_var.get()
        prefix_path = self.prefix_var.get()
        clean_after = self.clean_after_add.get_selected()

        self._free()

        if params.get("canInstall"):
            installers = [params.get("mainFile"), self.ftp_installer_var.get()]
            installers = [i for i in installers if i]
            ftp_installer.install(game_name, installers, prefix_path, game_path,
                                  clean_after)
            return

        main_form = self.app.main_form
        panel = main_form.add_stub_game()
        panel["name"].set_name(game_name)

        def worker():
            original_file = params.get("originalFile")
            path = game_path

            if original_file and os.path.splitext(original_file)[1].lower().lstrip(".") == "rar":
                ui_later(lambda: panel["status"].set_status(i18n._("NEWGAMECONFIG.UNPACKING")))
                extractor = RarExtractor()
                try:
                    extractor.unpack_rar(original_file, game_path)
                except Exception as exc:
                    result = extractor.retry_with_ensure_error(str(exc), original_file,
                                                               game_path)
                    if result is not True:
                        ui_later(lambda: main_form.remove_stub_game(panel["box"]))
                        return

            main_file = params.get("mainFile") or ""
            if not os.path.isfile(main_file):
                main_file = f"{game_path}{main_file}"

            if params.get("unpackedPath"):
                path = f"{game_path}{params['unpackedPath']}"

            ui_later(lambda: panel["status"].set_status(i18n._("NEWGAMECONFIG.DLLS")))
            parsed = fix_parser.parse_dlls(path) or {}
            if parsed.get("fakeAppId") is not None:
                self.app.games.set("fakeSteamID", parsed["fakeAppId"], game_name)

            banner_path = None
            if parsed.get("realAppId") is not None:
                banner_path = fix_parser.parse_banner(str(parsed["realAppId"]))
                if os.path.isfile(str(banner_path)):
                    self.app.games.set("banner", banner_path, game_name)
                else:
                    ui_later(lambda b=banner_path: dialogs.show_message(
                        main_form.win, str(b), "ERROR"))
                self.app.games.set("steamID", parsed["realAppId"], game_name)

            ui_later(lambda: panel["status"].set_status(i18n._("NEWGAMECONFIG.ICOEXTRACT")))
            app_icon = None
            try:
                app_icon = fix_parser.parse_icon(main_file)
                if app_icon and os.path.isfile(app_icon):
                    self.app.games.set("icon", app_icon, game_name)
                else:
                    app_icon = None
            except Exception as exc:
                app_icon = None
                ui_later(lambda msg=str(exc): dialogs.show_message(
                    main_form.win, i18n._("MAINFORM.ICONPARSERERROR") % msg, "ERROR"))

            ui_later(lambda: panel["status"].set_status(i18n._("NEWGAMECONFIG.SETTINGS")))

            default_proton = self.app.launcher.get("defaultProton", "User Settings") or \
                "GE-Proton Latest"
            self.app.games.put({
                "overrides": parsed.get("overrides") or "",
                "executable": main_file,
                "mainPath": path,
                "prefixPath": prefix_path,
                "proton": default_proton,
                "steamRuntime": bool(files_worker.find_steam_runtime(default_proton)),
                "steamOverlay": True,
                "wined3d": self.app.launcher.get("gamesUsesWined3d", "User Settings") or "",
                "nativeWayland": self.app.launcher.get("gamesUsesWayland", "User Settings") or "",
                "fixPath": parsed.get("fixPath") or "",
            }, game_name)

            def finish():
                main_form.remove_stub_game(panel["box"])
                main_form.add_game(game_name, main_file, parsed.get("overrides"),
                                   banner_path, app_icon)
                ui_later(lambda: main_form._toast(f"{game_name} added to your library"))

            ui_later(finish)

            if clean_after and original_file:
                orig_parent = os.path.dirname(original_file)
                if orig_parent and orig_parent in path:
                    ui_later(lambda: dialogs.show_message(
                        main_form.win, i18n._("NEWGAMECONFIG.CLEANSKIPPED"), "WARNING"))
                else:
                    shutil.rmtree(orig_parent, ignore_errors=True)

        threading.Thread(target=worker, daemon=True).start()
