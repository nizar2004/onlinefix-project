"""Application container: modules, forms and global settings."""
from __future__ import annotations

import os
import threading
import urllib.request
from typing import Optional

from . import i18n, runtime
from .assets import BASE_DIR
from .files_worker import banners_dir, default_share_dir, icons_dir
from .runtime import GLOBALS, log_error, log_info
from .storage import IniStorage


class Application:
    def __init__(self, root, argv: Optional[list[str]] = None):
        self.root = root
        self.argv = argv or []
        self.forms: dict[str, object] = {}
        self.main_form = None
        self.visible = False

        home = os.path.expanduser("~")
        config = os.path.join(home, ".config", "OFME-Linux")
        os.makedirs(config, exist_ok=True)
        self.games = IniStorage(os.path.join(config, "Games.ini"))
        self.launcher = IniStorage(os.path.join(config, "Launcher.ini"))
        self.launcher.ensure_section("User Settings")

        language = self.launcher.get("language", "User Settings")
        i18n.init(language)

        self.launcher_settings = LauncherSettingsHelper(self)

    # ------------------------------------------------------------------ forms
    def show_form(self, name: str, new: bool = False, **kwargs):
        from .forms.main_form import MainForm
        from .forms.new_game_configurator import NewGameConfigurator
        from .forms.game_remover import GameRemover
        from .forms.proton_downloader import ProtonDownloader
        from .forms.game_starting import GameStarting

        constructors = {
            "MainForm": MainForm,
            "newGameConfigurator": NewGameConfigurator,
            "gameRemover": GameRemover,
            "protonDownloader": ProtonDownloader,
            "gameStarting": GameStarting,
        }

        if name == "MainForm":
            if self.main_form is None:
                self.main_form = MainForm(self)
                self.forms["MainForm"] = self.main_form
            return self.main_form

        existing = self.forms.get(name)
        if not new and existing is not None and _alive(existing):
            existing.show()
            return existing

        # In-window pages hosted by the main form.
        if self.main_form is None and name in (
                "gameSettings", "downloads", "log", "envViewer",
                "launcherSettings"):
            return None
        if name == "gameSettings":
            return self.main_form.open_game_settings(
                kwargs.get("game_name"),
                game_icon=kwargs.get("game_icon"),
                banner=kwargs.get("banner"))
        if name == "downloads":
            self.main_form.open_downloads()
            return self.main_form.downloads_page
        if name == "log":
            game = kwargs.get("game_name") or self.main_form.current_game
            if game:
                self.main_form.log_page.set_game(game)
            self.main_form.log_page.show()
            return self.main_form.log_page
        if name == "envViewer":
            return self.main_form.open_env_page(
                kwargs.get("game_name"),
                on_back=kwargs.get("on_back"))
        if name == "launcherSettings":
            self.main_form.settings_page.show()
            return self.main_form.settings_page

        cls = constructors.get(name)
        if cls is None:
            raise KeyError(f"Unknown form: {name}")
        form = cls(self, **kwargs)
        self.forms[name] = form
        return form

    def ensure_form(self, name: str, **kwargs):
        form = self.forms.get(name)
        if form is not None and _alive(form):
            return form
        return self.show_form(name, **kwargs)

    def open_proton_downloader(self, name: str, url: Optional[str], modal: bool = False):
        form = self.show_form("protonDownloader", new=True)
        form.start_download(name, url)
        if modal:
            runtime.ui_call(form.wait_until_closed)
        return form

    def shutdown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    # ----------------------------------------------------------------- proton
    def fetch_latest_proton(self):
        GLOBALS["LatestProton"] = "fetching"
        releases = self._fetch_releases_safe()
        if releases:
            first = next(iter(releases.values()))
            GLOBALS["LatestProton"] = first["url"]
            log_info(f"Fetched latest GE-Proton download URL! {first['url']}")
        else:
            GLOBALS["LatestProton"] = None
            log_error("Failed to fetch latest proton version")

    def _fetch_releases_safe(self):
        from .files_worker import fetch_proton_releases
        try:
            return fetch_proton_releases()
        except Exception as exc:
            log_error(str(exc))
            return {}

    def check_updates(self):
        jar = os.path.join(os.getcwd(), "ofmeupd.jar")
        if not os.path.isfile(jar):
            return
        url = "https://zzedovec.github.io/resources/ofmelauncher/currentversion"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "OnlineFix-Linux-Launcher"})
            with urllib.request.urlopen(request, timeout=5) as response:
                latest = response.read().decode("utf-8", "replace").strip()
        except Exception as exc:
            log_error(f"Failed to fetch latest launcher version - {exc}")
            return
        if latest and latest != GLOBALS.get("version"):
            java = os.path.join(os.getcwd(), "jre", "bin", "java")
            if not os.path.isfile(java):
                java = "java"
            import subprocess
            try:
                subprocess.Popen([java, "-jar", "ofmeupd.jar"], cwd=os.getcwd())
            except Exception as exc:
                log_error(f"Failed to start updater - {exc}")
                return
            runtime.ui_later(self.shutdown)


class LauncherSettingsHelper:
    """Implements launcherSettings::getBasePathFor and setWithDirChooser."""

    def __init__(self, app: Application):
        self.app = app

    def get_base_path_for(self, for_what: str) -> str:
        default_dir = os.path.join(default_share_dir(), for_what)
        user_dir = self.app.launcher.get(f"{for_what}Path", "User Settings")
        if not user_dir:
            os.makedirs(default_dir, exist_ok=True)
            return default_dir
        return user_dir

    def set_with_dir_chooser(self, param: str, sender_var=None, for_section=("launcher",)):
        from tkinter import filedialog
        path = filedialog.askdirectory(parent=self.app.root, title="Select directory")
        if not path:
            return False
        if sender_var is not None:
            sender_var.set(path)
        if for_section[0] == "launcher":
            self.app.launcher.set(param, path, "User Settings")
        else:
            self.app.games.set(param, path, for_section[1])
        return True


def _alive(form) -> bool:
    try:
        return bool(form.win.winfo_exists())
    except Exception:
        return False
