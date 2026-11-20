
#!/usr/bin/env python3
"""OnlineFix Linux Launcher - Python port of the DevelNext/JPHP application.

Usage:
    ./onlinefix-linux-launcher            # open the game library
    ./onlinefix-linux-launcher "<game>"   # launch a game directly (shortcut)
"""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import dialogs, i18n, runtime, theme  # noqa: E402
from app.core import Application  # noqa: E402
from app.runtime import GLOBALS  # noqa: E402

PID_FILE = "/tmp/ofllpid"


def setup_styles(root: tk.Tk):
    # The Midnight design system styles the whole toolkit from the shared
    # tokens (see app/theme.py). This also calibrates `tk scaling`, resolves
    # the real UI font families now that a root exists, and seeds Tk's
    # option database (combobox listboxes, menus).
    theme.apply_ttk_style(root)


def running_pid() -> int | None:
    try:
        with open(PID_FILE, "r", encoding="utf-8", errors="replace") as fh:
            value = fh.read().strip()
        return int(value) if value else None
    except (OSError, ValueError):
        return None


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def write_pid():
    try:
        with open(PID_FILE, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
    except OSError as exc:
        runtime.log_warn(f"Failed to write PID to {PID_FILE} - {exc}")


def remove_pid():
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def report_callback_exception(exc_type, exc_value, exc_tb):
    runtime.log_error("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))


def main() -> int:
    if "--version" in sys.argv or "-V" in sys.argv:
        print(f"OnlineFix Linux Launcher {GLOBALS.get('version', '2.7.1')}")
        return 0

    root = tk.Tk(className="OnlineFixLauncher")
    root.withdraw()
    root.report_callback_exception = report_callback_exception
    runtime.set_root(root)
    setup_styles(root)

    app = Application(root, sys.argv)
    runtime.set_app(app)
    GLOBALS["argv"] = sys.argv

    game_name = sys.argv[1] if len(sys.argv) > 1 else None
    executable = app.games.get("executable", game_name) if game_name else None
    minimal_mode = bool(game_name and executable and os.path.isfile(executable))

    def on_close():
        try:
            if app.main_form is not None:
                app.main_form.close()
        finally:
            remove_pid()
            try:
                root.destroy()
            except Exception:
                pass

    root.protocol("WM_DELETE_WINDOW", on_close)

    if minimal_mode:
        if app.games.get("proton", game_name) == "GE-Proton Latest":
            app.fetch_latest_proton()
        app.show_form("gameStarting", game_name=game_name)
    else:
        pid = running_pid()
        if pid and pid != os.getpid() and pid_alive(pid):
            # A launcher is already running — ask it to come back up
            # (this is what the window's minimise button does) and exit.
            import signal
            import time as _time
            try:
                os.kill(pid, signal.SIGUSR1)
            except OSError:
                dialogs.show_message(root, i18n._("APPMODULE.PIDEXISTS") % pid, "ERROR")
            try:
                root.destroy()
            except Exception:
                pass
            return 0

        write_pid()
        app.show_form("MainForm")
        root.deiconify()
        root.lift()

        threading.Thread(target=app.fetch_latest_proton, daemon=True).start()
        threading.Thread(target=app.check_updates, daemon=True).start()

    try:
        root.mainloop()
    finally:
        remove_pid()
    return 0


if __name__ == "__main__":
    sys.exit(main())
