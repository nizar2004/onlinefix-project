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
import subprocess
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
    "steamOverlay", "steamRuntime", "wined3d", "nativeWayland", "noBanner",
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
    def _running_game_name(self) -> Optional[str]:
        """Name of the game that is running right now.

        Besides the process this launcher started, games that were started by
        an earlier launcher session are detected as well — otherwise the Stop
        button would be missing exactly when the game refuses to quit.
        """
        running = GLOBALS.get("currentGameName")
        if running:
            return running
        now = time.time()
        checked = GLOBALS.get("externalRunningAt") or 0
        if now - checked < 2.0:
            return GLOBALS.get("externalRunning")
        found = None
        for name in self.games.sections():
            executable = self.games.get("executable", name) or ""
            if not executable:
                continue
            if self._pids_matching(executable, os.path.basename(executable),
                                   wine_only=True):
                found = name
                break
        GLOBALS["externalRunning"] = found
        GLOBALS["externalRunningAt"] = now
        return found

    def list_games(self) -> list[dict[str, Any]]:
        """Every game section as a UI-friendly dict."""
        out: list[dict[str, Any]] = []
        running = self._running_game_name()
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
                "running": running == name,
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

    # ---------------------------------------------------------------- OnlineFix
    @staticmethod
    def _scan_root(game: dict[str, Any]) -> str:
        """Folder the classic wizard scans for OnlineFix DLLs."""
        main_path = game.get("mainPath") or ""
        if main_path and os.path.isdir(main_path):
            return main_path
        executable = game.get("executable") or ""
        return os.path.dirname(executable) if executable else ""

    def _fix_folder(self, name: str) -> str:
        path = self.games.get("fixPath", name) or ""
        return path if path and os.path.isdir(path) else ""

    def _steamfix_dlls(self, name: str) -> list[str]:
        folder = self._fix_folder(name)
        if not folder:
            return []
        try:
            entries = os.listdir(folder)
        except OSError:
            return []
        return [os.path.join(folder, entry) for entry in entries
                if entry.lower() in ("steamfix32.dll", "steamfix64.dll")]

    def _fake_steam_active(self, name: str) -> bool:
        folder = self._fix_folder(name)
        if not folder:
            return False
        try:
            entries = os.listdir(folder)
        except OSError:
            return False
        return any(entry.endswith(".noofllpath") for entry in entries)

    @staticmethod
    def _merge_overrides(current: str, found: str) -> str:
        """Union of both override lists, keeping the user's order first."""
        seen: set[str] = set()
        parts: list[str] = []
        for chunk in f"{current};{found}".split(";"):
            chunk = chunk.strip()
            if not chunk or chunk.lower() in seen:
                continue
            seen.add(chunk.lower())
            parts.append(chunk)
        return ";".join(parts)

    def detect_fixes(self, name: str, fetch_art: bool = True) -> dict[str, Any]:
        """Port of the classic add-game fix pipeline (FixParser.php).

        Scans the game folder the way ``new_game_configurator`` does, then
        stores the native DLL overrides, the fix folder and the Steam app ids
        that ``files_worker.generate_process`` turns into the Proton command:
        ``WINEDLLOVERRIDES`` makes Proton use the OnlineFix DLLs shipped with
        the game and the Steam overlay env registers Spacewar (480) so those
        DLLs see a running Steam game.
        """
        if not self.games.has_section(name):
            return {"ok": False, "error": "game not found"}
        game = self.get_game(name)
        root = self._scan_root(game)
        if not root or not os.path.isdir(root):
            return {"ok": False, "error": "game folder not found"}
        try:
            from . import fix_parser
            parsed = fix_parser.parse_dlls(root) or {}
        except Exception as exc:
            log_error(f"fix scan for {name} failed: {exc}")
            return {"ok": False, "error": str(exc)}

        # OnlineFix/FreeTP patches inside the folder (steamfix.ini …) have
        # been applied by parse_dlls at this point, exactly like the wizard.
        current = game.get("overrides") or ""
        merged = self._merge_overrides(current, parsed.get("overrides") or "")
        if merged != current:
            self.games.set("overrides", merged, name)

        fix_path = parsed.get("fixPath")
        if fix_path:
            self.games.set("fixPath", fix_path, name)

        real_id = parsed.get("realAppId")
        fake_id = parsed.get("fakeAppId")
        if real_id is not None:
            self.games.set("steamID", real_id, name)
        if fake_id is not None:
            self.games.set("fakeSteamID", fake_id, name)

        # the wizard always enables the overlay: without it Proton never
        # starts the Spacewar session the fix DLLs talk to
        if "steamOverlay" not in self.games.section(name):
            self.games.set("steamOverlay", True, name)

        if fetch_art:
            if not game.get("banner") and real_id is not None:
                try:
                    banner = fix_parser.parse_banner(str(real_id))
                    if banner and os.path.isfile(str(banner)):
                        self.games.set("banner", banner, name)
                except Exception as exc:
                    log_error(f"banner fetch failed: {exc}")
            if not game.get("icon"):
                try:
                    icon = fix_parser.parse_icon(game.get("executable") or "")
                    if icon and os.path.isfile(icon):
                        self.games.set("icon", icon, name)
                except Exception as exc:
                    log_error(f"icon extraction failed: {exc}")

        data = self.get_game(name)
        data.update({
            "ok": True,
            "found": bool(parsed),
            "hasSteamfix": bool(self._steamfix_dlls(name)),
            "fakeSteamActive": self._fake_steam_active(name),
        })
        return data

    def set_fake_steam(self, name: str, enabled: bool) -> dict[str, Any]:
        """Mirror of the classic “Use fake Steam” switch: swap the fix's
        steamfix DLLs with the bundled FreeTP ones so the game boots through
        Spacewar instead of the real Steam client."""
        if not self.games.has_section(name):
            return {"ok": False, "error": "game not found"}
        dlls = self._steamfix_dlls(name)
        if not dlls:
            return {"ok": False,
                    "error": "this fix does not ship steamfix DLLs to swap"}
        from .assets import asset
        for dll in dlls:
            backup = dll + ".noofllpath"
            try:
                if enabled:
                    if not os.path.exists(backup):
                        os.replace(dll, backup)
                    source = asset("ftpPath", "ftpPath32.dll"
                                   if dll.lower().endswith("32.dll")
                                   else "ftpPath64.dll")
                    shutil.copy2(source, dll)
                else:
                    if os.path.exists(dll):
                        os.remove(dll)
                    if os.path.exists(backup):
                        os.replace(backup, dll)
            except OSError as exc:
                log_error(f"fake steam toggle for {name} failed: {exc}")
                return {"ok": False, "error": str(exc)}
        return {"ok": True, "fakeSteamActive": self._fake_steam_active(name)}

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
        data["hasSteamfix"] = bool(self._steamfix_dlls(name))
        data["fakeSteamActive"] = self._fake_steam_active(name)
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
        # Run the same OnlineFix detection the classic add-game wizard does:
        # DLL overrides + fix folder + Steam app ids, plus banner/icon.
        try:
            details = self.detect_fixes(name, fetch_art=True)
        except Exception as exc:
            log_error(f"fix detection for {name} failed: {exc}")
            details = {}
        return {"ok": True, "name": name,
                "fix": {key: details.get(key) for key in
                        ("found", "overrides", "fixPath", "steamID",
                         "fakeSteamID", "hasSteamfix")}}

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
        # Every Play button applies the OnlineFix DLL overrides of the game
        # folder first, so a game added by hand (or before the fix pipeline
        # existed) still launches exactly like the classic launcher. Games
        # that already carry fix settings keep them untouched.
        if not (game.get("overrides") or game.get("fixPath")):
            try:
                self.detect_fixes(name, fetch_art=False)
            except Exception as exc:
                log_error(f"fix detection for {name} failed: {exc}")
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
        current = self.get_game(name)
        overlay = bool(current.get("steamOverlay"))
        fake_id = current.get("fakeSteamID") or "480"
        has_fix = bool((current.get("overrides") or "").strip()
                       or current.get("fixPath"))
        return {
            "ok": True,
            "status": "preparing",
            "steamOverlay": overlay,
            "fakeSteamID": str(fake_id),
            "note": (f"Launching {name} · OnlineFix → Spacewar {fake_id}"
                     if overlay and has_fix else f"Launching {name}"),
        }

    def stop(self, name: Optional[str] = None) -> dict[str, Any]:
        """Stop the running game.

        Proton is started in its own session, so a plain ``terminate()`` only
        kills the wrapper and leaves wine/the game alive.  We signal the whole
        process group, ask that prefix's wineserver to quit, and finally reap
        any process still holding the game executable.
        """
        import signal

        process = GLOBALS.get("currentGameProcess")
        target = name or GLOBALS.get("currentGameName")
        if process is None:
            if GLOBALS.get("launchStatus") == "preparing":
                self._cancel_launch.set()
                return {"ok": True, "cancelling": True}
            # orphaned session (for example after the launcher restarted):
            # look for the game executable and stop it anyway
            if target:
                executable = self.games.get("executable", target) or ""
                pids = self._pids_matching(executable,
                                           os.path.basename(executable),
                                           wine_only=True)
                if pids:
                    self._signal_pids(pids, signal.SIGTERM)
                    threading.Thread(target=self._reap, args=(pids,),
                                     daemon=True).start()
                    log_info(f"Stopped leftover processes of {target}")
                    return {"ok": True, "stopping": True,
                            "orphans": len(pids)}
            return {"ok": False, "error": "No game is running"}
        executable = ""
        if target:
            executable = self.games.get("executable", target) or ""
        GLOBALS["launchStatus"] = "stopping"
        threading.Thread(target=self._kill_tree,
                         args=(process, target, executable),
                         daemon=True).start()
        log_info(f"Stopping {target or 'game'}…")
        return {"ok": True, "stopping": True}

    @staticmethod
    def _pids_matching(*needles: str, wine_only: bool = False) -> list[int]:
        """PIDs whose command line mentions any of the needles (self excluded).

        ``wine_only`` keeps only processes that really are wine/wineserver
        builds, so a shell that merely mentions the game in its arguments is
        never touched.
        """
        needles = [n for n in needles if n]
        if not needles:
            return []
        self_pid = os.getpid()
        found: list[int] = []
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            if pid == self_pid:
                continue
            try:
                with open(f"/proc/{entry}/cmdline", "rb") as fh:
                    cmdline = fh.read().replace(b"\0", b" ").decode(
                        "utf-8", "replace")
            except OSError:
                continue
            lowered = cmdline.lower()
            if not any(needle.lower() in lowered for needle in needles):
                continue
            if wine_only and not WebApp._is_wine_process(pid):
                continue
            found.append(pid)
        return found

    @staticmethod
    def _is_wine_process(pid: int) -> bool:
        """True for the wine/wineserver processes that host a Windows game."""
        try:
            exe = os.readlink(f"/proc/{pid}/exe")
        except OSError:
            return False
        name = os.path.basename(exe).lower()
        return "wine" in name or name.startswith("proton")

    @staticmethod
    def _signal_pids(pids: list[int], sig: int) -> None:
        for pid in pids:
            try:
                os.kill(pid, sig)
            except OSError:
                pass

    def _kill_tree(self, process, name: Optional[str],
                   executable: str) -> None:
        import signal

        name = name or ""
        game = os.path.basename(executable) if executable else ""

        def signal_group(sig: int) -> None:
            try:
                os.killpg(os.getpgid(process.pid), sig)
                return
            except OSError:
                pass
            try:
                process.send_signal(sig)
            except Exception:
                pass

        signal_group(signal.SIGTERM)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.15)

        leftovers = self._pids_matching(executable, game, wine_only=True)
        if process.poll() is None or leftovers:
            self._shutdown_wineserver(name)
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                leftovers = [pid for pid in leftovers
                             if os.path.exists(f"/proc/{pid}")]
                if process.poll() is not None and not leftovers:
                    break
                time.sleep(0.15)

        if process.poll() is None:
            signal_group(signal.SIGKILL)
        alive = [pid for pid in leftovers if os.path.exists(f"/proc/{pid}")]
        self._signal_pids(alive, signal.SIGKILL)
        log_info(f"{name or game or 'game'} stopped")

    def _reap(self, pids: list[int], grace: float = 2.5) -> None:
        import signal

        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            pids = [pid for pid in pids if os.path.exists(f"/proc/{pid}")]
            if not pids:
                return
            time.sleep(0.15)
        self._signal_pids(pids, signal.SIGKILL)

    def _shutdown_wineserver(self, name: str) -> None:
        """Ask the prefix's wineserver to quit, which closes every wine app."""
        if not name or not self.games.has_section(name):
            return
        try:
            proton = get_proton_executable(name, skip_if_not_found=True)
            if not proton:
                return
            wineserver = os.path.join(os.path.dirname(proton), "files", "bin",
                                      "wineserver")
            if not os.path.isfile(wineserver):
                return
            from .files_worker import get_proton_prefix_path
            prefix = get_proton_prefix_path(name, "wine")
            env = os.environ.copy()
            env["WINEPREFIX"] = prefix
            env["WINEDEBUG"] = "-all"
            subprocess.run([wineserver, "-k"], env=env, timeout=10,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        except Exception as exc:
            log_error(f"wineserver shutdown for {name} failed: {exc}")


    def state(self) -> dict[str, Any]:
        return {
            "running": self._running_game_name(),
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
                "filename": info.get("filename"),
                "size": int(info.get("size") or 0)}

    def proton_releases(self) -> dict[str, Any]:
        """Every GE-Proton release the Runners page can install."""
        from .files_worker import fetch_proton_releases
        try:
            releases = fetch_proton_releases()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if not releases:
            return {"ok": False, "error": "no releases found"}
        installed = set()
        try:
            installed = set(get_installed_protons())
        except Exception:
            pass
        items = []
        for name, info in releases.items():
            filename = info.get("filename") or ""
            folder = os.path.splitext(os.path.splitext(filename)[0])[0]
            items.append({
                "name": name,
                "filename": filename,
                "folder": folder,
                "url": info.get("url") or "",
                "size": int(info.get("size") or 0),
                "installed": name in installed or folder in installed,
            })
        return {"ok": True, "releases": items,
                "latest": items[0]["name"] if items else None}

    def proton_download(self, name: str, url: str,
                        size: int = 0) -> dict[str, Any]:
        """Stream a GE-Proton release, extract it into the protons folder and
        report progress through :meth:`proton_progress`."""
        if self._dl.get("busy"):
            return {"ok": False, "error": "another download is running"}
        url = url or ""
        if not url:
            info = self.proton_latest()
            url = info.get("url") or ""
            name = name or info.get("name") or ""
            size = size or int(info.get("size") or 0)
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
        self._dl = {"name": name or filename, "dest": dest,
                    "fraction": 0.0, "bytes": 0, "total": int(size or 0),
                    "done": False, "error": None, "busy": True,
                    "extracting": False, "cancel": threading.Event()}
        cancel = self._dl["cancel"]

        def worker():
            tmp = dest + ".part"
            try:
                tmp = self._download_release(url, dest, cancel)
                if cancel.is_set():
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
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                log_error(f"proton download failed: {exc}")
                self._dl.update({"error": str(exc), "busy": False})

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True, "dest": dest}

    def _download_release(self, url: str, dest: str,
                          cancel: threading.Event) -> str:
        """Fetch a release archive.

        GitHub's asset CDN drops Python's TLS handshake now and then, so curl
        (which follows the redirect reliably) is used when available and
        urllib stays as the fallback.
        """
        tmp = dest + ".part"
        curl = shutil.which("curl")
        if curl:
            process = subprocess.Popen(
                [curl, "-L", "--fail", "--silent", "--show-error",
                 "--retry", "3", "--retry-delay", "2", "--connect-timeout", "30",
                 "-o", tmp, url],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            while process.poll() is None:
                if cancel.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except Exception:
                        process.kill()
                    raise RuntimeError("cancelled")
                try:
                    self._dl["bytes"] = os.path.getsize(tmp)
                except OSError:
                    pass
                total = self._dl.get("total") or 0
                if total:
                    self._dl["fraction"] = min(1.0, self._dl["bytes"] / total)
                time.sleep(0.35)
            error = (process.stderr.read() or b"").decode("utf-8", "replace").strip()
            if process.returncode != 0:
                raise RuntimeError(error or f"curl exited with {process.returncode}")
            return tmp

        request = urllib.request.Request(
            url, headers={"User-Agent": "OnlineFix-Linux-Launcher"})
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            self._dl["total"] = total or self._dl.get("total") or 0
            with open(tmp, "wb") as fh:
                while not cancel.is_set():
                    chunk = response.read(128 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    self._dl["bytes"] += len(chunk)
                    if self._dl["total"]:
                        self._dl["fraction"] = \
                            self._dl["bytes"] / self._dl["total"]
        if cancel.is_set():
            raise RuntimeError("cancelled")
        return tmp

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