"""Headless backend for the web UI.

Duck-types enough of :class:`app.core.Application` for
:mod:`app.files_worker` to generate and run game processes without a
Tk main loop.  ``runtime.set_root()`` is intentionally never called, so
``runtime.ui_call`` executes callbacks directly on the calling thread.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional

from . import i18n
from .files_worker import banners_dir, generate_process, icons_dir, run as run_spec
from .runtime import GLOBALS, log_error, log_info
from .storage import IniStorage


def config_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".config", "OFME-Linux")


class WebApp:
    """Headless application core (no Tk)."""

    def __init__(self):
        config = config_dir()
        os.makedirs(config, exist_ok=True)
        self.root = None                 # no Tk in web mode
        self.main_form = None            # files_worker tolerates None
        self.games = IniStorage(os.path.join(config, "Games.ini"))
        self.launcher = IniStorage(os.path.join(config, "Launcher.ini"))
        self.launcher.ensure_section("User Settings")
        i18n.init(self.launcher.get("language", "User Settings"))

        from .core import LauncherSettingsHelper
        self.launcher_settings = LauncherSettingsHelper(self)

        self._launch_lock = threading.Lock()

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

    # ---------------------------------------------------------------- launch
    def launch(self, name: str, debug: bool = False) -> dict[str, Any]:
        if GLOBALS.get("currentGameProcess") is not None:
            return {"ok": False, "error": "A game is already running"}

        def worker():
            try:
                spec = generate_process(name, debug)
                if spec is None:
                    return
                GLOBALS["currentGameName"] = name
                run_spec(spec, name, debug)
                log_info(f"{name} fully terminated")
            except Exception as exc:  # pragma: no cover
                log_error(f"launch of {name} failed: {exc}")
            finally:
                GLOBALS["currentGameProcess"] = None
                GLOBALS["currentGameName"] = None

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def stop(self) -> dict[str, Any]:
        process = GLOBALS.get("currentGameProcess")
        name = GLOBALS.get("currentGameName")
        if process is None:
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
            "version": GLOBALS.get("version", "2.7.1"),
            "configDir": config_dir(),
            "time": time.time(),
        }
