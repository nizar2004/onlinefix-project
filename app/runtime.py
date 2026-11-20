"""Global runtime helpers: Tk thread marshalling and globals."""
from __future__ import annotations

import queue
import sys
import threading
import traceback
from queue import Empty
from typing import Any, Callable, Optional

GLOBALS: dict[str, Any] = {
    "version": "2.7.1",
    "LatestProton": None,
    "argv": [],
    "implicitDisableReason": None,
}

_root = None
APP = None


def set_root(root):
    global _root
    _root = root
    # start the main-thread drain loop for ui_later()
    try:
        root.after(50, lambda: _drain_ui_queue(root))
    except Exception:
        pass


def get_root():
    return _root


def set_app(app):
    global APP
    APP = app


def get_app():
    return APP


def ui_later(func: Callable, *args, **kwargs):
    """Run ``func`` on the Tk thread.

    Calls are pushed to a thread-safe queue that a repeating ``after``
    loop drains on the main thread.  (Scheduling ``after`` directly from
    a worker thread only works while ``mainloop()`` services Tcl's
    cross-thread event queue; the drain loop is reliable in every case
    and never touches Tk from another thread.)
    """
    _UI_QUEUE.put(lambda: func(*args, **kwargs))


_UI_QUEUE: "queue.Queue" = queue.Queue()


def _drain_ui_queue(root):
    """Main-thread drain loop for :func:`ui_later`."""
    try:
        while True:
            func = _UI_QUEUE.get_nowait()
            try:
                func()
            except Exception:
                log_error("ui_later callback failed:\n"
                          + traceback.format_exc())
    except Empty:
        pass
    try:
        if root.winfo_exists():
            root.after(50, lambda: _drain_ui_queue(root))
    except Exception:
        pass


def ui_call(func: Callable, *args, **kwargs) -> Any:
    """Run func on the Tk thread and wait for the result."""
    root = _root
    if root is None:
        return func(*args, **kwargs)
    if threading.current_thread() is threading.main_thread():
        return func(*args, **kwargs)
    done = threading.Event()
    box: dict[str, Any] = {}

    def wrapper():
        try:
            box["value"] = func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - diagnostics
            box["error"] = exc
        finally:
            done.set()

    root.after(0, wrapper)
    done.wait()
    if "error" in box:
        raise box["error"]
    return box.get("value")


def log(message: str):
    print(message, file=sys.stderr, flush=True)


def log_info(message: str):
    log("[INFO] " + message)


def log_warn(message: str):
    log("[WARN] " + message)


def log_error(message: str):
    log("[ERROR] " + message)


def log_exception(exc: BaseException):
    log("[ERROR] " + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
