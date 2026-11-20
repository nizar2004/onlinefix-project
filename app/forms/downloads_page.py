"""Downloads page — browse online-fix.me inside the launcher and install.

A simple built-in browser (Back / Forward / Reload / Home + address
bar) over the download shelf: files land in the downloads folder and
can be installed straight into the library.
"""
from __future__ import annotations

import os
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request

from .. import i18n, icons, runtime
from ..process_util import open_path, open_url
from ..theme import *  # noqa: F401,F403 — tokens
from .. import theme as T
from ..widgets import (ActionRow, HeaderBar, IconButton, PreferencesGroup,
                       RoundedButton, ScrollFrame, WindowControls, tooltip,
                       toast)

CHUNK = 128 * 1024
HOME_URL = "https://online-fix.me/"
FILE_EXTS = (".rar", ".zip", ".7z", ".torrent", ".exe")

HOME_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body { background:#0C0C0E; color:#E8EAEE; font-family: sans-serif;
         display:flex; align-items:center; justify-content:center;
         height:95vh; margin:0; }
  .card { text-align:center; max-width:460px; }
  h1 { font-size:22px; margin:0 0 8px; }
  p { color:#747880; line-height:1.5; }
  a { display:inline-block; margin-top:18px; padding:10px 22px;
      border-radius:10px; background:#46586A; color:#FFFFFF;
      text-decoration:none; font-weight:600; }
  a:hover { background:#556A80; }
  .hint { font-size:11px; color:#4F5258; margin-top:16px; }
</style></head><body><div class="card">
  <h1>Download games</h1>
  <p>Use the address bar above to visit any game source.<br>
     Archives you download are listed below and can be installed
     straight into your library.</p>
  <a href="https://online-fix.me/">Open online-fix.me</a>
  <p class="hint">Only download games you legally own.</p>
</div></body></html>"""


class DownloadsPage(tk.Frame):
    def __init__(self, window):
        super().__init__(window.content, bg=WINDOW)
        self.window = window
        self.app = window.app
        self._downloads: dict[str, dict] = {}
        self._history: list[str] = []
        self._history_index = -1
        self._loading_home = False

        self._build_header()
        self._build_browser()
        self._build_shelf()

        self.show_home()

    # ------------------------------------------------------------------ header
    def _build_header(self):
        self.header = HeaderBar(self, draggable=True)
        self.header.pack(fill="x")

        self.back_btn = IconButton(self.header, image=icons.icon("back", 18),
                                   size=34, command=self._back)
        self.header.pack_start(self.back_btn, padx=(8, 0))
        # forward uses a mirrored back arrow
        self.fwd_btn = tk.Label(self.header, bg=WINDOW, cursor="hand2")
        self.fwd_btn.bind("<Button-1>", lambda _e: self._forward())
        self.header.pack_start(self.fwd_btn, padx=(2, 0))
        self.reload_btn = IconButton(self.header,
                                     image=icons.icon("refresh", 16),
                                     size=34, command=self._reload)
        self.header.pack_start(self.reload_btn, padx=(2, 0))
        self.home_btn = IconButton(self.header, image=icons.icon("home", 16),
                                   size=34, command=self.show_home)
        self.header.pack_start(self.home_btn, padx=(2, 0))
        self._sync_nav_buttons()

        self.url_entry = tk.Entry(
            self.header, bg=FIELD, fg=FG, insertbackground=FG,
            relief="flat", bd=0, font=T.FONT_SM, highlightthickness=1,
            highlightbackground=WINDOW, highlightcolor=ACCENT)
        self.header.set_title_widget(self.url_entry)
        self.url_entry.bind("<Return>", lambda _e: self._open_address())

        self.header.pack_end(WindowControls(
            self.header, bg=WINDOW,
            on_minimize=self.window.frameless.minimize,
            on_maximize=self.window.frameless.maximize,
            on_close=self.window._on_window_close))

        self.external_btn = IconButton(self.header,
                                       image=icons.icon("external", 16),
                                       size=34, command=self._open_externally)
        self.header.pack_end(self.external_btn)
        tooltip(self.external_btn, "Open in system browser")

        self.files_btn = RoundedButton(
            self.header, text="Files", height=34, radius=8,
            image=icons.icon("folder", 15), compound="left",
            command=self._toggle_shelf)
        self.header.pack_end(self.files_btn)
        tooltip(self.back_btn, "Back")
        tooltip(self.reload_btn, "Reload")
        tooltip(self.home_btn, "Home")
        tooltip(self.files_btn, "Show downloaded files")
    def _sync_nav_buttons(self):
        can_back = self._history_index > 0
        can_fwd = self._history_index < len(self._history) - 1
        try:
            self.back_btn.set_enabled(can_back)
        except Exception:
            pass
        self._paint_forward(can_fwd)

    def _paint_forward(self, enabled: bool):
        """Forward arrow = mirrored back arrow, dimmed when unavailable."""
        from PIL import Image, ImageTk
        img = icons.icon("back", 18,
                         color=T.STROKE if enabled else T.DIM)
        pil = ImageTk.getimage(img).transpose(Image.FLIP_LEFT_RIGHT)
        photo = ImageTk.PhotoImage(pil)
        self.fwd_btn.configure(image=photo)
        self.fwd_btn.image = photo
        self.fwd_btn._enabled = enabled
        self.fwd_btn.configure(cursor="hand2" if enabled else "arrow")

    # ----------------------------------------------------------------- browser
    def _build_browser(self):
        try:
            from tkinterweb import HtmlFrame
            self.browser = HtmlFrame(
                self, dark_theme_enabled=True, images_enabled=True,
                on_link_click=self._on_link_click,
                on_form_submit=self._on_form_submit)
        except Exception:
            self.browser = None
        if self.browser is not None:
            self.browser.pack(fill="both", expand=True)
        else:
            # graceful fallback when tkinterweb is unavailable
            self.browser = tk.Label(
                self, bg=WINDOW, fg=MUTED,
                text="The built-in browser is unavailable.\n"
                     "Install the 'tkinterweb' package to browse in-app.",
                justify="center")
            self.browser.pack(fill="both", expand=True)

    # ------------------------------------------------------------------- shelf
    def _build_shelf(self):
        self.shelf = tk.Frame(self, bg=SIDEBAR, height=T.px(240))
        self._shelf_visible = False

        head = tk.Frame(self.shelf, bg=SIDEBAR, height=T.px(40))
        head.pack(fill="x")
        head.pack_propagate(False)
        tk.Label(head, text="Downloads", bg=SIDEBAR, fg=FG,
                 font=T.FONT_SUBTITLE).pack(side="left", padx=(T.px(14), 0))
        self.shelf_dir = tk.Label(head, text="", bg=SIDEBAR, fg=MUTED,
                                  font=T.FONT_TINY)
        self.shelf_dir.pack(side="left", padx=(T.px(12), 0))
        RoundedButton(head, text="Open folder", height=28, radius=6,
                      font=T.FONT_SM, variant="flat",
                      command=lambda: open_path(self.download_dir())
                      ).pack(side="right", padx=(0, T.px(12)))

        self.shelf_list = ScrollFrame(self.shelf, bg=SIDEBAR)
        self.shelf_list.pack(fill="both", expand=True,
                             padx=T.px(10), pady=(0, T.px(8)))
        self.shelf.pack_forget()

    def _toggle_shelf(self):
        self._shelf_visible = not self._shelf_visible
        if self._shelf_visible:
            self.shelf.pack(fill="x", side="bottom")
            self.refresh_shelf()
        else:
            self.shelf.pack_forget()

    # ------------------------------------------------------------ navigation
    # The page HTML is fetched here (tkinterweb's own document fetcher is
    # unstable on some Python builds) and handed to the renderer, which
    # still loads images and stylesheets itself.
    USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

    def show_home(self):
        self._show_page(HOME_HTML, HOME_URL, push=True, home=True)

    def _open_address(self):
        text = self.url_entry.get().strip()
        if not text:
            return
        if "://" not in text:
            if " " in text or "." not in text:
                from urllib.parse import quote
                text = ("https://online-fix.me/index.php?do=search"
                        "&subaction=search&story=" + quote(text))
            else:
                text = "https://" + text
        self._go(text)

    def _go(self, url: str, push: bool = True):
        self._set_loading(True)
        def worker():
            try:
                request = urllib.request.Request(url, headers={
                    "User-Agent": self.USER_AGENT})
                with urllib.request.urlopen(request, timeout=20) as response:
                    raw = response.read()
                    final_url = response.geturl()
                    ctype = (response.headers.get("Content-Type") or "")
                charset = "utf-8"
                if "charset=" in ctype:
                    charset = ctype.split("charset=")[1].split(";")[0].strip()
                try:
                    html = raw.decode(charset, errors="replace")
                except LookupError:
                    html = raw.decode("utf-8", errors="replace")
                runtime.ui_later(lambda: self._show_page(html, final_url, push))
            except Exception as exc:
                runtime.log_error(f"browser fetch failed: {exc}")
                runtime.ui_later(lambda: self._show_error(url, exc))
        threading.Thread(target=worker, daemon=True).start()

    def _show_page(self, html: str, url: str, push: bool = True,
                   home: bool = False):
        self._set_loading(False)
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, url)
        if push:
            self._history = self._history[:self._history_index + 1]
            self._history.append(url)
            self._history_index = len(self._history) - 1
        self._sync_nav_buttons()
        try:
            self.browser.load_html(html, base_url=url)
        except Exception:
            self.browser.load_html(html)

    def _show_error(self, url: str, exc: Exception):
        self._set_loading(False)
        safe = (str(exc)).replace("<", "&lt;").replace("&", "&amp;")
        pretty = url.replace("<", "&lt;").replace("&", "&amp;")
        self._show_page(
            f"<html><body style='background:#0C0C0E;color:#E8EAEE;"
            f"font-family:sans-serif;padding:40px'>"
            f"<h2>Could not load this page</h2>"
            f"<p style='color:#747880'>{safe}</p>"
            f"<p style='color:#747880'>{pretty}</p>"
            f"<p><a href='{url}' style='color:#9FB2C4'>Try again</a></p>"
            f"</body></html>", url, push=False)

    def _set_loading(self, loading: bool):
        try:
            self.url_entry.configure(fg=MUTED if loading else FG)
        except Exception:
            pass

    def _back(self):
        if self._history_index > 0:
            self._history_index -= 1
            self._go(self._history[self._history_index], push=False)

    def _forward(self):
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._go(self._history[self._history_index], push=False)

    def _reload(self):
        url = self.url_entry.get().strip()
        if url:
            self._go(url, push=False)

    def _open_externally(self):
        url = self.url_entry.get().strip()
        if url:
            open_url(url)

    def _on_form_submit(self, url: str, data: str, method: str):
        if method.upper() == "GET" and data:
            self._go(url + ("&" if "?" in url else "?") + data)
        else:
            self._go(url)

    def _on_link_click(self, url: str):
        if not url:
            return
        lower = url.lower().split("?")[0]
        if lower.endswith(FILE_EXTS):
            self._start_url_download(url)
            return
        self._go(url)

    # ------------------------------------------------------------- downloads
    def refresh_shelf(self):
        for child in self.shelf_list.inner.winfo_children():
            child.destroy()

        save_dir = self.download_dir()
        os.makedirs(save_dir, exist_ok=True)
        self.shelf_dir.configure(text=save_dir)

        for name, item in list(self._downloads.items()):
            self.shelf_list.inner.pack_propagate(True)
            group_card = tk.Frame(self.shelf_list.inner, bg=CARD)
            group_card.pack(fill="x", pady=1)
            self._live_row(group_card, name, item)

        files = self._list_files(save_dir)
        for path in files:
            row = tk.Frame(self.shelf_list.inner, bg=CARD)
            row.pack(fill="x", pady=1)
            self._file_row(row, path)

        if not files and not self._downloads:
            tk.Label(self.shelf_list.inner, text="No downloads yet",
                     bg=SIDEBAR, fg=DIM, font=T.FONT_SM).pack(pady=T.px(18))

    def _list_files(self, folder: str) -> list[str]:
        try:
            names = sorted(
                (n for n in os.listdir(folder)
                 if os.path.isfile(os.path.join(folder, n))
                 and not n.startswith(".")),
                key=lambda n: -os.path.getmtime(os.path.join(folder, n)))
        except OSError:
            return []
        return [os.path.join(folder, n) for n in names
                if time.time() - os.path.getmtime(os.path.join(folder, n)) > 2]

    def _file_row(self, parent, path: str):
        name = os.path.basename(path)
        try:
            size = os.path.getsize(path) / (1024 * 1024)
            subtitle = f"{size:.1f} MB" if size >= 1 else f"{int(size * 1024)} KB"
        except OSError:
            subtitle = path

        row = ActionRow(parent, title=name, subtitle=subtitle)
        ext = os.path.splitext(name)[1].lower()
        if ext in (".rar", ".zip", ".7z"):
            row.add_suffix(RoundedButton(
                row.suffix_box, text="Install", variant="suggested", height=30,
                padx=10, pady=3, font=T.FONT_SM, radius=6,
                command=lambda p=path: self._install(p)))
        row.add_suffix(RoundedButton(
            row.suffix_box, text="Folder", variant="flat", height=30,
            padx=10, pady=3, font=T.FONT_SM, radius=6,
            command=lambda p=path: open_path(os.path.dirname(p))))
        return row

    def _live_row(self, parent, name: str, item: dict):
        row = ActionRow(parent, title=name, subtitle="Downloading…")
        bar = tk.Canvas(row.suffix_box, width=T.px(140), height=T.px(6),
                        bg=FIELD, highlightthickness=0, bd=0)
        bar.pack(side="left", padx=(T.px(6), 0))
        self._draw_progress(bar, item.get("fraction", 0.0))
        item["bar"] = bar
        row.add_suffix(RoundedButton(
            row.suffix_box, text="Cancel", variant="flat", height=30,
            padx=10, pady=3, font=T.FONT_SM, radius=6,
            command=lambda n=name: self._cancel(n)))
        return row

    @staticmethod
    def _draw_progress(bar: tk.Canvas, fraction: float):
        bar.delete("all")
        w = T.px(140)
        bar.create_rectangle(0, 0, w, T.px(6), fill=FIELD, outline="")
        if fraction > 0:
            fw = max(T.px(6), int(w * fraction))
            bar.create_rectangle(0, 0, fw, T.px(6), fill=PRIMARY, outline="")

    # ---------------------------------------------------------------- actions
    def download_dir(self) -> str:
        """The configured downloads folder."""
        settings = self.app.launcher_settings
        path = self.app.launcher.get("downloadsPath", "User Settings") or ""
        if not path:
            path = settings.get_base_path_for("downloads")
        return path

    def _start_url_download(self, url: str = ""):
        url = url or self.url_entry.get().strip()
        if not url:
            toast(self, "Paste a link first")
            return
        if "://" not in url:
            url = "https://" + url
        name = os.path.basename(url.split("?")[0]) or f"download-{int(time.time())}"
        dest = os.path.join(self.download_dir(), name)
        if name in self._downloads:
            toast(self, "Already downloading that file")
            return

        item = {"fraction": 0.0, "cancel": threading.Event(), "url": url,
                "dest": dest}
        self._downloads[name] = item
        if not self._shelf_visible:
            self._toggle_shelf()
        else:
            self.refresh_shelf()
        toast(self, f"Downloading {name}…")
        threading.Thread(target=self._worker, args=(name, item),
                         daemon=True).start()

    def _worker(self, name: str, item: dict):
        url, dest = item["url"], item["dest"]
        cancel: threading.Event = item["cancel"]

        def progress(fraction, _text):
            item["fraction"] = fraction
            self._update_bar(name, fraction)

        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) OnlineFix-Linux-Launcher"})
            with urllib.request.urlopen(request, timeout=30) as response:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                with open(dest + ".part", "wb") as fh:
                    while True:
                        if cancel.is_set():
                            break
                        chunk = response.read(CHUNK)
                        if not chunk:
                            break
                        fh.write(chunk)
                        done += len(chunk)
                        fraction = done / total if total else 0.0
                        progress(fraction, "")
            if cancel.is_set():
                if os.path.exists(dest + ".part"):
                    os.remove(dest + ".part")
                runtime.ui_later(lambda: self._finish(name, False, "Cancelled"))
                return
            os.replace(dest + ".part", dest)
            runtime.ui_later(lambda: self._finish(name, True, dest))
        except (urllib.error.URLError, OSError) as exc:
            if os.path.exists(dest + ".part"):
                try:
                    os.remove(dest + ".part")
                except OSError:
                    pass
            runtime.ui_later(lambda: self._finish(name, False, str(exc)))

    def _update_bar(self, name: str, fraction: float):
        def update():
            item = self._downloads.get(name)
            if item and item.get("bar") is not None:
                try:
                    self._draw_progress(item["bar"], fraction)
                except Exception:
                    pass
        runtime.ui_later(update)

    def _finish(self, name: str, ok: bool, detail):
        self._downloads.pop(name, None)
        toast(self.window.win, f"Download finished: {name}" if ok
              else f"Download failed: {detail}",
              tone="success" if ok else "error")
        if self._shelf_visible:
            self.refresh_shelf()

    def _cancel(self, name: str):
        item = self._downloads.get(name)
        if item:
            item["cancel"].set()

    def _install(self, path: str):
        """Hand the archive to the add-game wizard (rar → exe → library)."""
        if not os.path.isfile(path):
            toast(self, "File is missing")
            return
        configurator = self.app.show_form("newGameConfigurator", new=True)
        configurator.parse_from_rar(path)
