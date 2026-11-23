"""Port of FixParser.php: DLL overrides, banners, icons and fix-specific patches."""
from __future__ import annotations

import os
import random
import re
import shutil
import string
import subprocess
import urllib.error
import urllib.request

from . import i18n, runtime
from .assets import ASSETS, asset
from .files_worker import banners_dir, get_third_party, icons_dir
from .process_util import run
from .runtime import log_error, log_info
from .storage import IniStorage

DLL_PATTERN = re.compile(
    r"(?i)^(emp|custom)\.dll$|^win.*\.dll$|^(online|steam).*\.(dll|ini|json)$|"
    r"^eos.*\.dll$|^epicfix.*\.dll$|^(winmm|dlllist)\.txt$|^launch_data\.of.*$"
)
_NAME_LOWER = re.compile(r"(?i)^(winmm|dlllist)\.txt$")
_INIFIX = re.compile(r"(?i)^(online|steam)fix\.ini$")
_STEAMFIX_DLL = re.compile(r"(?i)^steamfix.*\.dll$")
_PHOTON = re.compile(r"(?i)^launch_data\.of.*$|^onlinefix\.json$")

# the launcher creates its Wine prefix inside the game folder when no
# prefixPath is configured — those DLLs are Wine's own, not the fix's
_PREFIX_DIR_NAMES = {"ofme prefix", "prefix", "pfx", "proton prefix"}


def _is_prefix_dir(name: str, path: str) -> bool:
    """True for the launcher's prefix folder (and anything shaped like one)."""
    if name.lower() in _PREFIX_DIR_NAMES:
        return True
    return os.path.isdir(os.path.join(path, "drive_c"))


def _walk_files(path: str):
    if not os.path.isdir(path):
        return
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs
                   if not d.startswith(".")
                   and not _is_prefix_dir(d, os.path.join(root, d))]
        for name in files:
            yield os.path.join(root, name)


def parse_dlls(path: str):
    overrides = ""
    real_app_id = None
    fake_app_id = None
    fix_path = None

    files = [f for f in _walk_files(path) if DLL_PATTERN.match(os.path.basename(f))]
    if not files:
        return None

    for file in files:
        name = os.path.basename(file)

        if _NAME_LOWER.match(name):
            try:
                with open(file, "r", encoding="utf-8", errors="replace") as fh:
                    lines = fh.read().split("\n")
            except OSError:
                lines = []
            for dll in lines:
                dll = dll.strip()
                if not dll or os.path.splitext(dll)[1].lower().lstrip(".") != "dll":
                    continue
                dll = os.path.splitext(os.path.basename(dll.replace("\\", "/")))[0].lower()
                if dll and dll not in overrides:
                    overrides += dll + "=n;"
            continue

        if _INIFIX.match(name):
            ini = IniStorage(file, autosave=False)
            real = ini.get("RealAppId", "OnlineFix Linux")
            if real is None:
                real = ini.get("RealAppId", "Main")
            fake = ini.get("FakeAppId", "Main")
            real_app_id = real
            fake_app_id = fake

            if name.lower() == "steamfix.ini" and not ini.has_section("OnlineFix Linux"):
                ini.set("RealAppId", fake, "Main")
                ini.set("RealAppId", real, "OnlineFix Linux")
                log_info("FreeTP patch applied!")

            if ini.get("ExtraProtection", "Misc") is not None:
                ini.set("ExtraProtection", "false", "Misc")

            ini.save()
            continue

        if _STEAMFIX_DLL.match(name):
            fix_path = os.path.dirname(file)
            continue

        if _PHOTON.match(name):
            parent = os.path.dirname(file)
            if os.path.isfile(os.path.join(parent, "Launcher.exe")) and not os.path.isfile(
                    os.path.join(parent, "Newtonsoft.Json.dll")):
                newton = [f for f in _walk_files(path)
                          if os.path.basename(f) == "Newtonsoft.Json.dll"]
                if not newton:
                    src = asset("Newtonsoft.Json", "Newtonsoft.Json.dll")
                    if os.path.isfile(src):
                        shutil.copy2(src, os.path.join(parent, "Newtonsoft.Json.dll"))
                else:
                    for lib in newton:
                        # skip if the path is itself a symlink (matches canonical check)
                        if os.path.islink(lib):
                            continue
                        dest = os.path.join(parent, os.path.basename(lib))
                        if not os.path.exists(dest):
                            try:
                                os.symlink(os.path.abspath(lib), dest)
                            except OSError:
                                pass
                log_info("Photon Launcher patch applied!")
                continue

        dll = os.path.splitext(name)[0].lower()
        if dll not in overrides:
            overrides += dll + ("=n,b;" if re.match(r"(?i)^win.*\.dll$", name) else "=n;")

    if overrides.endswith(";"):
        overrides = overrides[:-1]

    return {
        "overrides": overrides,
        "realAppId": real_app_id,
        "fakeAppId": fake_app_id,
        "fixPath": fix_path,
    }


def parse_banner(app_id: str):
    images = banners_dir()
    os.makedirs(images, exist_ok=True)
    image_path = os.path.join(images, f"{app_id}.jpg")
    log_info("Trying to fetch banner from akamai CDN")
    url = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=15) as response, open(image_path, "wb") as fh:
            shutil.copyfileobj(response, fh)
    except urllib.error.HTTPError as exc:
        log_error(f"Failed to fetch banner, status code - {exc.code}")
        try:
            os.remove(image_path)
        except OSError:
            pass
        return i18n._("BANNEREDITOR.FILE.FAILED") % f"{exc.reason} ({exc.code})"
    except Exception as exc:
        log_error(f"Failed to fetch banner - {exc}")
        try:
            os.remove(image_path)
        except OSError:
            pass
        return i18n._("BANNEREDITOR.FILE.FAILED") % str(exc)

    log_info("Banner fetched")
    return image_path


def read_app_id(path: str):
    """Steam app id of a game folder (``steam_appid.txt`` or the fix ini).

    OnlineFix releases ship ``steam_appid.txt`` next to the executable, which
    is the only hint about the real store app for folders without an
    ``OnlineFix.ini``/``steamfix.ini``.
    """
    candidates = []
    if path and os.path.isdir(path):
        candidates.append(os.path.join(path, "steam_appid.txt"))
        try:
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs
                           if not d.startswith(".")
                           and not _is_prefix_dir(d, os.path.join(root, d))]
                for name in files:
                    if name.lower() == "steam_appid.txt":
                        candidates.append(os.path.join(root, name))
                break
        except OSError:
            pass
    for candidate in candidates:
        try:
            with open(candidate, "r", encoding="utf-8", errors="replace") as fh:
                value = fh.read().strip().splitlines()[0].strip()
        except (OSError, IndexError):
            continue
        if value.isdigit():
            return value
    return None


def parse_avatar(app_id: str):
    """Fetch the game's store art and keep it as the launcher avatar.

    The exe icon is preferred (it is the game's own artwork), this is the
    fallback for folders whose executable carries no resources.
    """
    if not app_id:
        return None
    images = icons_dir()
    os.makedirs(images, exist_ok=True)
    image_path = os.path.join(images, f"avatar{app_id}.png")
    if os.path.isfile(image_path):
        return image_path
    log_info("Trying to fetch avatar from akamai CDN")
    for url in (f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/capsule_sm.png",
                f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=15) as response, open(image_path, "wb") as fh:
                shutil.copyfileobj(response, fh)
        except Exception as exc:
            log_error(f"Failed to fetch avatar - {exc}")
            try:
                os.remove(image_path)
            except OSError:
                pass
            continue
        log_info("Avatar fetched")
        return image_path
    return None


def _random_name() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(16))


def parse_icon(executable: str):
    tmp = "/tmp/OFME-icon"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    largest_file = None
    icons_path = tmp

    if os.path.isfile("/usr/bin/icoextract"):
        log_info("Using icoextract instead of 7zip")
        extractor = run(["icoextract", executable, os.path.join(tmp, "icon.ico")])
        largest_file = os.path.join(tmp, "icon.ico")
        icons_path = tmp
    else:
        seven = get_third_party("7zip")
        if not seven:
            return None
        extractor = run([seven, "-y", "x", executable, ".rsrc/ICON"], cwd=tmp)

    if not os.path.isdir(tmp) or not os.listdir(tmp) or extractor.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    if largest_file is None or not os.path.isfile(largest_file):
        candidates = []
        icon_dir = os.path.join(tmp, ".rsrc", "ICON")
        if os.path.isdir(icon_dir):
            for name in os.listdir(icon_dir):
                full = os.path.join(icon_dir, name)
                if os.path.isfile(full):
                    candidates.append((os.path.getsize(full), full))
        if not candidates:
            shutil.rmtree(tmp, ignore_errors=True)
            return None
        largest_file = max(candidates)[1]
        icons_path = icon_dir

    ext = os.path.splitext(largest_file)[1].lower().lstrip(".")
    if ext == "ico":
        if not os.path.isfile("/usr/bin/ffmpeg"):
            shutil.rmtree(tmp, ignore_errors=True)
            raise IOError(i18n._("FFMPEG.NOTFOUND"))
        converted = os.path.join(icons_path, os.path.splitext(os.path.basename(largest_file))[0] + ".png")
        run(["ffmpeg", "-y", "-i", largest_file, converted])
        largest_file = converted

    icons = icons_dir()
    os.makedirs(icons, exist_ok=True)
    icon_name = _random_name()
    icon_path = os.path.join(icons, icon_name)
    while os.path.isfile(icon_path):
        icon_name = _random_name()
        icon_path = os.path.join(icons, icon_name)

    shutil.copy2(largest_file, icon_path)
    shutil.rmtree(tmp, ignore_errors=True)
    return icon_path
