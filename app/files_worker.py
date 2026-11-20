"""Port of FilesWorker.php: Proton discovery, process generation and logging."""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tkinter as tk
import time
import urllib.request
from dataclasses import dataclass
from typing import Optional

from . import dialogs, i18n, runtime
from .assets import BASE_DIR
from .process_util import (hook_process_outputs, open_path, popen, run as run_command,
                           wait_for_process, which)
from .runtime import GLOBALS, log_error, log_info, log_warn, ui_call


@dataclass
class LaunchSpec:
    args: list[str]
    cwd: Optional[str]
    env: dict


def _app():
    return runtime.get_app()


def config_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".config", "OFME-Linux")


def banners_dir() -> str:
    return os.path.join(config_dir(), "banners")


def icons_dir() -> str:
    return os.path.join(config_dir(), "icons")


def default_share_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".local", "share", "OnlineFix Linux Launcher")


def launcher_executable() -> str:
    """The launcher executable to write into game .desktop shortcuts.

    Prefers the installed command (from install.sh) and falls back to the
    in-tree script so development copies keep working.
    """
    from shutil import which

    for candidate in (
        which("onlinefix-launcher"),
        "/usr/local/bin/onlinefix-launcher",
        os.path.expanduser("~/.local/bin/onlinefix-launcher"),
        "/usr/bin/onlinefix-linux-launcher",
    ):
        if candidate and os.path.isfile(candidate):
            return candidate
    return os.path.join(BASE_DIR, "onlinefix-linux-launcher")


def generate_desktop_entry(name: str, icon: Optional[str] = None) -> str:
    pwd = os.path.abspath(".")
    exec_path = launcher_executable()
    return (
        "[Desktop Entry]\n"
        f"Name={name}\n"
        "GenericName=Play this game with OnlineFix Launcher\n"
        f"Exec=\"{exec_path}\" \"{name}\"\n"
        f"Icon={icon or ''}\n"
        f"Path={pwd}\n"
        "Type=Application\n"
        "Categories=Game;"
    )


# --------------------------------------------------------------------- launch
def _error(message: str):
    ui_call(lambda: dialogs.show_message(runtime.get_root(), message, "ERROR", "error"))


def generate_process(name: str, debug: bool = False) -> Optional[LaunchSpec]:
    app = _app()
    launcher = app.launcher
    games = app.games

    if not launcher.get_bool("noSteamRequest", "User Settings", False):
        if which("steam") is None:
            _error(i18n._("FILESWORKER.NOSTEAM"))
            return None
        pidof = run_command(["pidof", "steam"])
        if pidof.returncode == 1:
            if not run_steam():
                def fail():
                    dialogs.show_message(runtime.get_root(), i18n._("FILESWORKER.STEAMNOTSTARTED"), "ERROR")
                    main = app.main_form
                    if main and main.visible:
                        main.switch_play_button("play")
                ui_call(fail)
                return None

    executable = games.get("executable", name)
    proton = get_proton_executable(name)
    if proton is False or proton is None:
        _error(i18n._("FILESWORKER.PROTON.NOTFOUND"))
        return None
    if not executable or not os.path.isfile(executable):
        _error(i18n._("FILESWORKER.NOGAME"))
        return None

    args_before = games.get("argsBefore", name)
    args_after = games.get("argsAfter", name)

    args = [proton, "run", executable]
    user_home = os.path.expanduser("~")
    wined3d = games.get_bool("wined3d", name, False)

    if not wined3d:
        dx_overrides = ("d3d11=n;d3d10=n;d3d10core=n;dxgi=n;openvr_api_dxvk=n;"
                        "d3d12=n;d3d12core=n;d3d9=n;d3d8=n;")
    else:
        dx_overrides = ""

    env = {
        "WINEDLLOVERRIDES": dx_overrides + (games.get("overrides", name) or ""),
        "WINEDEBUG": debug if debug else "-all",
        "STEAM_COMPAT_DATA_PATH": get_proton_prefix_path(name),
        "STEAM_COMPAT_CLIENT_INSTALL_PATH": os.path.join(user_home, ".steam", "steam"),
        "PROTON_USE_WINED3D": "1" if wined3d else "0",
        "PROTON_ENABLE_WAYLAND": "1" if games.get_bool("nativeWayland", name, False) else "0",
    }

    if games.get_bool("steamOverlay", name, False):
        env.update({
            "LD_PRELOAD": (f":{user_home}/.steam/steam/ubuntu12_32/gameoverlayrenderer.so:"
                           f"{user_home}/.steam/steam/ubuntu12_64/gameoverlayrenderer.so"),
            "ENABLE_VK_LAYER_VALVE_steam_overlay_1": "1",
            "SteamOverlayGameId": str(games.get("fakeSteamID", name) or 480),
        })

    if games.get("environment", name):
        from .forms.env_viewer import parse_environment_array
        env.update(parse_environment_array(name))

    if args_after:
        args.extend(str(args_after).split())

    if games.get_bool("steamRuntime", name, False):
        steam_runtime = find_steam_runtime(games.get("proton", name))
        if steam_runtime is False:
            games.set("steamRuntime", False, name)
        else:
            args = [steam_runtime, "--"] + args

    if args_before:
        args = str(args_before).split() + args

    prefix = env["STEAM_COMPAT_DATA_PATH"]
    try:
        os.makedirs(prefix, exist_ok=True)
    except OSError as exc:
        log_error(f"Failed to create prefix {prefix}: {exc}")

    return LaunchSpec(args=args, cwd=os.path.dirname(executable), env=env)


def run_game_process(spec: LaunchSpec, game_name: str, debug: bool = False) -> int:
    app = _app()
    start = int(time.time())
    GLOBALS["implicitDisableReason"] = "game"

    process = popen(spec.args, cwd=spec.cwd, env=spec.env)
    # tracked so the Runners page can stop a running game
    GLOBALS["currentGameProcess"] = process
    GLOBALS["currentGameName"] = game_name

    def line_hook(tag: str, line: str):
        def add():
            form = app.forms.get("log")
            if form is not None:
                try:
                    form.text_area.insert("end", f"STD{tag} - {line}\n")
                    form.text_area.see("end")
                except tk.TclError:
                    pass  # log page was closed
        runtime.ui_later(add)

    hook_process_outputs(process, debug=debug, line_callback=line_hook)
    exit_code = wait_for_process(process)
    GLOBALS["currentGameProcess"] = None
    GLOBALS["currentGameName"] = None
    GLOBALS["lastExitCode"] = exit_code

    if debug:
        debug_log(exit_code, game_name)

    stop = int(time.time())
    old = app.games.get_int("timeSpent", game_name, 0)
    app.games.set("timeSpent", old + (stop - start), game_name)

    if GLOBALS.get("implicitDisableReason") == "game":
        GLOBALS["implicitDisableReason"] = None
    log_info(f"{game_name} process has finished, waiting for the wineprefix to complete")
    return exit_code


def run(spec: LaunchSpec, game_name: str, debug: bool = False) -> int:
    return run_game_process(spec, game_name, debug)


def debug_log(exit_code: int, game_name: str):
    app = _app()

    def show():
        info = f"Game name - {game_name}\nExit code - {exit_code}\nGame settings:\n"
        for param, value in app.games.section(game_name).items():
            info += f"\t{param} - {value}\n"
        info += "OS Release:\n"
        try:
            with open("/etc/os-release", "r", encoding="utf-8", errors="replace") as fh:
                for line in fh.read().splitlines():
                    info += f"\t{line}\n"
        except OSError:
            pass
        form = app.ensure_form("log")
        form.set_game(game_name)
        form.prepend_text(info + "\n")
        form.show()

    runtime.ui_later(show)


# --------------------------------------------------------------------- Proton
def _machine_is_arm() -> bool:
    return platform.machine().lower() in ("aarch64", "arm64")


def fetch_proton_releases() -> dict[str, dict]:
    protons: dict[str, dict] = {}
    request = urllib.request.Request(
        "https://api.github.com/repos/gloriouseggroll/proton-ge-custom/releases",
        headers={"User-Agent": "OnlineFix-Linux-Launcher", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
    except Exception as exc:
        log_error(f"Failed to fetch GE-Proton releases - {exc}")
        return protons

    for release in data if isinstance(data, list) else []:
        name = filename = url = None
        for asset in release.get("assets", []):
            content_type = asset.get("content_type", "")
            is_gzip = bool(re.search(r"^application/(gzip|x-gtar)$", content_type))
            is_arm = "aarch64" in asset.get("name", "")
            if not is_gzip or is_arm != _machine_is_arm():
                continue
            name = release.get("tag_name")
            filename = asset.get("name")
            url = asset.get("browser_download_url")
            break
        if not (name and filename and url):
            continue
        protons[name] = {"filename": filename, "url": url}
    return protons


def find_newest_available_proton() -> Optional[str]:
    protons_path = _app().launcher_settings.get_base_path_for("protons")
    latest_path = None
    latest_date = 0.0
    try:
        for entry in os.listdir(protons_path):
            proton = os.path.join(protons_path, entry, "proton")
            if os.path.isfile(proton):
                mtime = os.path.getmtime(proton)
                if mtime > latest_date:
                    latest_date = mtime
                    latest_path = entry
    except OSError:
        return None
    return latest_path


def get_installed_protons() -> list[str]:
    protons_path = _app().launcher_settings.get_base_path_for("protons")
    result = []
    if os.path.isdir(protons_path):
        for entry in sorted(os.listdir(protons_path)):
            if os.path.isfile(os.path.join(protons_path, entry, "proton")):
                result.append(entry)
    return result


def ensure_proton_latest_name() -> Optional[str]:
    latest = GLOBALS.get("LatestProton")
    if not latest or latest == "fetching":
        return find_newest_available_proton()
    pos = latest.rfind("/")
    tar_pos = latest.find(".tar")
    if tar_pos == -1:
        tar_pos = len(latest)
    return latest[pos + 1:tar_pos]


def ensure_proton_path(proton: str) -> Optional[str]:
    if proton == "GE-Proton Latest":
        proton = ensure_proton_latest_name()
        if not proton:
            return None
    path = os.path.join(_app().launcher_settings.get_base_path_for("protons"), proton)
    return path if os.path.exists(path) else None


def get_proton_executable(game_name: Optional[str] = None, exec_name: str = "proton",
                          skip_if_not_found: bool = False):
    app = _app()
    if game_name is not None:
        proton = app.games.get("proton", game_name)
    else:
        proton = app.launcher.get("defaultProton", "User Settings") or "GE-Proton Latest"

    proton_path = ensure_proton_path(proton)
    exec_path = (os.path.join(proton_path, "proton") if exec_name == "proton"
                 else os.path.join(proton_path, "files", "bin", exec_name)) if proton_path else None

    if not exec_path or not os.path.isfile(exec_path):
        if not skip_if_not_found:
            main = app.main_form
            if main and main.visible:
                runtime.ui_later(lambda: main.switch_play_button("wait"))
            url = GLOBALS.get("LatestProton")
            app.open_proton_downloader(proton, url, modal=True)
            return get_proton_executable(game_name, exec_name, True)
        return False
    return os.path.abspath(exec_path)


def get_proton_prefix_path(game_name: str, prefix_type: str = "proton") -> str:
    app = _app()
    prefix = app.games.get("prefixPath", game_name)
    if not prefix:
        executable = app.games.get("executable", game_name) or ""
        prefix = os.path.join(os.path.dirname(executable), "OFME Prefix")
    if prefix_type == "wine":
        prefix = os.path.join(prefix, "pfx")
    os.makedirs(prefix, exist_ok=True)
    return prefix


# ---------------------------------------------------------------- Steam parts
def _vdf_load(path: str) -> dict:
    try:
        import vdf  # type: ignore
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return vdf.load(fh)
    except Exception:
        return {}


def find_steam_runtime(for_proton: Optional[str]):
    proton_path = ensure_proton_path(for_proton or "GE-Proton Latest")
    if not proton_path:
        return False
    proton_version = None
    try:
        with open(os.path.join(proton_path, "version"), "r", encoding="utf-8", errors="replace") as fh:
            match = re.search(r"GE-Proton(\d+)-", fh.read())
            if match:
                proton_version = int(match.group(1))
    except OSError:
        pass
    if proton_version is None:
        proton_version = 11

    if proton_version >= 11:
        if platform.machine().lower() in ("aarch64", "arm64"):
            appid, dirname = 4185400, "SteamLinuxRuntime_4-arm64"
        else:
            appid, dirname = 4183110, "SteamLinuxRuntime_4"
    elif 8 <= proton_version <= 10:
        appid, dirname = 1628350, "SteamLinuxRuntime_sniper"
    else:
        appid, dirname = 1391110, "SteamLinuxRuntime_soldier"

    vdf_path = os.path.join(os.path.expanduser("~"), ".steam", "steam", "steamapps", "libraryfolders.vdf")
    data = _vdf_load(vdf_path)
    libraryfolders = data.get("libraryfolders", {}) if isinstance(data, dict) else {}
    folders = libraryfolders.values() if isinstance(libraryfolders, dict) else []
    for folder in folders:
        if not isinstance(folder, dict):
            continue
        try:
            apps = folder.get("apps", {})
            path = folder.get("path")
            if str(appid) in apps and path and os.path.isfile(
                    os.path.join(path, "steamapps", "common", dirname, "run")):
                return os.path.join(path, "steamapps", "common", dirname, "run")
        except Exception:
            continue
    return False


def run_steam() -> bool:
    app = _app()
    attempts = 0

    def switch_wait():
        main = app.main_form
        if main and main.visible:
            main.switch_play_button("wait")

    runtime.ui_later(switch_wait)
    try:
        steam = subprocess.Popen(["steam", "-silent"], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        loginusers = os.path.join(os.path.expanduser("~"), ".steam", "steam", "config", "loginusers.vdf")
        try:
            last_mod = os.path.getmtime(loginusers)
        except OSError:
            last_mod = -1
        while attempts <= 420:
            exists = os.path.exists(loginusers)
            if exists and os.path.getmtime(loginusers) != last_mod:
                break
            if steam.poll() is not None:
                attempts = 421
                break
            attempts += 1
            time.sleep(1)
    except Exception:
        attempts = 421

    runtime.ui_later(switch_wait)
    return attempts <= 420


def scan_dir(path: str) -> list[str]:
    """Recursively find .exe/.vbs/.bat/.rar files (MainForm::scanDir)."""
    allowed = (".exe", ".vbs", ".bat", ".rar")
    result = []
    for root, _dirs, files in os.walk(path):
        for name in files:
            if name.lower().endswith(allowed):
                result.append(os.path.join(root, name))
    result.sort()
    return result


def get_third_party(prog: str) -> Optional[str]:
    progs = {
        "7zip": "/usr/bin/7z" if os.path.isfile("/usr/bin/7z") else os.path.join(BASE_DIR, "thirdparty", "7zip", "7z"),
        "unrar": "/usr/bin/unrar" if os.path.isfile("/usr/bin/unrar") else os.path.join(BASE_DIR, "thirdparty", "unrar", "unrar"),
    }
    path = progs.get(prog)
    if not path or not os.path.isfile(path):
        ui_call(lambda: dialogs.show_message(
            runtime.get_root(), i18n._("FILESWORKER.NOSUBMODULE") % path, "ERROR"))
        return None
    try:
        os.chmod(path, os.stat(path).st_mode | 0o111)
    except OSError:
        pass
    return os.path.abspath(path)
