"""Headless backend for the web UI.

Duck-types enough of :class:`app.core.Application` for
:mod:`app.files_worker` to generate and run game processes without a
Tk main loop.  ``runtime.set_root()`` is intentionally never called, so
``runtime.ui_call`` executes callbacks directly on the calling thread.

It also implements the web-native equivalents of the project's classic
forms: add-game (folder scan), game settings (all Games.ini keys),
rename/remove, environment editor, artwork upload, desktop shortcuts,
Proton management (list / latest / download with progress) and launcher
settings — all through the same storage the tkinter UI uses.
"""
from __future__ import annotations

import base64
import os
import shutil
import threading
import time
import urllib.request
from typing import Any, Optional

from . import i18n
from .files_worker import (banners_dir, default_share_dir, find_steam_runtime,
                           generate_desktop_entry, generate_process,
                           get_installed_protons, get_proton_executable,
                           icons_dir, run as run_spec, scan_dir)
from .runtime import GLOBALS, log_error, log_info, set_app
from .storage import IniStorage

# Games.ini value format (same as the classic forms)
ENV_SEPARATOR = "\\" * 4
ENV_KEY_SEPARATOR = "===="

GAME_TEXT_KEYS = (
    "executable", "mainPath", "prefixPath", "proton", "overrides",
    "argsBefore", "argsAfter", "fixPath", "fakeSteamID", "steamID",
    "banner", "icon", "notes",
)
GAME_BOOL_KEYS = (
    "steamOverlay", "wined3d", "nativeWayland", "noBanner",
)


def config_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".config", "OFME-Linux")


def parse_environment(raw: Optional[str]) -> dict[str, str]:
    """Same rules as env_viewer.parse_environment_array (no Tk import)."""
    if not raw:
        return {}
    parsed: dict[str, str] = {}
    entries = [e for e in __import__("re").split(r"\\{2,}", raw) if e]
    if len(entries) == 1:
        parts = raw.split(ENV_KEY_SEPARATOR)
        if len(parts) >= 2:
            parsed[parts[0]] = parts[1]
        return parsed
    for entry in entries:
        parts = entry.split(ENV_KEY_SEPARATOR)
        if len(parts) < 2:
            continue
        parsed[parts[0]] = parts[1]
    return parsed


def serialize_environment(env: dict[str, str]) -> str:
    """Join KEY====value pairs with four backslashes (new format)."""
    return ENV_SEPARATOR.join(f"{k}{ENV_KEY_SEPARATOR}{v}"
                              for k, v in env.items() if k)


class WebApp:
    """Headless application core (no Tk)."""

    def __init__(self):
        config = config_dir()
        os.makedirs(config, exist_ok=True)
        self.root = None                 # no Tk in web mode
        self.main_form = None            # files_worker tolerates None
        self.forms: dict[str, Any] = {}  # classic log/debug windows
        self.games = IniStorage(os.path.join(config, "Games.ini"))
        self.launcher = IniStorage(os.path.join(config, "Launcher.ini"))
        self.launcher.ensure_section("User Settings")
        i18n.init(self.launcher.get("language", "User Settings"))

        from .core import LauncherSettingsHelper
        self.launcher_settings = LauncherSettingsHelper(self)

        # files_worker reaches for the active application through runtime
        set_app(self)

        self._launch_lock = threading.Lock()
        self._cancel_launch = threading.Event()
        self._dl: dict[str, Any] = {"name": None, "fraction": 0.0,
                                    "bytes": 0, "total": 0, "done": False,
                                    "error": None, "cancel": threading.Event()}

    # ------------------------------------------------------------------ games
    def list_games(self) -> list[dict[str, Any]]:
        """Every game section as a UI-friendly dict."""
        out: list[dict[str, Any]] = []
        for name in self.games.sections():
            if not name:
                continue
            executable = self.games.get("executable", name) or ""
            banner = self._resolve_art(banners_dir(), self.games.get("banner", name), name)
            icon = self._resolve_art(icons_dir(), self.games.get("icon", name), name)
            spent = self.games.get_int("timeSpent", name, 0)
            out.append({
                "name": name,
                "executable": executable,
                "hasExecutable": bool(executable and os.path.isfile(executable)),
                "proton": self.games.get("proton", name) or "",
                "banner": banner,
                "icon": icon,
                "timeSpent": spent,
                "running": GLOBALS.get("currentGameName") == name,
            })
        return out

    @staticmethod
    def _resolve_art(folder: str, stored: Optional[str], name: str) -> str:
        """Return an existing art file path (ini value or banner/icon dir)."""
        candidates: list[str] = []
        if stored:
            candidates.append(stored)
            candidates.append(os.path.join(folder, os.path.basename(stored)))
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            candidates.append(os.path.join(folder, name + ext))
        for path in candidates:
            if path and os.path.isfile(path):
                return path
        return ""

    def get_game(self, name: str) -> dict[str, Any]:
        """Full settings of one game (what the classic form edits)."""
        if not self.games.has_section(name):
            return {}
        data: dict[str, Any] = {"name": name}
        for key in GAME_TEXT_KEYS:
            data[key] = self.games.get(key, name) or ""
        for key in GAME_BOOL_KEYS:
            data[key] = self.games.get_bool(key, name, False)
        data["environment"] = parse_environment(
            self.games.get("environment", name))
        data["timeSpent"] = self.games.get_int("timeSpent", name, 0)
        data["banner"] = self._resolve_art(
            banners_dir(), self.games.get("banner", name), name)
        data["icon"] = self._resolve_art(
            icons_dir(), self.games.get("icon", name), name)
        return data

    def set_game(self, name: str, data: dict[str, Any],
                 new_name: Optional[str] = None) -> dict[str, Any]:
        if not self.games.has_section(name):
            return {"ok": False, "error": "game not found"}
        for key in GAME_TEXT_KEYS:
            if key in data:
                self.games.set(key, data[key], name)
        for key in GAME_BOOL_KEYS:
            if key in data:
                self.games.set(key, bool(data[key]), name)
        if "environment" in data and isinstance(data["environment"], dict):
            self.games.set("environment",
                           serialize_environment(data["environment"]),
                           name)
        if new_name and new_name != name:
            if self.games.has_section(new_name):
                return {"ok": False, "error": "name already taken"}
            section = self.games.section(name)
            self.games.remove_section(name)
            self.games.put(section, new_name)
        return {"ok": True, "name": new_name or name}

    def remove_game(self, name: str) -> dict[str, Any]:
        if not self.games.has_section(name):
            return {"ok": False, "error": "game not found"}
        for key in ("banner", "icon"):
            path = self.games.get(key, name)
            if path and os.path.isfile(path):
                if os.path.dirname(path) in (banners_dir(), icons_dir()):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
        self.games.remove_section(name)
        return {"ok": True}

    # ------------------------------------------------------------- add a game
    def default_proton(self) -> str:
        return self.launcher.get("defaultProton", "User Settings") or \
            "GE-Proton Latest"

    def installs_dir(self) -> str:
        try:
            return self.launcher_settings.get_base_path_for("installs")
        except Exception:
            return os.path.join(default_share_dir(), "installs")

    def scan(self, path: str) -> dict[str, Any]:
        """List launchable files inside a folder (same rules as scan_dir)."""
        if not path or not os.path.isdir(path):
            return {"ok": False, "error": "folder not found"}
        files: list[dict[str, Any]] = []
        for full in scan_dir(path):
            ext = os.path.splitext(full)[1].lower()
            files.append({
                "path": full,
                "name": os.path.basename(full),
                "dir": os.path.dirname(full),
                "type": "archive" if ext == ".rar" else "executable",
                "size": os.path.getsize(full),
            })
        return {"ok": True, "path": path, "files": files}

    def add_game(self, name: str, executable: str,
                 main_path: Optional[str] = None) -> dict[str, Any]:
        name = (name or "").strip()
        if not name:
            return {"ok": False, "error": "name is required"}
        if not executable:
            return {"ok": False, "error": "executable is required"}
        if self.games.has_section(name):
            return {"ok": False, "error": "a game with this name exists"}
        if not main_path:
            main_path = os.path.dirname(executable)
        proton = self.default_proton()
        self.games.put({
            "executable": executable,
            "mainPath": main_path,
            "proton": proton,
            "steamRuntime": bool(find_steam_runtime(proton)),
            "steamOverlay": True,
            "overrides": "",
            "wined3d": self.launcher.get("gamesUsesWined3d", "User Settings") or "",
            "nativeWayland": self.launcher.get("gamesUsesWayland", "User Settings") or "",
            "timeSpent": 0,
        }, name)
        return {"ok": True, "name": name}

    def extract_archive(self, archive: str, name: str) -> dict[str, Any]:
        """Extract a .rar/.zip/.7z into the installs folder."""
        import subprocess
        from .files_worker import get_third_party

        if not os.path.isfile(archive):
            return {"ok": False, "error": "archive not found"}
        folder = name or os.path.splitext(os.path.basename(archive))[0]
        dest = os.path.join(self.installs_dir(), folder)
        os.makedirs(dest, exist_ok=True)
        ext = os.path.splitext(archive)[1].lower()
        try:
            if ext == ".rar":
                unrar = get_third_party("unrar")
                if not unrar:
                    return {"ok": False, "error": "unrar is not available"}
                result = subprocess.run(
                    [unrar, "x", "-y", "-p-", archive, os.path.join(dest, "")],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    text=True, timeout=1800)
                if result.returncode not in (0, 1):  # 1 = warnings
                    return {"ok": False,
                            "error": (result.stderr or "extraction failed").strip()}
            else:
                seven = get_third_party("7zip")
                if not seven:
                    return {"ok": False, "error": "7z is not available"}
                subprocess.run([seven, "x", "-y", f"-o{dest}", archive],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=1800)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "extraction timed out"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        files = []
        for full in scan_dir(dest):
            files.append({"path": full, "name": os.path.basename(full),
                          "dir": os.path.dirname(full), "type": "executable",
                          "size": os.path.getsize(full)})
        return {"ok": True, "dest": dest, "files": files}

    # ------------------------------------------------------------------ launch
    def launch(self, name: str, debug: bool = False) -> dict[str, Any]:
        """Start a game.  Everything that can fail fast is checked here so
        the UI gets an immediate answer; the Proton/Steam preparation runs
        in a worker thread (it can take a while when Steam has to boot)."""
        if GLOBALS.get("currentGameProcess") is not None or \
                GLOBALS.get("launchStatus") == "preparing":
            return {"ok": False, "error": "A game is already running"}
        game = self.get_game(name)
        if not game:
            return {"ok": False, "error": "unknown game"}
        executable = game.get("executable") or ""
        if not executable or not os.path.isfile(executable):
            return {"ok": False, "error": "executable not found"}
        if not self.launcher.get_bool("noSteamRequest", "User Settings", False):
            from shutil import which
            if which("steam") is None:
                return {"ok": False,
                        "error": "Steam is not installed — enable “Skip the "
                                 "Steam check” in Settings to launch anyway"}
        try:
            proton = get_proton_executable(name)
        except Exception as exc:
            log_error(f"proton lookup failed: {exc}")
            proton = None
        if proton in (False, None):
            return {"ok": False,
                    "error": "Proton not found — download one on the Runners page"}
        self._cancel_launch.clear()
        GLOBALS["currentGameName"] = name
        GLOBALS["launchStatus"] = "preparing"
        GLOBALS["lastLaunchError"] = None

        def worker():
            try:
                spec = generate_process(name, debug)
                if spec is None:
                    raise RuntimeError("Proton could not start the game")
                if self._cancel_launch.is_set():
                    log_info(f"launch of {name} cancelled")
                    return
                GLOBALS["launchStatus"] = "running"
                run_spec(spec, name, debug)
                log_info(f"{name} fully terminated")
            except Exception as exc:
                log_error(f"launch of {name} failed: {exc}")
                GLOBALS["lastLaunchError"] = str(exc)
            finally:
                GLOBALS["currentGameProcess"] = None
                GLOBALS["currentGameName"] = None
                GLOBALS["launchStatus"] = None

        threading.Thread(target=worker, daemon=True, name=f"launch-{name}").start()
        return {"ok": True, "status": "preparing"}

    def stop(self) -> dict[str, Any]:
        process = GLOBALS.get("currentGameProcess")
        name = GLOBALS.get("currentGameName")
        if process is None:
            if GLOBALS.get("launchStatus") == "preparing":
                self._cancel_launch.set()
                return {"ok": True, "cancelling": True}
            return {"ok": False, "error": "No game is running"}
        try:
            process.terminate()
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        log_info(f"Stopping {name or 'game'}…")
        return {"ok": True}

    def state(self) -> dict[str, Any]:
        return {
            "running": GLOBALS.get("currentGameName"),
            "status": GLOBALS.get("launchStatus"),
            "lastError": GLOBALS.get("lastLaunchError"),
            "version": GLOBALS.get("version", "2.7.1"),
            "configDir": config_dir(),
            "time": time.time(),
        }

    def open_proton_downloader(self, proton: str = "",
                               url: Optional[str] = None,
                               modal: bool = True) -> None:
        """Headless counterpart of the classic Proton downloader window."""
        log_info(f"Proton '{proton}' is missing — use the Runners page")

    # ------------------------------------------------------------------ artwork
    def set_art(self, name: str, kind: str, data_url: str) -> dict[str, Any]:
        """Save a data-URL image as banner/icon and point Games.ini to it."""
        if not self.games.has_section(name):
            return {"ok": False, "error": "game not found"}
        try:
            header, b64 = data_url.split(",", 1)
            if ";base64" not in header:
                return {"ok": False, "error": "unsupported image data"}
            ext = "png"
            if "image/jpeg" in header:
                ext = "jpg"
            elif "image/webp" in header:
                ext = "webp"
            data = base64.b64decode(b64)
        except Exception:
            return {"ok": False, "error": "bad image data"}
        if len(data) > 12 * 1024 * 1024:
            return {"ok": False, "error": "image too large (12 MB max)"}
        if kind == "icon":
            folder, key = icons_dir(), "icon"
        else:
            folder, key = banners_dir(), "banner"
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{name}.{ext}")
        try:
            with open(path, "wb") as fh:
                fh.write(data)
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        self.games.set(key, path, name)
        return {"ok": True, "path": path}

    # ---------------------------------------------------------------- shortcuts
    def create_shortcut(self, name: str) -> dict[str, Any]:
        game = self.get_game(name)
        if not game:
            return {"ok": False, "error": "unknown game"}
        icon = game.get("icon") or ""
        entry = generate_desktop_entry(name, icon or None)
        targets = [
            os.path.join(os.path.expanduser("~"), ".local", "share",
                         "applications", f"{name}.desktop"),
            os.path.join(os.path.expanduser("~"), "Desktop", f"{name}.desktop"),
        ]
        created: list[str] = []
        for path in targets:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(entry)
                os.chmod(path, 0o755)
                created.append(path)
            except OSError:
                pass
        if not created:
            return {"ok": False, "error": "could not write .desktop entries"}
        run_command = __import__("subprocess").run
        try:
            run_command(["update-desktop-database", os.path.join(
                os.path.expanduser("~"), ".local", "share", "applications")],
                stdout=__import__("subprocess").DEVNULL,
                stderr=__import__("subprocess").DEVNULL)
        except Exception:
            pass
        return {"ok": True, "created": created}

    # ------------------------------------------------------------------ protons
    def installed_protons(self) -> dict[str, Any]:
        protons: list[str] = []
        try:
            protons = get_installed_protons()
        except Exception as exc:
            log_error(f"proton listing failed: {exc}")
        latest = None
        try:
            from .files_worker import ensure_proton_latest_name
            latest = ensure_proton_latest_name()
        except Exception:
            pass
        return {"installed": protons, "latestName": latest}

    def proton_latest(self) -> dict[str, Any]:
        from .files_worker import fetch_proton_releases
        try:
            releases = fetch_proton_releases()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if not releases:
            return {"ok": False, "error": "no releases found"}
        name, info = next(iter(releases.items()))
        return {"ok": True, "name": name, "url": info.get("url"),
                "filename": info.get("filename")}

    def proton_download(self, name: str, url: str) -> dict[str, Any]:
        """Stream the newest GE-Proton release, extract it into the protons
        folder and report progress through :meth:`proton_progress`."""
        if self._dl.get("busy"):
            return {"ok": False, "error": "another download is running"}
        info = self.proton_latest()
        url = url or info.get("url") or ""
        if not url:
            return {"ok": False, "error": "no download URL"}
        try:
            os.makedirs(self.launcher_settings.get_base_path_for("protons"),
                        exist_ok=True)
        except Exception:
            pass
        dest_dir = self.launcher_settings.get_base_path_for("protons")
        filename = os.path.basename(url.split("?")[0]) or (name + ".tar.gz")
        dest = os.path.join(dest_dir, filename)
        self._dl = {"name": name or info.get("name"), "dest": dest,
                    "fraction": 0.0, "bytes": 0, "total": 0,
                    "done": False, "error": None, "busy": True,
                    "extracting": False, "cancel": threading.Event()}
        cancel = self._dl["cancel"]

        def worker():
            import subprocess
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "OnlineFix-Linux-Launcher"})
                with urllib.request.urlopen(request, timeout=60) as response:
                    total = int(response.headers.get("Content-Length") or 0)
                    self._dl["total"] = total
                    tmp = dest + ".part"
                    with open(tmp, "wb") as fh:
                        while not cancel.is_set():
                            chunk = response.read(128 * 1024)
                            if not chunk:
                                break
                            fh.write(chunk)
                            self._dl["bytes"] += len(chunk)
                            if total:
                                self._dl["fraction"] = \
                                    self._dl["bytes"] / total
                    if cancel.is_set():
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
                        self._dl.update({"error": "cancelled", "busy": False})
                        return
                    os.replace(tmp, dest)
                # extract into its own folder
                folder = os.path.join(
                    dest_dir,
                    os.path.splitext(os.path.splitext(filename)[0])[0])
                os.makedirs(folder, exist_ok=True)
                seven = self._seven_zip_path()
                if seven:
                    self._dl["extracting"] = True
                    subprocess.run([seven, "x", "-y", f"-o{dest_dir}", dest],
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                    try:
                        os.remove(dest)
                    except OSError:
                        pass
                self._dl.update({"done": True, "fraction": 1.0, "busy": False})
            except Exception as exc:
                log_error(f"proton download failed: {exc}")
                self._dl.update({"error": str(exc), "busy": False})

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True, "dest": dest}

    @staticmethod
    def _seven_zip_path() -> Optional[str]:
        for path in ("/usr/bin/7z", "/usr/bin/7za"):
            if os.path.isfile(path):
                if os.access(path, os.X_OK):
                    return path
                return path  # chmod happens on demand in files_worker
        bundled = os.path.join(default_share_dir(), "..", "thirdparty", "7zip",
                               "7z")
        path = os.path.abspath(bundled)
        return path if os.path.isfile(path) else None

    def proton_progress(self) -> dict[str, Any]:
        dl = self._dl
        return {k: v for k, v in dl.items() if k not in ("cancel",)}

    def cancel_proton_download(self) -> dict[str, Any]:
        ev = self._dl.get("cancel")
        if ev:
            ev.set()
        return {"ok": True}

    # --------------------------------------------------------------- launcher
    LAUNCHER_KEYS = ("defaultProton", "noSteamRequest", "fullscreen",
                     "language", "gamesUsesWined3d", "gamesUsesWayland",
                     "installsPath", "protonsPath", "prefixesPath",
                     "defaultRunner", "defaultFixType")

    def launcher_config(self) -> dict[str, Any]:
        """The launcher preferences shown on the Settings page."""
        get = self.launcher.get
        gb = self.launcher.get_bool
        return {
            "defaultProton": get("defaultProton", "User Settings") or "",
            "noSteamRequest": gb("noSteamRequest", "User Settings", False),
            "fullscreen": gb("fullscreen", "User Settings", False),
            "language": get("language", "User Settings") or "en",
            "gamesUsesWined3d": gb("gamesUsesWined3d", "User Settings", False),
            "gamesUsesWayland": gb("gamesUsesWayland", "User Settings", False),
            "installsPath": get("installsPath", "User Settings")
                            or self.installs_dir(),
            "protonsPath": self.launcher_settings.get_base_path_for("protons"),
            "prefixesPath": self.launcher_settings.get_base_path_for("prefixes"),
            "bannersPath": banners_dir(),
            "iconsPath": icons_dir(),
            "defaultRunner": get("defaultRunner", "User Settings") or "proton",
            "defaultFixType": get("defaultFixType", "User Settings") or "onlinefix",
            "protons": get_installed_protons(),
            "version": GLOBALS.get("version", "2.7.1"),
            "configDir": config_dir(),
        }

    def launcher_set(self, key: str, value: Any) -> dict[str, Any]:
        if key not in self.LAUNCHER_KEYS:
            return {"ok": False, "error": "unknown setting"}
        self.launcher.set(key, value, "User Settings")
        return {"ok": True}