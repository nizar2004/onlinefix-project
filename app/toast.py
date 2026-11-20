"""Non-blocking toast notifications — Adwaita style.

A rounded pill anchored to the bottom-center of the window (like an
Adw.Toast): dark surface, white text, gentle fade. Never steals focus.
"""
from __future__ import annotations

import tkinter as tk

from . import theme as T

__all__ = ["show_toast"]


def show_toast(parent: tk.Misc, text: str, tone: str = "info",
               duration: int = 3000) -> None:
    """Show a temporary toast anchored to the bottom-center of ``parent``.

    Parameters
    ----------
    parent
        Any Tk widget — the toast will position itself relative to that
        widget's screen bounds.
    text
        Message. Wraps at ~420px.
    tone
        ``info`` or ``success`` / ``warning`` / ``error`` (coloured dot).
    duration
        Milliseconds before the fade-out starts.
    """
    try:
        dot = {"success": T.SUCCESS, "warning": T.WARNING,
               "error": T.DANGER}.get(tone)
        bg = T.SURFACE

        toast = tk.Toplevel(parent)
        toast.overrideredirect(True)
        toast.configure(bg=bg, highlightthickness=1,
                        highlightbackground=T.BORDER)

        body = tk.Frame(toast, bg=bg)
        body.pack(fill="both", expand=True, padx=6, pady=6)
        if dot:
            tk.Label(body, text="●", bg=bg, fg=dot,
                     font=T.FONT_TINY).pack(side="left", padx=(10, 2))
        tk.Label(toast, text=text, bg=bg, fg=T.FG,
                 font=T.FONT_BODY, justify="left",
                 wraplength=420, padx=(14 if dot else 18), pady=10).pack()

        # position relative to the parent widget's screen rect
        parent.update_idletasks()
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
        except Exception:
            px = py = 0
            pw = toast.winfo_screenwidth()
            ph = toast.winfo_screenheight()

        toast.update_idletasks()
        tw = toast.winfo_width()
        th = toast.winfo_height()
        x = max(8, px + (pw - tw) // 2)
        y = max(8, py + ph - th - 42)
        toast.geometry(f"+{x}+{y}")

        # slide up slightly, then fade out
        def _slide_up(step: int = 0):
            if step >= 6:
                return
            try:
                toast.geometry(f"+{x}+{y + (6 - step) * 2}")
            except Exception:
                pass
            toast.after(16, _slide_up, step + 1)

        def _fade(step: float = 1.0):
            if step <= 0:
                try:
                    toast.destroy()
                except Exception:
                    pass
                return
            try:
                toast.attributes("-alpha", step)
            except Exception:
                pass
            toast.after(30, _fade, step - 0.08)

        try:
            toast.attributes("-alpha", 1.0)
        except Exception:
            pass

        _slide_up()
        toast.after(duration, _fade)
    except Exception:
        # Never let feedback break the app.
        pass
