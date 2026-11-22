"""Web-UI entry point: local server + pywebview window (Chrome fallback).

Native-app behaviours implemented here:
  * single instance — a second launch raises the open window instead of
    starting a new one (unix socket based, no root needed)
  * X11 backend — GTK3's Wayland backend ignores ``set_decorated(False)``
    (KWin then draws its own server-side titlebar); XWayland honours it
    and the design's frameless look survives
  * proper window icon / WM class
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from shutil import which

from . import webserver
from .webbridge import WebApp
from .runtime import GLOBALS, log_error, log_info

WINDOW_W = 1380
WINDOW_H = 880
APP_ICON = os.path.join(webserver.BASE_DIR, "webui", "assets", "img",
                        "steam.svg")
SOCK_PATH = f"/tmp/ofllweb-{os.getuid()}.sock"


def _browser_fallback(url: str) -> int:
    """Open the UI in a Chrome/Chromium app window (or default browser)."""
    for binary, flags in (
        ("google-chrome-stable", ["--app=" + url, "--window-size=1400,920"]),
        ("chromium", ["--app=" + url, "--window-size=1400,920"]),
        ("brave", ["--app=" + url, "--window-size=1400,920"]),
    ):
        path = which(binary)
        if path:
            log_info(f"opening {url} in {binary}")
            subprocess.Popen([path, *flags], start_new_session=True)
            # keep serving while the tab lives
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                return 0
    log_info("no chrome found — opening the default browser")
    subprocess.Popen(["xdg-open", url], start_new_session=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


def _bind_listener() -> socket.socket | None:
    """Bind the raise-socket; None means another instance owns it."""
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(SOCK_PATH)
    except OSError:
        listener.close()
        return None
    listener.listen(4)
    return listener


def _start_raise_listener(listener: socket.socket) -> None:
    """Unix-socket listener: another instance tells us to come up."""
    import threading

    def worker() -> None:
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            try:
                conn.recv(16)
            except OSError:
                pass
            conn.close()
            win = webserver.window
            try:
                if win is not None:
                    win.restore()
                    win.show()
                    win.on_top = True
                    win.on_top = False
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True,
                     name="ofll-raise").start()


def _raise_existing() -> bool:
    """True when another instance was found and told to raise."""
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(SOCK_PATH)
        client.sendall(b"raise")
        client.close()
        return True
    except OSError:
        client.close()
        # stale socket file
        try:
            os.unlink(SOCK_PATH)
        except OSError:
            pass
        return False


def run_web(argv: list[str]) -> int:
    listener = _bind_listener()
    if listener is None:
        # socket owned by a running instance — ask it to raise itself
        _raise_existing()
        log_info("another instance is already running — raising it")
        return 0

    backend = WebApp()
    server, port = webserver.start_server(backend)
    url = f"http://127.0.0.1:{port}/"
    GLOBALS["webUrl"] = url

    # GTK3 only honours set_decorated(False) reliably on X11; on native
    # Wayland, KWin re-adds its titlebar and the frameless design is gone.
    os.environ.setdefault("GDK_BACKEND", "x11")

    try:
        import webview  # pywebview
    except Exception as exc:
        log_error(f"pywebview unavailable ({exc}) — falling back to browser")
        return _browser_fallback(url)

    webserver.ui_mode = "pywebview"
    web = webview.create_window(
        "OnlineFix Launcher",
        url=url,
        width=WINDOW_W,
        height=WINDOW_H,
        min_size=(1080, 660),
        frameless=True,
        easy_drag=False,
        focus=True,
        background_color="#141415",
    )
    webserver.window = web
    _start_raise_listener(listener)

    try:
        webview.start(private_mode=False,
                      icon=APP_ICON if os.path.isfile(APP_ICON) else None)
    except Exception as exc:
        log_error(f"pywebview failed ({exc}) — falling back to browser")
        webserver.ui_mode = "browser"
        webserver.window = None
        try:
            web.destroy()
        except Exception:
            pass
        return _browser_fallback(url)
    finally:
        try:
            os.unlink(SOCK_PATH)
        except OSError:
            pass
    return 0