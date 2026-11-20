"""protonDownloader port — Midnight edition.

A compact dark progress card: quiet label, slim animated violet bar.
The download / unpack / cancel logic is unchanged.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request

from .. import assets, dialogs, i18n, runtime
from ..process_util import xdg_user_dir
from ..runtime import GLOBALS
from .. import theme as T
from ..theme import PRIMARY, WINDOW, FIELD, MUTED, FG
from ..theme import font as _font
from ..widgets import round_rect

CHUNK = 128 * 1024


class ProtonDownloader:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("Proton")
        self.win.configure(bg=WINDOW)
        self.win.geometry(f"{T.px(410)}x{T.px(104)}")
        self.win.resizable(False, False)
        self.win.transient(app.root)

        self.label = tk.Label(self.win, text=i18n._("PROTONDOWNLOADER.DOWNLOADING"),
                              bg=WINDOW, fg=FG, font=_font(12, True),
                              anchor="w")
        self.label.place(x=T.px(24), y=T.px(18), width=T.px(362), height=T.px(20))

        self.progress = tk.Canvas(self.win, width=T.px(362), height=T.px(8), bg=WINDOW,
                                  highlightthickness=0, bd=0)
        self.progress.place(x=T.px(24), y=T.px(54))
        self._progress_value = 0.0
        self._indeterminate = False
        self._indicator_pos = 0
        self._animation_job = None
        self._draw_progress()

        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._partial_file: str | None = None
        self._closed = False

        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self.win.bind("<Escape>", lambda e: self.hide())

    # ------------------------------------------------------------- drawing
    def _draw_progress(self):
        self.progress.delete("all")
        round_rect(self.progress, 0, 0, 361, 7, 3, fill=FIELD, outline=FIELD)
        if self._indeterminate:
            width = 90
            x = self._indicator_pos
            if x < -width:
                x = 362
            self._indicator_pos = x - 6
            if self._indicator_pos < -width:
                self._indicator_pos = 362
            round_rect(self.progress, x, 1, x + width, 6, 2,
                       fill=PRIMARY, outline=PRIMARY)
        elif self._progress_value > 0:
            fill_width = max(8, int(358 * self._progress_value / 100))
            round_rect(self.progress, 2, 1, 2 + fill_width, 6,
                       min(2, fill_width // 2), fill=PRIMARY, outline=PRIMARY)

    def _animate(self):
        if self._closed or not self._indeterminate:
            return
        self._draw_progress()
        try:
            self._animation_job = self.win.after(45, self._animate)
        except Exception:
            pass

    def set_progress(self, value: float):
        self._indeterminate = value < 0
        if value >= 0:
            self._progress_value = max(0.0, min(100.0, value))
            self._draw_progress()
        else:
            self._draw_progress()
            self._animate()

    # ------------------------------------------------------------- download
    def start_download(self, name: str, url: str | None):
        proton_path = self.app.launcher_settings.get_base_path_for("protons")
        try:
            os.makedirs(proton_path, exist_ok=True)
        except OSError:
            proton_path = ""

        if not url or not os.path.isdir(proton_path):
            dialogs.show_message(
                self.win,
                i18n._("PROTONDOWNLOADER.NOURL") if not url
                else i18n._("PROTONDOWNLOADER.NOPATH"),
                "ERROR",
            )
            self.win.after(30, self.hide)
            return

        self.win.title(name)
        self.label.configure(text=i18n._("PROTONDOWNLOADER.DOWNLOADING") + " (0.0MB/s)")
        self._progress_value = 0
        self._indeterminate = False
        self._draw_progress()

        filename = os.path.basename(url.split("?")[0]) or f"{name}.tar.gz"
        destination = os.path.join(proton_path, filename)
        self._partial_file = destination
        self._cancel.clear()

        def worker():
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "OnlineFix-Linux-Launcher"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    total = int(response.headers.get("Content-Length") or 0)
                    downloaded = 0
                    last_time = time.time()
                    last_bytes = 0
                    with open(destination, "wb") as fh:
                        while True:
                            if self._cancel.is_set():
                                raise InterruptedError
                            chunk = response.read(CHUNK)
                            if not chunk:
                                break
                            fh.write(chunk)
                            downloaded += len(chunk)
                            now = time.time()
                            if now - last_time >= 0.4:
                                speed = (downloaded - last_bytes) / (now - last_time) / 1e6
                                last_time, last_bytes = now, downloaded
                                if total:
                                    percent = downloaded / total * 100
                                    runtime.ui_later(self.set_progress, percent)
                                runtime.ui_later(
                                    lambda t=(f"{i18n._('PROTONDOWNLOADER.DOWNLOADING')} "
                                              f"({speed:.2f}MB/s)"):
                                    self.label.configure(text=t)
                                )
                if self._cancel.is_set():
                    raise InterruptedError
            except InterruptedError:
                self._cleanup_partial()
                return
            except Exception as exc:
                runtime.log_error(f"Proton download failed - {exc}")
                self._cleanup_partial()
                runtime.ui_later(self._download_failed)
                return

            runtime.ui_later(lambda: self.label.configure(
                text=i18n._("PROTONDOWNLOADER.UNPACKING")))
            runtime.ui_later(self.set_progress, -1)

            if not os.path.isfile("/usr/bin/tar"):
                runtime.ui_later(lambda: dialogs.show_message(
                    self.win, i18n._("PROTONDOWNLOADER.NOTAR"), "ERROR"))
                self._cleanup_partial()
                runtime.ui_later(self.hide)
                return

            try:
                subprocess.run(["tar", "-xzf", filename], cwd=proton_path,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as exc:
                runtime.log_error(f"Failed to unpack Proton - {exc}")
            try:
                os.remove(destination)
            except OSError:
                pass
            self._partial_file = None
            runtime.ui_later(self.hide)

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
        self.win.lift()
        self.win.focus_force()

    def _download_failed(self):
        dialogs.show_message(self.win, i18n._("PROTONDOWNLOADER.ERRORDOWNLOADING"),
                             "ERROR")
        self.hide()

    def _cleanup_partial(self):
        path = self._partial_file
        self._partial_file = None
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass

    # ----------------------------------------------------------------- misc
    def wait_until_closed(self):
        try:
            self.win.wait_window()
        except Exception:
            pass

    def hide(self):
        if self._closed:
            return
        self._closed = True
        self._cancel.set()
        self._indeterminate = False
        if self._animation_job:
            try:
                self.win.after_cancel(self._animation_job)
            except Exception:
                pass
            self._animation_job = None
        self._cleanup_partial()
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass

    def show(self):
        self.win.deiconify()
