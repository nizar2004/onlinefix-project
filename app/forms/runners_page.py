"""Runners page — mirrors the reference Proton page.

Preferences groups: GE-Proton download (+ live progress), installed
runners list, running games (stop button) and a link to open the
compatibility tools folder.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
import tkinter as tk
import urllib.request

from .. import files_worker, icons, runtime
from ..process_util import open_path
from ..runtime import GLOBALS
from ..theme import *  # noqa: F401,F403 — tokens
from .. import theme as T
from ..widgets import (ActionRow, HeaderBar, PreferencesGroup, RoundedButton,
                       ScrollFrame, WindowControls, toast)

CHUNK = 128 * 1024


class RunnersPage(tk.Frame):
    def __init__(self, window):
        super().__init__(window.content, bg=WINDOW)
        self.window = window
        self.app = window.app
        self._icon_refs: dict[str, tk.PhotoImage] = {}

        self.header = HeaderBar(self, draggable=True)
        self.header.pack(fill="x")
        self.header.pack_start(RoundedButton(
            self.header, text="Refresh", height=34,
            image=self._icon("refresh", 15), compound="left",
            command=self.refresh))
        self.header.set_title("Runners")
        self.header.pack_end(WindowControls(
            self.header, bg=WINDOW,
            on_minimize=self.window.frameless.minimize,
            on_maximize=self.window.frameless.maximize,
            on_close=self.window._on_window_close))

        self.scroll = ScrollFrame(self, bg=WINDOW)
        self.scroll.pack(fill="both", expand=True)
        self._inner = self.scroll.inner

        self.progress_bar = None
        self.progress_label = None
        self.status_label = None
        self.kill_btn = None
        self._downloading = False

    # ------------------------------------------------------------------ refresh
    def refresh(self):
        for child in self._inner.winfo_children():
            child.destroy()
        self.progress_bar = None
        self.progress_label = None

        content = tk.Frame(self._inner, bg=WINDOW)
        content.pack(fill="x", padx=T.px(18), pady=(T.px(14), T.px(24)))

        # --- GE-Proton ---------------------------------------------------------
        install_group = PreferencesGroup(content, title="GE-Proton",
                                         description="Latest build from GloriousEggroll.")
        install_group.pack(fill="x")
        self.download_btn = RoundedButton(
            install_group.card, text="Download latest GE-Proton",
            image=self._icon("download", 15, color="#FFFFFF"),
            compound="left", variant="suggested", height=38,
            command=self._on_download)
        install_group.add(self.download_btn)

        progress_row = tk.Frame(install_group.card, bg=SURFACE)
        self.progress_label = tk.Label(progress_row, text="", bg=SURFACE,
                                       fg=MUTED, font=T.FONT_SM, anchor="w")
        self.progress_label.pack(anchor="w", padx=14, pady=(8, 2))
        bar = tk.Canvas(progress_row, width=T.px(380), height=T.px(6), bg=FIELD,
                        highlightthickness=0, bd=0)
        bar.pack(anchor="w", padx=14, pady=(0, 10))
        self.progress_bar = bar
        self.progress_row = progress_row
        progress_row.pack(fill="x")
        progress_row.pack_forget()   # revealed while downloading

        # --- installed runners --------------------------------------------------
        installed_group = PreferencesGroup(content, title="Installed runners")
        installed_group.pack(fill="x", pady=(18, 0))

        versions = files_worker.get_installed_protons()
        protons_path = self.app.launcher_settings.get_base_path_for("protons")
        if not versions:
            installed_group.add(ActionRow(
                installed_group.card, title="No Proton builds installed",
                subtitle="Download GE-Proton to run games, or install system Wine."))
        for name in versions:
            row = ActionRow(installed_group.card, title=name,
                            subtitle=os.path.join(protons_path, name))
            badge = ActionBadge(row, "Proton", tone="accent")
            row.add_suffix(badge)
            installed_group.add(row)
        if os.path.isfile("/usr/bin/wine"):
            row = ActionRow(installed_group.card, title="System Wine",
                            subtitle="/usr/bin/wine")
            badge = ActionBadge(row, "Wine", tone="muted")
            row.add_suffix(badge)
            installed_group.add(row)

        # --- running games -------------------------------------------------------
        kill_group = PreferencesGroup(
            content, title="Running games",
            description="Stop a game that is running right now.")
        kill_group.pack(fill="x", pady=(18, 0))

        self.status_label = tk.Label(kill_group.card, text="", bg=SURFACE,
                                     fg=MUTED, font=T.FONT_SM, anchor="w")
        self.status_label.pack(anchor="w", padx=14, pady=(8, 6))

        self.kill_btn = RoundedButton(
            kill_group.card, text="Stop running game processes",
            image=self._icon("stop", 15), compound="left",
            variant="destructive", height=38, command=self._on_kill)
        kill_group.add(self.kill_btn)
        self._update_running_state()

        # --- open folder ----------------------------------------------------------
        open_btn = RoundedButton(content, text="Open compatibilitytools.d",
                                 command=self._on_open_dir, height=38,
                                 variant="flat")
        open_btn.pack(anchor="center", pady=(T.px(18), 0))

    def _update_running_state(self):
        if self.status_label is None:
            return
        process = GLOBALS.get("currentGameProcess")
        name = GLOBALS.get("currentGameName")
        if process is not None:
            self.status_label.configure(text=f"{name or 'A game'} is running.")
            self.kill_btn.set_enabled(True)
        else:
            self.status_label.configure(
                text="No Wine or Proton process is running.")
            self.kill_btn.set_enabled(False)

    # ----------------------------------------------------------------- progress
    def show_progress(self, text: str, fraction: float):
        if self.progress_row is None:
            return
        self.progress_row.pack(fill="x")
        self.progress_label.configure(text=text)
        if self.progress_bar is not None:
            self.progress_bar.delete("all")
            w = T.px(380)
            self.progress_bar.create_rectangle(0, 0, w, T.px(6), fill=FIELD,
                                               outline="")
            if fraction > 0:
                fw = max(T.px(6), int(w * min(1.0, fraction)))
                self.progress_bar.create_rectangle(0, 0, fw, T.px(6), fill=PRIMARY,
                                                   outline="")

    def hide_progress(self):
        if self.progress_row is not None:
            try:
                self.progress_row.pack_forget()
            except Exception:
                pass

    # ----------------------------------------------------------------- actions
    def _on_download(self):
        if self._downloading:
            return
        url = GLOBALS.get("LatestProton")
        if not url or url == "fetching":
            toast(self, "Looking up the latest GE-Proton release…")
            return

        proton_path = self.app.launcher_settings.get_base_path_for("protons")
        try:
            os.makedirs(proton_path, exist_ok=True)
        except OSError:
            toast(self, "Cannot write to the Proton folder")
            return

        filename = os.path.basename(url.split("?")[0]) or "GE-Proton.tar.gz"
        destination = os.path.join(proton_path, filename)
        self._downloading = True
        self._download_url = url
        self._download_dest = destination
        self._download_partial = destination
        self._download_proton_path = proton_path
        self._cancel_download = threading.Event()
        self.download_btn.set_text("Cancel download")
        self.download_btn.set_command(self._on_cancel_download)
        self.progress_row.pack(fill="x")
        self.show_progress("Downloading…", 0.0)

        threading.Thread(target=self._download_worker, daemon=True).start()

    def _on_cancel_download(self):
        if getattr(self, "_cancel_download", None):
            self._cancel_download.set()

    def _download_worker(self):
        url = self._download_url
        destination = self._download_dest
        cancel = self._cancel_download

        def progress(fraction, text):
            runtime.ui_later(lambda: self.show_progress(text, fraction))

        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "OnlineFix-Linux-Launcher"})
            with urllib.request.urlopen(request, timeout=30) as response:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                last_time = time.time()
                last_bytes = 0
                with open(destination, "wb") as fh:
                    while True:
                        if cancel.is_set():
                            raise InterruptedError
                        chunk = response.read(CHUNK)
                        if not chunk:
                            break
                        fh.write(chunk)
                        done += len(chunk)
                        now = time.time()
                        if now - last_time >= 0.4:
                            speed = ((done - last_bytes)
                                     / (now - last_time) / 1e6)
                            last_time, last_bytes = now, done
                            fraction = done / total if total else 0.0
                            progress(fraction,
                                     f"Downloading {filename} "
                                     f"({speed:.1f} MB/s)")
            if cancel.is_set():
                raise InterruptedError
        except InterruptedError:
            self._cleanup_partial()
            runtime.ui_later(self._download_finished_cancelled)
            return
        except Exception as exc:
            runtime.log_error(f"Proton download failed - {exc}")
            self._cleanup_partial()
            runtime.ui_later(lambda: self._download_finished(
                False, str(exc)))
            return

        runtime.ui_later(lambda: self.show_progress("Unpacking…", -1))
        try:
            subprocess.run(["tar", "-xzf", filename],
                           cwd=self._download_proton_path,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        except Exception as exc:
            runtime.log_error(f"Failed to unpack Proton - {exc}")
        try:
            os.remove(destination)
        except OSError:
            pass
        self._download_partial = None
        runtime.ui_later(lambda: self._download_finished(True, ""))

    def _cleanup_partial(self):
        path = getattr(self, "_download_partial", None)
        self._download_partial = None
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass

    def _download_finished_cancelled(self):
        self._download_done()
        toast(self, "Download cancelled")

    def _download_finished(self, ok: bool, message: str):
        self._download_done()
        if ok:
            toast(self, "GE-Proton installed")
            self.refresh()
        else:
            toast(self, f"Install failed: {message}")

    def _download_done(self):
        self._downloading = False
        self.hide_progress()
        try:
            self.download_btn.set_text("Download latest GE-Proton")
            self.download_btn.set_command(self._on_download)
        except Exception:
            pass

    def _on_kill(self):
        self.window.stop_running_game()
        self._update_running_state()

    def _on_open_dir(self):
        open_path(self.app.launcher_settings.get_base_path_for("protons"))

    def _icon(self, name: str, size: int = 16, color: str | None = None):
        key = (name, size, str(color))
        if key not in self._icon_refs:
            self._icon_refs[key] = icons.icon(name, size, color=color)
        return self._icon_refs[key]


class ActionBadge(tk.Label):
    """A pill badge used as an ActionRow suffix."""

    def __init__(self, parent, text: str, tone: str = "accent"):
        bg, fg = ((T.ACCENT_DIM, T.ACCENT_SOFT) if tone == "accent"
                  else (T.SURFACE_2, T.FG_SOFT))
        super().__init__(parent, text=text, bg=bg, fg=fg, font=T.FONT_PILL,
                         padx=10, pady=3)
