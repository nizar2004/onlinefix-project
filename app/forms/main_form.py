"""OnlineFix main window — mirrors the reference shell.

A fixed sidebar (brand header, Library / Downloads / Runners / Settings
navigation, version) over a content area with stacked in-window pages:
Library (search + portrait card grid + empty state), game Detail, game
Settings, Downloads and Runners. Clicking a card opens the detail page.

The window is frameless: the header bars are the title bars, dragging
one moves the window, the round buttons minimise / maximise / close it.
"""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

from .. import assets, dialogs, files_worker, i18n, icons, runtime
from ..frameless import FramelessWindow
from ..game_card import GameTile, GameTileGrid
from ..process_util import open_path
from ..runtime import ui_later
from ..theme import *  # noqa: F401,F403 — tokens
from ..theme import font as _font
from .. import theme as T
from ..widgets import (HeaderBar, NavRow, RoundedButton, SearchEntry,
                       StatusPage, WindowControls, make_draggable, tooltip,
                       toast)

SIDEBAR_W = 240  # logical px — scaled at build time
GRID_COVER = (T.COVER_W, T.COVER_H)


class _StubText:
    """Adapter so the configurator can drive stub labels via
    ``set_name`` / ``set_status`` / ``set_text``."""

    def __init__(self, label: tk.Label):
        self._label = label

    def set_name(self, text: str):
        self._label.configure(text=text)

    def set_status(self, text: str):
        self._label.configure(text=text)

    def set_text(self, text: str):
        self._label.configure(text=text)


class MainForm:
    def __init__(self, app):
        self.app = app
        self.win = app.root
        self.win.title("OnlineFix Launcher")
        self.win.configure(bg=WINDOW)
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        default_w = min(T.px(1040), screen_w - T.px(24))
        default_h = min(T.px(660), screen_h - T.px(24))
        self.win.geometry(f"{default_w}x{default_h}")
        self.win.minsize(min(T.px(720), screen_w - T.px(24)),
                         min(T.px(480), screen_h - T.px(24)))
        self.current_game: Optional[str] = None
        self.running_game: Optional[str] = None
        self.visible = True
        self.play_state = "play"
        self._cards: dict[str, tk.Frame] = {}
        self._icon_refs: dict[str, tk.PhotoImage] = {}
        self._set_icon()

        self.frameless = FramelessWindow(self.win)
        self._center_window()

        self._build()
        self._load_games()
        if self.app.launcher.get_bool("fullscreen", "User Settings", False):
            self.frameless.maximize()

    def _set_icon(self):
        try:
            icon = icons.logo(64)
            self.win.iconphoto(True, icon)
            self._window_icon = icon
        except Exception:
            pass

    def _center_window(self):
        """Frameless windows are not placed by the WM — centre it instead."""
        try:
            self.win.update_idletasks()
            sw = self.win.winfo_screenwidth()
            sh = self.win.winfo_screenheight()
            w = self.win.winfo_width() or 1040
            h = self.win.winfo_height() or 660
            self.win.geometry(f"+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2)}")
        except Exception:
            pass

    def _icon(self, name: str, size: int = 16, color: str | None = None):
        key = (name, size, str(color))
        if key not in self._icon_refs:
            self._icon_refs[key] = icons.icon(name, size, color=color)
        return self._icon_refs[key]

    # ------------------------------------------------------------------ shell
    def _build(self):
        self._build_sidebar()

        self.content = tk.Frame(self.win, bg=WINDOW,
                                highlightthickness=1,
                                highlightbackground=SIDEBAR_LINE)
        self.content.pack(side="left", fill="both", expand=True)

        # --- pages -----------------------------------------------------------
        self._build_library_page()
        self._build_downloads_page()

        from .game_detail import GameDetailPage
        self.detail_page = GameDetailPage(self)

        from .runners_page import RunnersPage
        self.runners_page = RunnersPage(self)

        from .log_form import LogPage
        self.log_page = LogPage(self)

        from .launcher_settings import LauncherSettingsPage
        self.settings_page = LauncherSettingsPage(self)

        self.game_settings_page = None  # created on demand
        self.env_page = None

        self._page = "library"
        self._show_library_page()

        # keyboard shortcuts (like the reference)
        self.win.bind("<Control-f>", lambda _e: self.search.focus())
        self.win.bind("<Control-o>", lambda _e: self._add_game())
        self.win.bind("<Escape>", self._on_escape)

    def _on_escape(self, _e=None):
        if self._page != "library":
            self.show_library()

    # ---------------------------------------------------------------- sidebar
    def _build_sidebar(self):
        rail = tk.Frame(self.win, bg=SIDEBAR, width=T.px(SIDEBAR_W))
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        tk.Frame(rail, bg=SIDEBAR_LINE, width=T.px(1)).pack(side="right", fill="y")

        # brand header ---------------------------------------------------------
        brand = tk.Frame(rail, bg=SIDEBAR, height=T.HEADER_H)
        brand.pack(fill="x")
        brand.pack_propagate(False)
        try:
            logo = icons.logo(24)
            lbl = tk.Label(brand, image=logo, bg=SIDEBAR)
            lbl.image = logo
            lbl.pack(side="left", padx=(T.px(12), T.px(8)), pady=T.px(11))
        except Exception:
            pass
        tk.Label(brand, text="OnlineFix Launcher", bg=SIDEBAR, fg=T.FG,
                 font=T.FONT_TITLE, anchor="w").pack(side="left")
        make_draggable(brand)

        # nav ------------------------------------------------------------------
        self.nav_items: dict[str, NavRow] = {}
        nav = tk.Frame(rail, bg=SIDEBAR)
        nav.pack(fill="x", padx=T.px(6), pady=(T.px(6), 0))
        for key, label, icon_name in (
            ("library", "Library", "library"),
            ("downloads", "Downloads", "download"),
            ("runners", "Runners", "monitor"),
            ("settings", "Settings", "settings"),
        ):
            row = NavRow(nav, label, icon_name, command=lambda k=key: self._nav(k))
            row.pack(fill="x", padx=T.px(10), pady=T.px(1))
            self.nav_items[key] = row
        self._paint_nav("library")

        # bottom ---------------------------------------------------------------
        bottom = tk.Frame(rail, bg=SIDEBAR)
        bottom.pack(side="bottom", fill="x", padx=T.px(20), pady=(0, T.px(10)))
        tk.Label(bottom, text=f"v{runtime.GLOBALS.get('version', '2.7.1')}",
                 bg=SIDEBAR, fg=DIM, font=T.FONT_TINY,
                 anchor="w").pack(anchor="w")

    def _paint_nav(self, key: str):
        for k, row in self.nav_items.items():
            row.set_selected(k == key)

    def _nav(self, key: str):
        if key == "library":
            self.show_library()
        elif key == "downloads":
            self.open_downloads()
        elif key == "runners":
            self.open_runners()
        elif key == "settings":
            self.open_settings()

    # ------------------------------------------------------------------ pages
    def _build_library_page(self):
        self.library_page = tk.Frame(self.content, bg=WINDOW)

        # --- header strip ------------------------------------------------------
        self.library_header = HeaderBar(self.library_page, draggable=True)
        self.library_header.pack(fill="x")

        self.add_button = RoundedButton(
            self.library_header, text="Add Game", command=self._add_game,
            variant="suggested", height=34,
            image=self._icon("plus", 15, color="#FFFFFF"), compound="left")
        self.library_header.pack_start(self.add_button, padx=(T.px(8), 0))

        self.search = SearchEntry(self.library_header,
                                  placeholder="Search your library…",
                                  command=self._filter_games)
        self.library_header.set_title_widget(self.search)
        self.search.entry.bind("<Return>", self._open_first_match)

        self.stop_button = RoundedButton(
            self.library_header, text="Stop", variant="destructive", height=34,
            image=self._icon("stop", 15), compound="left",
            command=self.stop_running_game)
        self.library_header.pack_end(self.stop_button)
        self.stop_button.pack_forget()

        self.library_header.pack_end(WindowControls(
            self.library_header, bg=WINDOW,
            on_minimize=self.frameless.minimize,
            on_maximize=self.frameless.maximize,
            on_close=self._on_window_close))
        self._tooltip_window_controls()

        # --- body: grid or empty state ----------------------------------------
        self.library_body = tk.Frame(self.library_page, bg=WINDOW)
        self.library_body.pack(fill="both", expand=True)

        self.grid_holder = tk.Frame(self.library_body, bg=WINDOW)
        self.scroll = _SmoothScroll(self.grid_holder)
        self.scroll.pack(fill="both", expand=True)
        self.grid = GameTileGrid(self.scroll.inner)
        self.grid.pack(fill="both", expand=True, padx=T.px(24), pady=(T.px(18), T.px(24)))

        # --- empty state ------------------------------------------------------
        self.empty_box = StatusPage(
            self.library_body, title="Your library is empty",
            description="Add games you own to your library to organize them\n"
                        "and manage their settings.",
            paintable=icons.logo(96))
        self._empty_plus = self._icon("plus", 17, color="#FFFFFF")
        self.empty_button = RoundedButton(
            self.empty_box.child, text="Add a Game", variant="suggested",
            height=42, radius=999, padx=26, font=T.FONT_PLAY,
            image=self._empty_plus, compound="left",
            command=self._add_game)
        self.empty_button.pack()

    def _tooltip_window_controls(self):
        """KDE-style tooltips for the round window buttons."""
        controls = [w for w in self.library_header.winfo_children()
                    if isinstance(w, WindowControls)]
        if not controls:
            return
        for btn, label in zip(controls[0].winfo_children(),
                              ("Minimise", "Maximise", "Close")):
            tooltip(btn, label)

    def _on_window_close(self):
        try:
            if self.app.main_form is not None:
                self.app.main_form.close()
        finally:
            try:
                os.remove("/tmp/ofllpid")
            except OSError:
                pass
            self.win.destroy()

    def _show_library_page(self):
        for page in self._iter_pages():
            page.pack_forget()
        self.library_page.pack(fill="both", expand=True)
        self._page = "library"
        self._paint_nav("library")
        self._filter_games()

    def _iter_pages(self):
        pages = [self.library_page, self.downloads_page, self.detail_page,
                 self.runners_page, self.log_page, self.settings_page]
        if self.env_page is not None:
            pages.append(self.env_page)
        if self.game_settings_page is not None:
            pages.append(self.game_settings_page)
        return pages

    def show_library(self):
        self._show_library_page()

    def open_detail(self, name: str):
        self.current_game = name
        self.detail_page.show(name)
        for page in self._iter_pages():
            page.pack_forget()
        self.detail_page.pack(fill="both", expand=True)
        self._page = "detail"
        self._paint_nav("library")

    def open_game_settings(self, name: str, game_icon=None, banner=None):
        from .game_settings import GameSettingsPage
        # recreate the page fresh for the selected game
        if self.game_settings_page is not None:
            try:
                self.game_settings_page.destroy()
            except Exception:
                pass
        self.game_settings_page = GameSettingsPage(
            self, name,
            game_icon=game_icon or self.app.games.get("icon", name),
            banner=banner or self.app.games.get("banner", name))
        for page in self._iter_pages():
            page.pack_forget()
        self.game_settings_page.pack(fill="both", expand=True)
        self._page = "game-settings"
        self._paint_nav("library")
        return self.game_settings_page

    def open_downloads(self):
        if getattr(self.downloads_page, "_shelf_visible", False):
            self.downloads_page.refresh_shelf()
        for page in self._iter_pages():
            page.pack_forget()
        self.downloads_page.pack(fill="both", expand=True)
        self._page = "downloads"
        self._paint_nav("downloads")

    def open_runners(self):
        self.runners_page.refresh()
        for page in self._iter_pages():
            page.pack_forget()
        self.runners_page.pack(fill="both", expand=True)
        self._page = "runners"
        self._paint_nav("runners")

    # ------------------------------------------------------------------ games
    def _build_downloads_page(self):
        from .downloads_page import DownloadsPage
        self.downloads_page = DownloadsPage(self)

    def _load_games(self):
        for name in self.app.games.sections():
            self.add_game(name)
        self._filter_games()

    def add_game(self, name: str, executable=None, overrides=None,
                 banner=None, icon=None, reflow=True):
        if name in self._cards:
            return self._cards[name]

        banner_path = banner or self.app.games.get("banner", name)
        try:
            cover = assets.cover_photo(banner_path, GRID_COVER, radius=T.px(10),
                                       fallback="noBanner.png")
        except Exception:
            cover = None

        icon_path = icon or self.app.games.get("icon", name)
        tile = GameTile(
            self.grid, title=name, cover=cover, game_icon=icon_path,
            on_activate=lambda n=name: self.open_detail(n),
        )
        self._cards[name] = tile
        self.grid.add(tile)
        self._filter_games()
        return tile

    def update_game_visuals(self, name: str):
        """Refresh a tile's cover + icon badge after artwork changes."""
        tile = self._cards.get(name)
        if tile is None:
            return
        banner_path = self.app.games.get("banner", name)
        try:
            cover = assets.cover_photo(banner_path, GRID_COVER, radius=T.px(10),
                                       fallback="noBanner.png")
        except Exception:
            cover = None
        tile.set_cover(cover)
        tile.set_icon(self.app.games.get("icon", name))

    def rename_game(self, old: str, new: str):
        tile = self._cards.pop(old, None)
        if tile is None:
            return
        self._cards[new] = tile
        tile._title = new
        tile._caption.configure(text=tile._ellipsize(new))
        if self.current_game == old:
            self.current_game = new
        self._filter_games()

    def remove_game(self, name: str):
        tile = self._cards.pop(name, None)
        if tile is not None:
            self.grid.remove(tile)
            tile.destroy()
        if self.current_game == name:
            self.current_game = None
        self._filter_games()

    def _relayout(self):
        self.grid.reflow()
        self._filter_games()

    def _filter_games(self, _event=None):
        if not hasattr(self, "search"):
            return
        query = self.search.get().lower().strip()
        visible: list[GameTile] = []
        for name, tile in self._cards.items():
            if query in name.lower():
                visible.append(tile)
            elif tile.winfo_manager():
                tile.grid_remove()
        # re-flow the visible tiles so no gaps are left behind
        for index, tile in enumerate(visible):
            row, col = divmod(index, self.grid._columns)
            tile.grid(row=row, column=col,
                      padx=(0, self.grid.COL_GAP), pady=(0, self.grid.ROW_GAP),
                      sticky="nw")
        total = len(self._cards)
        if not visible:
            if total == 0:
                self.empty_box.set_title("Your library is empty")
                self.empty_box.set_description(
                    "Add games you own to your library to organize them\n"
                    "and manage their settings.")
                self.empty_button.set_text("Add a Game")
                self.empty_button.set_command(self._add_game)
            else:
                self.empty_box.set_title("No games found")
                self.empty_box.set_description(
                    "Try a different search term or clear your search.")
                self.empty_button.set_text("Clear Search")
                self.empty_button.set_command(self._clear_search)
            self._show_empty()
        else:
            self._hide_empty()

    def _show_empty(self):
        try:
            self.grid_holder.pack_forget()
        except Exception:
            pass
        self.empty_box.pack(fill="both", expand=True)

    def _hide_empty(self):
        try:
            self.empty_box.pack_forget()
        except Exception:
            pass
        self.grid_holder.pack(fill="both", expand=True)

    def _clear_search(self):
        self.search.set("")
        self._filter_games()

    def _open_first_match(self, _e=None):
        """Enter in the search opens the first matching game."""
        for name, tile in self._cards.items():
            if tile.winfo_manager():
                self.open_detail(name)
                return True
        return False

    # ------------------------------------------------------------------ compat
    def show_game_menu(self, name: str):
        """Legacy entry point — now opens the detail page."""
        self.open_detail(name)

    def hide_game_menu(self):
        """Legacy entry point — now returns to the library."""
        self.show_library()

    def _quick_play(self, name: str):
        self.run_game(name)

    def _game_menu(self, name: str):
        menu = tk.Menu(self.win, tearoff=0)
        menu.add_command(label="Game settings",
                         command=lambda: self.open_game_settings(name))
        menu.add_command(label="Open folder",
                         command=lambda: self._open_game_folder(name))
        menu.add_command(label="Remove",
                         command=lambda: self._delete_game(name))
        menu.tk_popup(self.win.winfo_pointerx(), self.win.winfo_pointery())

    # ------------------------------------------------------------------ launch
    def launch_game(self, game_name: str, debug: bool = False):
        try:
            self.run_game(game_name, debug=debug)
            self._toast(f"Launching {game_name}{' (debug)' if debug else ''}")
        except Exception as exc:
            self._toast(str(exc))
            return
        self.running_game = game_name
        self.log_page.set_game(game_name)
        self.log_page.show()
        if self._page == "detail" and self.current_game == game_name:
            self.detail_page.refresh_state()

    def stop_running_game(self):
        process = runtime.GLOBALS.get("currentGameProcess")
        name = runtime.GLOBALS.get("currentGameName")
        if process is None:
            self._toast("No game is running")
            return
        try:
            process.terminate()
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        self._toast(f"Stopping {name or 'game'}…")

    def run_game(self, game_name: str, debug: bool = False):
        def worker():
            spec = files_worker.generate_process(game_name, debug)
            if spec is None:
                return
            ui_later(lambda: setattr(self, "play_state", "stop"))
            ui_later(lambda: setattr(self, "running_game", game_name))
            ui_later(self._show_stop_button)
            files_worker.run(spec, game_name, debug)
            ui_later(lambda: self._on_game_exit(game_name))
            runtime.log_info(f"{game_name} fully terminated")
        threading.Thread(target=worker, daemon=True).start()

    def _show_stop_button(self):
        try:
            self.stop_button.pack(side="right", padx=(0, T.px(8)))
        except Exception:
            pass
        self._set_tile_running(True)

    def _set_tile_running(self, running: bool):
        name = self.running_game
        tile = self._cards.get(name or "")
        if tile is not None and hasattr(tile, "set_running"):
            tile.set_running(running)

    def _on_game_exit(self, game_name: str):
        self.play_state = "play"
        self.running_game = None
        try:
            self.stop_button.pack_forget()
        except Exception:
            pass
        code = runtime.GLOBALS.get("lastExitCode", "?")
        self._toast(f"{game_name} exited ({code})")
        self._set_tile_running(False)
        if self._page == "detail" and self.current_game == game_name:
            self.detail_page.refresh_state()

    def switch_play_button(self, status: str):
        self.play_state = status

    # ------------------------------------------------------------------ misc
    def _game_settings(self, name: str):
        self.open_game_settings(name)

    def _delete_game(self, name: str):
        self.app.show_form("gameRemover", game_name=name)

    def _open_game_folder(self, name: str):
        path = self.app.games.get("mainPath", name)
        if not path:
            executable = self.app.games.get("executable", name) or ""
            path = os.path.dirname(executable)
        open_path(path)

    def _show_library(self):
        self.show_library()

    def _show_no_games(self, show: bool = True):
        self._filter_games()

    def _reflow(self):
        self._relayout()

    def open_settings(self):
        self.settings_page.show()

    def open_log(self):
        if self.current_game and not self.log_page.game_name:
            self.log_page.set_game(self.current_game)
        self.log_page.show()

    def open_env_page(self, game_name: str, on_back=None):
        from .env_viewer import EnvPage
        try:
            if self.env_page is not None:
                self.env_page.destroy()
        except Exception:
            pass
        self.env_page = EnvPage(self, game_name,
                                on_back=lambda: self.open_game_settings(game_name))
        self.env_page.show()
        return self.env_page

    def _settings(self):
        self.open_settings()

    def _add_game(self):
        self.app.show_form("newGameConfigurator", new=True)

    def _toast(self, message: str):
        toast(self.win, message)

    def add_stub_game(self, name: str = "", status: str = ""):
        """Skeleton tile shown while a game is being added."""
        from ..widgets import StubCard
        stub = StubCard(self.grid, name=name or "Adding game",
                        status=status or "Please wait")
        self.grid.add(stub)
        self._cards[name or ""] = stub
        self._filter_games()
        return {"box": stub,
                "name": _StubText(stub._name_lbl),
                "status": _StubText(stub._status_lbl)}

    def remove_stub_game(self, box):
        try:
            box.destroy()
        except Exception:
            pass
        self.grid.remove(box)
        for name, card in list(self._cards.items()):
            if card is box:
                del self._cards[name]
        self._filter_games()

    def close(self):
        try:
            os.remove("/tmp/ofllpid")
        except OSError:
            pass

    def show(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        self.visible = True


class _SmoothScroll(tk.Frame):
    """A vertical scrollable container with themed scrollbar + wheel."""

    def __init__(self, master, bg=None, **kwargs):
        super().__init__(master, bg=bg or WINDOW, **kwargs)
        self.canvas = tk.Canvas(self, bg=bg or WINDOW,
                                highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical",
                                       command=self.canvas.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.inner = tk.Frame(self.canvas, bg=bg or WINDOW)
        self.window = self.canvas.create_window((0, 0), window=self.inner,
                                                anchor="nw")
        self.inner.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.bind("<Enter>", self._bind_wheel)
        self.bind("<Leave>", self._unbind_wheel)

    # X11 delivers wheel turns as Button-4/5; Windows/macOS as MouseWheel.
    def _bind_wheel(self, _e=None):
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.bind_all("<Button-4>", self._on_wheel, add="+")
        self.bind_all("<Button-5>", self._on_wheel, add="+")

    def _unbind_wheel(self, _e=None):
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")

    def _on_wheel(self, event):
        try:
            step = T.px(60)
            if getattr(event, "num", None) == 4:
                self.canvas.yview_scroll(-step, "pixels")
            elif getattr(event, "num", None) == 5:
                self.canvas.yview_scroll(step, "pixels")
            else:
                delta = getattr(event, "delta", 0) or 0
                if delta:
                    self.canvas.yview_scroll(int(-delta / 120) * step,
                                             "pixels")
        except (tk.TclError, ValueError, TypeError):
            pass

    def _on_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
