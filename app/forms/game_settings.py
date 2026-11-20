"""gameSettings port — mirrors the reference game settings page.

An in-window page with preference groups (General, Artwork, Launch,
Multiplayer fix, Graphics). All of the original behaviour is preserved:
icon & banner editing, renaming, Proton selection, prefix, DLL
overrides, environment, args and the compatibility toggles.
"""
from __future__ import annotations

import os
import shutil
import threading
import tkinter as tk
from tkinter import filedialog

from .. import assets, dialogs, files_worker, fix_parser, i18n, icons, runtime
from ..assets import BASE_DIR
from ..process_util import open_path, xdg_user_dir
from ..runtime import ui_later
from ..theme import *  # noqa: F401,F403 — tokens
from ..theme import font as _font
from .. import theme as T
from ..widgets import (ActionRow, EntryRow, HeaderBar, PreferencesGroup,
                       RoundedButton, ScrollFrame, Switch, SwitchRow, toast,
                       tooltip, WindowControls)

THUMB = 44  # logical px — scaled at use time


class GameSettingsPage(tk.Frame):
    def __init__(self, window, game_name: str,
                 game_icon: str = None, banner: str = None):
        super().__init__(window.content, bg=WINDOW)
        self.window = window
        self.app = window.app
        self.game_name = game_name
        self.game_icon = game_icon or app_icon(self.app, game_name)
        self.banner = banner or app_banner(self.app, game_name)
        self._icon_refs: dict[str, tk.PhotoImage] = {}
        self._pending_name = None

        self._build_header()
        self._build_content()
        self.win = _PageWin(self)

        # legacy attribute aliases used elsewhere
        self.pages = {}
        self.buttons = {}

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

        self.title_label = self.header.set_title(f"{self.game_name} — Settings")

        self.header.pack_end(WindowControls(
            self.header, bg=WINDOW,
            on_minimize=self.window.frameless.minimize,
            on_maximize=self.window.frameless.maximize,
            on_close=self.window._on_window_close))
        self.save_button = RoundedButton(
            self.header, text=i18n._("SAVE"), variant="suggested", height=34,
            image=self._icon("save", 15, color="#FFFFFF"), compound="left",
            command=self._on_save)
        self.header.pack_end(self.save_button)

    # ----------------------------------------------------------------- content
    def _build_content(self):
        scroll = ScrollFrame(self, bg=WINDOW)
        scroll.pack(fill="both", expand=True)
        content = tk.Frame(scroll.inner, bg=WINDOW)
        content.pack(fill="x", padx=T.px(18), pady=(T.px(14), T.px(24)))
        self._content = content

        self._build_general(content)
        self._build_artwork(content)
        self._build_launch(content)
        self._build_fix(content)
        self._build_graphics(content)

    # ------------------------------------------------------------------ helpers
    def _icon(self, name: str, size: int = 16, color: str | None = None):
        key = (name, size, str(color))
        if key not in self._icon_refs:
            self._icon_refs[key] = icons.icon(name, size, color=color)
        return self._icon_refs[key]

    def _group(self, parent, title: str, description: str = ""):
        group = PreferencesGroup(parent, title=title, description=description)
        group.pack(fill="x", pady=(0, T.px(18)))
        return group

    _BUTTON_ICONS = {
        "Choose": ("folder", None),
        "Change": ("pencil", None),
        "Reset": ("reset", None),
        "Edit": ("pencil", None),
        "Install": ("download", "#FFFFFF"),
    }

    def _flat(self, parent, text, command, tone="normal", image=None):
        if image is None and text in self._BUTTON_ICONS:
            icon_name, icon_color = self._BUTTON_ICONS[text]
            image = self._icon(icon_name, 14, color=icon_color)
        kwargs = {}
        if image is not None:
            kwargs = {"image": image, "compound": "left"}
        return RoundedButton(parent, text=text, command=command, variant=tone,
                             height=30, padx=10, pady=3, font=T.FONT_SM,
                             radius=6, **kwargs)

    # ------------------------------------------------------------------ general
    def _build_general(self, content):
        group = self._group(content, "General")
        row = EntryRow(group.card, title=i18n._("GAMESETTINGS.GAMENAME.PROMPT"),
                       text=self.game_name, width=32)
        group.add(row)
        self.name_var = row.entry
        self.apply_name_button = self._flat(
            row.suffix_box, "", self._apply_game_name, tone="suggested",
            image=self._icon("check", 14, color="#FFFFFF"))
        self.apply_name_button.set_enabled(False)
        row.entry.bind("<KeyRelease>", self._name_changed)

    def _name_changed(self, *_args):
        value = self.name_var.get()
        self.apply_name_button.set_enabled(
            bool(value) and value != self.game_name)

    def _apply_game_name(self):
        old_name = self.game_name
        new_name = self.name_var.get().strip()
        if not new_name or new_name == old_name:
            return
        desktop = os.path.join(xdg_user_dir("DESKTOP"), f"{old_name}.desktop")
        menu_dir = os.path.join(os.path.expanduser("~"), ".local/share/applications")
        menu = os.path.join(menu_dir, f"{old_name}.desktop")
        has_desktop = os.path.isfile(desktop)
        has_menu = os.path.isfile(menu)
        if has_desktop:
            os.remove(desktop)
        if has_menu:
            os.remove(menu)

        settings = self.app.games.section(old_name)
        if self.app.games.has_section(new_name):
            dialogs.show_message(self.win, i18n._("MAINFORM.GAMEEXISTS"), "ERROR")
            return
        self.app.games.remove_section(old_name)
        self.app.games.put(settings, new_name)

        self.win.title(new_name)
        self.game_name = new_name
        self.name_var.delete(0, "end")
        self.name_var.insert(0, new_name)
        self._pending_name = new_name
        self.title_label.configure(text=f"{new_name} — Settings")

        main = self.app.main_form
        if main is not None:
            main.rename_game(old_name, new_name)

        icon = settings.get("icon")
        if has_desktop:
            path = os.path.join(xdg_user_dir("DESKTOP"), f"{new_name}.desktop")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(files_worker.generate_desktop_entry(new_name, icon))
            os.chmod(path, 0o755)
        if has_menu:
            with open(os.path.join(menu_dir, f"{new_name}.desktop"), "w",
                      encoding="utf-8") as fh:
                fh.write(files_worker.generate_desktop_entry(new_name, icon))
        self.apply_name_button.set_enabled(False)
        self._name_changed()

    # ------------------------------------------------------------------ artwork
    def _build_artwork(self, content):
        group = self._group(content, "Artwork")

        row = ActionRow(group.card, title="Icon")
        self.icon_label = tk.Label(row._box, bg=SURFACE,
                                   image=assets.photo(self.game_icon,
                                                      size=(T.px(THUMB), T.px(THUMB)),
                                                      stretch=False,
                                                      fallback="noImage.png"))
        self.icon_label.pack(side="left", pady=(4, 0))
        self._icon_img = self.icon_label.cget("image")
        row.add_suffix(self._flat(row.suffix_box, "Choose", self._edit_icon))
        group.add(row)

        row2 = ActionRow(group.card, title="Banner")
        self.banner_label = tk.Label(row2._box, bg=SURFACE,
                                     image=assets.photo(self.banner,
                                                        size=(T.px(76), T.px(THUMB)),
                                                        stretch=False,
                                                        fallback="noBanner.png"))
        self.banner_label.pack(side="left", pady=(4, 0))
        self._banner_img = self.banner_label.cget("image")
        row2.add_suffix(self._flat(row2.suffix_box, "Choose", self._banner_menu))
        group.add(row2)

    def _edit_icon(self):
        path = filedialog.askopenfilename(
            parent=self.win, title=i18n._("FILECHOOSER.IMG.TITLE"),
            filetypes=[(i18n._("FILECHOOSER.IMG.DESC"), "*.png *.jpg *.jpeg *.exe")])
        if not path:
            return
        try:
            if path.lower().endswith(".exe"):
                icon_path = fix_parser.parse_icon(path)
                if not icon_path or not os.path.isfile(icon_path):
                    raise IOError("File not found")
            else:
                icons_dir = os.path.join(os.path.expanduser("~"), ".config/OFME-Linux/icons")
                os.makedirs(icons_dir, exist_ok=True)
                icon_path = os.path.join(icons_dir, os.path.splitext(os.path.basename(path))[0])
                shutil.copy2(path, icon_path)
        except Exception as exc:
            dialogs.show_message(self.win, i18n._("MAINFORM.ICONPARSERERROR") % exc, "ERROR")
            return

        old_icon = self.app.games.get("icon", self.game_name)
        self.app.games.set("icon", icon_path, self.game_name)
        self.game_icon = icon_path
        img = assets.photo(icon_path, size=(T.px(THUMB), T.px(THUMB)), stretch=False,
                           fallback="noImage.png")
        self.icon_label.configure(image=img)
        self._icon_img = img

        main = self.app.main_form
        if main is not None:
            main.update_game_visuals(self.game_name)

        if old_icon and os.path.isfile(old_icon) and old_icon != icon_path:
            try:
                os.remove(old_icon)
            except OSError:
                pass

        for folder in (xdg_user_dir("DESKTOP"),
                       os.path.join(os.path.expanduser("~"), ".local/share/applications")):
            desktop = os.path.join(folder, f"{self.game_name}.desktop")
            if os.path.isfile(desktop) and old_icon:
                try:
                    with open(desktop, "r", encoding="utf-8") as fh:
                        file_content = fh.read()
                    with open(desktop, "w", encoding="utf-8") as fh:
                        fh.write(file_content.replace(old_icon, icon_path))
                except OSError:
                    pass

    def _banner_menu(self):
        menu = tk.Menu(self.win, tearoff=0)
        menu.add_command(label=i18n._("BANNEREDITOR.STEAM.HEADER"),
                         command=self._banner_from_steam)
        menu.add_command(label=i18n._("BANNEREDITOR.FILE.HEADER"),
                         command=self._banner_from_file)
        try:
            menu.tk_popup(self.win.winfo_pointerx(), self.win.winfo_pointery())
        finally:
            menu.grab_release()

    def _banner_from_steam(self):
        appid = dialogs.ask_string(self.win, i18n._("BANNEREDITOR.PROMPT"),
                                   self.app.games.get("steamID", self.game_name))
        if not appid:
            toast(self.win, i18n._("BANNEDEDITOR.STEAM.NOAPPID"), 3000)
            return

        def worker():
            banner = fix_parser.parse_banner(appid)
            if not os.path.isfile(str(banner)):
                ui_later(lambda: dialogs.show_message(self.win, str(banner), "ERROR"))
                return
            ui_later(lambda: self._set_banner(banner))

        threading.Thread(target=worker, daemon=True).start()

    def _banner_from_file(self):
        path = filedialog.askopenfilename(
            parent=self.win, title=i18n._("FILECHOOSER.IMG.TITLE"),
            filetypes=[(i18n._("FILECHOOSER.IMG.DESC"), "*.jpg *.jpeg *.png")])
        if path:
            self._set_banner(path)

    def _set_banner(self, path: str):
        try:
            from PIL import Image
            img = Image.open(path).convert("RGBA")
            banner_dir = os.path.join(os.path.expanduser("~"), ".config/OFME-Linux/banners")
            os.makedirs(banner_dir, exist_ok=True)
            current = self.app.games.get("banner", self.game_name)
            if current and os.path.isfile(current) and os.path.abspath(current) != os.path.abspath(path):
                try:
                    os.remove(current)
                except OSError:
                    pass
            dest = os.path.join(banner_dir, f"{self.game_name}.png")
            img.save(dest, "PNG")

            self.app.games.set("banner", dest, self.game_name)
            self.banner = dest
            image = assets.photo(dest, size=(T.px(76), T.px(THUMB)), stretch=False,
                                 fallback="noBanner.png")
            self.banner_label.configure(image=image)
            self._banner_img = image

            main = self.app.main_form
            if main is not None:
                main.update_game_visuals(self.game_name)
        except Exception as exc:
            dialogs.show_message(self.win, i18n._("BANNEREDITOR.FILE.FAILED") % exc, "ERROR")

    # ------------------------------------------------------------------ launch
    def _build_launch(self, content):
        group = self._group(content, "Launch")

        executable = self.app.games.get("executable", self.game_name) or ""
        exe_row = ActionRow(group.card, title="Executable", subtitle=executable)
        exe_row.add_suffix(self._flat(
            exe_row.suffix_box, "Choose", self._choose_executable))
        group.add(exe_row)
        self.exe_row = exe_row

        prefix_row = ActionRow(group.card, title=i18n._("GAMESETTINGS.PROTONS.PREFIXPATH"),
                               subtitle=self._prefix_path())
        self.prefix_row = prefix_row
        prefix_row.add_suffix(self._flat(prefix_row.suffix_box, "Reset",
                                         self._reset_prefix))
        prefix_row.add_suffix(self._flat(prefix_row.suffix_box, "Choose",
                                         self._choose_prefix))
        group.add(prefix_row)

        from ..widgets import ComboRow
        self.proton_row = ComboRow(group.card,
                                   title=i18n._("GAMESETTINGS.PROTONS.VERSION"),
                                   values=self._proton_values(), command=None)
        self.proton_row.combo.configure(width=24)
        self.proton_row.combo.bind("<<ComboboxSelected>>", self._proton_changed)
        group.add(self.proton_row)
        self.proton_var = self.proton_row.variable

    def _choose_executable(self):
        path = filedialog.askopenfilename(
            parent=self.win, title=i18n._("FILECHOOSER.EXE.TITLE"),
            filetypes=[(i18n._("FILECHOOSER.EXE.DESC"), "*.exe *.EXE")])
        if not path:
            return
        self.app.games.set("executable", path, self.game_name)
        self.exe_row.set_subtitle(path)

    def _proton_values(self):
        return (["GE-Proton Latest", i18n._("GAMESETTINGS.PROTONS.OTHER")]
                + files_worker.get_installed_protons())

    def _proton_changed(self, _event=None):
        if self.proton_var.get() == i18n._("GAMESETTINGS.PROTONS.OTHER"):
            current = self.app.games.get("proton", self.game_name)
            self.proton_var.set(current or "GE-Proton Latest")
            self.app.show_form("launcherSettings")
            self.proton_row.set_values(self._proton_values())
            self.proton_var.set(self.app.games.get("proton", self.game_name)
                                or "GE-Proton Latest")
            return
        self.app.games.set("proton", self.proton_var.get(), self.game_name)

    def _prefix_path(self) -> str:
        prefix = self.app.games.get("prefixPath", self.game_name)
        if prefix:
            return prefix
        executable = self.app.games.get("executable", self.game_name) or ""
        return os.path.join(os.path.dirname(executable), "OFME Prefix")

    def _choose_prefix(self):
        path = filedialog.askdirectory(parent=self.win)
        if not path:
            return
        if os.path.isdir(path) and os.listdir(path):
            dialogs.show_message(self.win, i18n._("NEWGAMECONFIG.PREFIX.PATHNONEMPTY"),
                                 "WARNING")
        old_prefix = self._prefix_path()
        try:
            old_files = os.listdir(old_prefix) if os.path.isdir(old_prefix) else []
        except OSError:
            old_files = []
        if old_files and dialogs.confirm(self.win, i18n._("GAMESETTINGS.PROTONS.PREFIXMOVE")):
            for item in old_files:
                src = os.path.join(old_prefix, item)
                dst = os.path.join(path, item)
                try:
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                        shutil.rmtree(src, ignore_errors=True)
                    else:
                        shutil.move(src, dst)
                except OSError:
                    pass
            shutil.rmtree(old_prefix, ignore_errors=True)
        self.app.games.set("prefixPath", path, self.game_name)
        self.prefix_row.set_subtitle(path)

    def _reset_prefix(self):
        self.app.games.set("prefixPath", "", self.game_name)
        self.prefix_row.set_subtitle(self._prefix_path())

    # ------------------------------------------------------------------ fix
    def _build_fix(self, content):
        group = self._group(content, "Multiplayer fix")

        overrides_row = EntryRow(group.card, title="DLL overrides",
                                 text=self.app.games.get("overrides", self.game_name) or "",
                                 width=28)
        group.add(overrides_row)
        self.overrides_entry = overrides_row.entry
        self.overrides_entry.bind(
            "<KeyRelease>", lambda _e: self._overrides_changed())

        env_row = ActionRow(group.card, title=i18n._("GAMESETTINGS.ENVS.ENVIRONMENT"),
                            subtitle=self._env_display())
        self.env_row = env_row
        env_row.add_suffix(self._flat(env_row.suffix_box, "Edit", self._open_env))
        group.add(env_row)

        args_before = EntryRow(group.card, title=i18n._("GAMESETTINGS.ENVS.ARGS.BEFORE"),
                               text=self.app.games.get("argsBefore", self.game_name) or "",
                               width=26)
        group.add(args_before)
        args_before.entry.bind(
            "<KeyRelease>", lambda _e: self.app.games.set(
                "argsBefore", args_before.entry.get(), self.game_name))

        args_after = EntryRow(group.card, title=i18n._("GAMESETTINGS.ENVS.ARGS.AFTER"),
                              text=self.app.games.get("argsAfter", self.game_name) or "",
                              width=26)
        group.add(args_after)
        args_after.entry.bind(
            "<KeyRelease>", lambda _e: self.app.games.set(
                "argsAfter", args_after.entry.get(), self.game_name))

        self.steam_overlay_row = SwitchRow(
            group.card, title=i18n._("GAMESETTINGS.ADDITIONALS.USESTEAMOVERLAY"),
            selected=self.app.games.get_bool("steamOverlay", self.game_name),
            command=lambda v: self.app.games.set("steamOverlay", v, self.game_name))
        group.add(self.steam_overlay_row)

        self.steam_runtime_row = SwitchRow(
            group.card, title=i18n._("GAMESETTINGS.ADDITIONALS.USESTEAMRUNTIME"),
            selected=self.app.games.get_bool("steamRuntime", self.game_name),
            command=self._toggle_steam_runtime)
        group.add(self.steam_runtime_row)

        self.no_steam_row = SwitchRow(
            group.card, title=i18n._("GAMESETTINGS.ADDITIONALS.USEFAKESTEAM"),
            selected=self._fake_steam_active(),
            command=self._toggle_fake_steam)
        group.add(self.no_steam_row)
        fix_path = self.app.games.get("fixPath", self.game_name)
        if not fix_path:
            self.no_steam_row.switch.set_enabled(False)

    def _env_display(self) -> str:
        env = self.app.games.get("environment", self.game_name) or ""
        return env.replace("====", "=").replace("\\\\\\\\", " ")

    def _open_env(self):
        self.window.open_env_page(self.game_name)

    def _overrides_changed(self, *_a):
        self.app.games.set("overrides", self.overrides_entry.get(), self.game_name)

    def _toggle_steam_runtime(self, selected: bool):
        if selected and not files_worker.find_steam_runtime(self.proton_var.get()):
            toast(self.win, i18n._("GAMESETTINGS.STEAM.NORUNTIME"))
            self.steam_runtime_row.set_active(False)
            return
        self.app.games.set("steamRuntime", selected, self.game_name)

    def _fix_steam_dlls(self):
        fix_path = self.app.games.get("fixPath", self.game_name)
        if not fix_path or not os.path.isdir(fix_path):
            return []
        return [os.path.join(fix_path, n) for n in os.listdir(fix_path)
                if n.lower() in ("steamfix32.dll", "steamfix64.dll")]

    def _fake_steam_active(self) -> bool:
        fix_path = self.app.games.get("fixPath", self.game_name)
        if not fix_path or not os.path.isdir(fix_path):
            return False
        return any(n.endswith(".noofllpath") for n in os.listdir(fix_path))

    def _toggle_fake_steam(self, selected: bool):
        dlls = self._fix_steam_dlls()
        if not dlls:
            dialogs.show_message(self.win, i18n._("GAMESETTINGS.FAKESTEAM.FAILED"))
            self.no_steam_row.set_active(False)
            return
        if selected:
            for dll in dlls:
                try:
                    backup = dll + ".noofllpath"
                    if not os.path.exists(backup):
                        os.replace(dll, backup)
                    src = assets.asset("ftpPath", "ftpPath32.dll" if dll.lower().endswith("32.dll")
                                       else "ftpPath64.dll")
                    shutil.copy2(src, dll)
                except OSError as exc:
                    runtime.log_error(str(exc))
        else:
            for dll in dlls:
                try:
                    if os.path.exists(dll):
                        os.remove(dll)
                    if os.path.exists(dll + ".noofllpath"):
                        os.replace(dll + ".noofllpath", dll)
                except OSError as exc:
                    runtime.log_error(str(exc))

    # ------------------------------------------------------------------ graphics
    def _build_graphics(self, content):
        group = self._group(content, "Graphics")

        self.wined3d_row = SwitchRow(
            group.card, title=i18n._("SETTINGSMODULE.USEWINED3D"),
            selected=self.app.games.get_bool("wined3d", self.game_name),
            command=lambda v: self.app.games.set("wined3d", v, self.game_name))
        group.add(self.wined3d_row)

        self.wayland_row = SwitchRow(
            group.card, title=i18n._("SETTINGSMODULE.NATIVEWAYLAND"),
            selected=self.app.games.get_bool("nativeWayland", self.game_name),
            command=lambda v: self.app.games.set("nativeWayland", v, self.game_name))
        group.add(self.wayland_row)

    # ------------------------------------------------------------------ save
    def _on_save(self):
        if self.name_var.get().strip() and \
                self.name_var.get().strip() != self.game_name:
            self._apply_game_name()
        toast(self.win, "Settings saved")
        self.window.show_library()

    # ------------------------------------------------------------------ misc
    def switch_page(self, page_name: str, button_id: str = None):
        """Legacy no-op — everything is one scrollable page now."""
        return

    def hide(self):
        self.window.show_library()

    def _icon_refs_clear(self):
        pass


def app_icon(app, game_name: str):
    return app.games.get("icon", game_name)


def app_banner(app, game_name: str):
    return app.games.get("banner", game_name)


class _PageWin:
    """Light shim so page code can use ``self.win`` like a Toplevel
    (title, transient dialogs parented to the real window)."""

    def __init__(self, page: "GameSettingsPage"):
        self._page = page

    def title(self, text: str = None):
        if text is not None:
            self._page.window.win.title(f"{text} — OnlineFix")
        return self._page.window.win.title()

    def winfo_pointerx(self):
        return self._page.window.win.winfo_pointerx()

    def winfo_pointery(self):
        return self._page.window.win.winfo_pointery()

    def wait_window(self, other):
        try:
            other.wait_window()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._page.window.win, name)


# Backwards-compatible class name used by core.show_form("gameSettings").
GameSettings = GameSettingsPage
