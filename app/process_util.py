"""Small process / desktop helpers used across the launcher."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from typing import Optional


def which(program: str) -> Optional[str]:
    return shutil.which(program)


@lru_cache(maxsize=32)
def xdg_user_dir(name: str) -> str:
    home = os.path.expanduser("~")
    defaults = {
        "DESKTOP": os.path.join(home, "Desktop"),
        "DOWNLOAD": os.path.join(home, "Downloads"),
        "DOCUMENTS": os.path.join(home, "Documents"),
    }
    try:
        out = subprocess.run(["xdg-user-dir", name], capture_output=True, text=True, timeout=5)
        value = (out.stdout or "").strip()
        if value:
            return value
    except Exception:
        pass
    return defaults.get(name.upper(), home)


def open_path(path: str):
    try:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception:
        pass


def open_url(url: str):
    try:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception:
        pass


def popen(args, cwd: Optional[str] = None, env: Optional[dict] = None) -> subprocess.Popen:
    full_env = os.environ.copy()
    if env:
        for key, value in env.items():
            if isinstance(value, bool):
                value = "1" if value else "0"
            full_env[str(key)] = str(value) if value is not None else ""
    return subprocess.Popen(
        args,
        cwd=cwd,
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        bufsize=1,
        start_new_session=True,
    )


def run(args, cwd: Optional[str] = None, env: Optional[dict] = None,
        timeout: Optional[float] = None) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    if env:
        full_env.update({str(k): str(v) for k, v in env.items() if v is not None})
    return subprocess.run(
        args, cwd=cwd, env=full_env, capture_output=True, text=True,
        errors="replace", timeout=timeout,
    )


def hook_process_outputs(process: subprocess.Popen, debug: bool = False,
                         line_callback=None):
    """Read stdout/stderr of a process in threads and optionally forward lines."""
    import threading

    def reader(stream, tag):
        try:
            for line in iter(stream.readline, ""):
                line = line.rstrip("\n")
                print(f"{line}", file=sys.stderr, flush=True)
                if debug and line_callback:
                    line_callback(tag, line)
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    threading.Thread(target=reader, args=(process.stdout, "OUT"), daemon=True).start()
    threading.Thread(target=reader, args=(process.stderr, "ERR"), daemon=True).start()


def wait_for_process(process: subprocess.Popen) -> int:
    while process.poll() is None:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            continue
    return process.returncode if process.returncode is not None else -1
