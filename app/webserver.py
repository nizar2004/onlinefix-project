"""Local HTTP server that serves the web UI and a small JSON API.

Only listens on 127.0.0.1.  Static files come from ``webui/``; the JSON
API bridges to :class:`app.webbridge.WebApp` (games, launch/stop,
settings helpers) and to the pywebview window (frameless controls).
"""
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .process_util import open_path, open_url
from .runtime import log_error, log_info

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBUI_DIR = os.path.join(BASE_DIR, "webui")
MAIN_PY = os.path.join(BASE_DIR, "main.py")

# Set by webapp.run_web() once the pywebview window exists.
window = None
ui_mode = "browser"  # or "pywebview"

_EXTRA_MIME = {
    ".woff2": "font/woff2",
    ".webp": "image/webp",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
}


def _spawn_tk_mode(mode: str, arg: str | None = None) -> dict:
    """Open one of the classic Tk windows in a separate process."""
    cmd = [sys.executable, MAIN_PY, mode]
    if arg:
        cmd.append(arg)
    try:
        subprocess.Popen(cmd, cwd=BASE_DIR, start_new_session=True)
        return {"ok": True}
    except OSError as exc:
        log_error(f"could not spawn {mode}: {exc}")
        return {"ok": False, "error": str(exc)}


class Handler(BaseHTTPRequestHandler):
    server_version = "OnlineFixWebUI/1.0"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------ utilities
    def log_message(self, fmt, *args):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str,
              cache: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control",
                         "public, max-age=86400" if cache else "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, payload, code: int = 200) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"),
                   "application/json")

    def _static(self, rel: str) -> None:
        rel = rel.lstrip("/")
        path = os.path.normpath(os.path.join(WEBUI_DIR, rel))
        if not path.startswith(WEBUI_DIR) or not os.path.isfile(path):
            self._json({"error": "not found"}, 404)
            return
        ctype, _ = mimetypes.guess_type(path)
        if path.endswith(".woff2"):
            ctype = "font/woff2"
        ctype = ctype or "application/octet-stream"
        # images/fonts are immutable enough to cache; code always revalidates
        cache = path.endswith((".png", ".jpg", ".jpeg", ".webp", ".svg",
                               ".woff2", ".ico"))
        with open(path, "rb") as fh:
            self._send(200, fh.read(), ctype, cache=cache)

    def _serve_image(self, query: str) -> None:
        """Serve a local image file (banners/icons referenced by Games.ini)."""
        path = (parse_qs(query).get("path") or [""])[0]
        if not path or not os.path.isfile(path):
            self._send(404, b"not found", "text/plain")
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".ico", ".bmp"):
            self._send(403, b"forbidden", "text/plain")
            return
        ctype = "image/png" if ext == ".png" else \
            "image/webp" if ext == ".webp" else \
            "image/x-icon" if ext == ".ico" else \
            "image/bmp" if ext == ".bmp" else "image/jpeg"
        with open(path, "rb") as fh:
            self._send(200, fh.read(), ctype, cache=True)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            pass
        return {}

    # -------------------------------------------------------------- routing
    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path
        backend = self.server.backend  # type: ignore[attr-defined]

        if route == "/api/games":
            self._json(backend.list_games())
        elif route == "/api/state":
            self._json({**backend.state(), "mode": ui_mode})
        elif route == "/api/banner":
            self._serve_image(parsed.query)
        elif route == "/api/icon":
            self._serve_image(parsed.query)
        elif route == "/" or route == "/index.html":
            self._static("index.html")
        elif route.startswith(("/css/", "/js/", "/assets/")):
            self._static(route)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        route = parsed.path
        backend = self.server.backend  # type: ignore[attr-defined]
        body = self._body()

        if route == "/api/launch":
            name = str(body.get("name") or "")
            ok = bool(name and backend.games.has_section(name))
            if not ok:
                self._json({"ok": False, "error": "unknown game"}, 400)
                return
            self._json(backend.launch(name, debug=bool(body.get("debug"))))
        elif route == "/api/stop":
            self._json(backend.stop())
        elif route == "/api/open":
            kind = body.get("kind")
            if kind == "url":
                open_url(str(body.get("target") or ""))
                self._json({"ok": True})
            else:
                open_path(str(body.get("target") or ""))
                self._json({"ok": True})
        elif route == "/api/add-game":
            self._json(_spawn_tk_mode("--add-game"))
        elif route == "/api/open-settings":
            self._json(_spawn_tk_mode("--tk"))
        elif route == "/api/game-settings":
            self._json(_spawn_tk_mode("--game-settings",
                                      str(body.get("name") or "")))
        elif route == "/api/window":
            self._json(self._window_action(str(body.get("action") or "")))
        else:
            self._json({"error": "not found"}, 404)

    def _window_action(self, action: str) -> dict:
        win = window
        if win is None:
            return {"ok": False, "error": "browser mode has no window handle"}
        try:
            if action == "minimize":
                win.minimize()
            elif action == "maximize":
                win.maximize()
            elif action == "restore":
                win.restore()
            elif action == "toggle-maximize":
                if getattr(win, "gui", None) and \
                        getattr(win.gui, "maximized", False):
                    win.restore()
                else:
                    win.maximize()
            elif action == "close":
                win.destroy()
            else:
                return {"ok": False, "error": "unknown action"}
            return {"ok": True}
        except Exception as exc:  # pragma: no cover
            log_error(f"window action failed: {exc}")
            return {"ok": False, "error": str(exc)}


def start_server(backend) -> tuple[ThreadingHTTPServer, int]:
    """Start the API + static server on a random localhost port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.backend = backend  # type: ignore[attr-defined]
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True,
                     name="ofll-web").start()
    log_info(f"web UI served on http://127.0.0.1:{port}/")
    return server, port
