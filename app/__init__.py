
"""OnlineFix Linux Launcher - Python port."""
from __future__ import annotations

import tkinter as tk


def bootstrap(root: tk.Tk) -> None:
    """Prepare a Tk root window for the launcher.

    Call once, right after creating the root, before building any UI.
    Idempotent — calling it twice is harmless.
    """
    from . import theme

    try:
        root.configure(bg=theme.BG)
    except Exception:
        pass

    theme.apply_ttk_style(root)

    try:
        # Default family for any raw tk widget that does not set a font.
        root.option_add("*Font", theme.FONT)
        root.option_add("*Background", theme.BG)
        root.option_add("*Foreground", theme.FG)
    except Exception:
        pass
