"""Design tokens for the OnlineFix Linux Launcher.

The look mirrors the reference OnlineFix Launcher (GTK4 / libadwaita dark
style): flat neutral-dark surfaces, a violet identity accent used for the
logo and accent pills, and a muted slate "suggested action" colour for
primary buttons.

**KDE integration** — on a Plasma desktop the palette is *derived* from
the active KDE colour scheme (see :mod:`app.kde_theme`), the system
accent colour is honoured, and every metric and font size is multiplied
by the display scale factor, so the launcher looks and sizes itself
like a native KDE application.  When no KDE settings are found the
reference palette below is used unchanged.

Font sizes are **pixels** (negative Tk sizes) so they match the CSS
pixel sizes used by the reference application exactly.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Reference palette (used as the fallback when KDE settings are unavailable)
# ---------------------------------------------------------------------------
WINDOW         = "#222226"   # app canvas / content area
SIDEBAR        = "#2E2E32"   # sidebar rail
SIDEBAR_ACTIVE = "#424246"   # selected nav row
SIDEBAR_LINE   = "#1D1D22"   # hairline between sidebar and content
CARD           = "#333337"   # boxed-list cards / raised rows
CARD_HOVER     = "#3A3A3F"
FIELD          = "#38383B"   # entries, secondary buttons, headerbar controls
FIELD_HOVER    = "#424247"

BG           = WINDOW
BG_SOFT      = SIDEBAR
SURFACE      = CARD
SURFACE_2    = FIELD
SURFACE_3    = FIELD_HOVER

BORDER       = "#3D3D42"   # hairline dividers
BORDER_SOFT  = "#2C2C30"   # subtle separation inside a surface

FG           = "#FFFFFF"   # primary text
FG_SOFT      = "#DBDEE3"   # body text
MUTED        = "#94969B"   # labels, captions, secondary text
DIM          = "#727275"   # disabled / tertiary text

ACCENT       = "#5C7186"   # identity accent (dark steel)
ACCENT_HOVER = "#6B8299"
ACCENT_DIM   = "#23282E"   # accent-tinted fill
ACCENT_SOFT  = "#9FB2C4"

PRIMARY      = "#46586A"   # suggested action (dark slate)
PRIMARY_HOVER = "#556A80"

LIGHT        = "#DFE4E8"   # light action — Save / Next
LIGHT_HOVER  = "#EAEEF1"
LIGHT_FG     = "#1B1D21"

SUCCESS      = "#33D17A"
SUCCESS_BG   = "#1F3329"
WARNING      = "#F5B84D"
WARNING_BG   = "#3A301B"
DANGER       = "#E5807A"   # destructive text
DANGER_HOVER = "#EE918B"
DANGER_BG    = "#433335"   # destructive button fill

STROKE       = "#C8CFDD"   # icon / label colour used by the reference
COVER_PLACEHOLDER = "#20242E"   # card cover placeholder background
BACKDROP     = "#0C0C0F"   # dimmed backdrop behind modal dialogs

INK          = PRIMARY
INK_HOVER    = PRIMARY_HOVER


# ---------------------------------------------------------------------------
# Backwards-compatible aliases
# ---------------------------------------------------------------------------
BG_HOVER     = SURFACE_3
INPUT_BG     = FIELD
BUTTON       = FIELD
BUTTON_HOVER = FIELD_HOVER
PANEL        = CARD
PANEL_2      = SIDEBAR
TEXT         = FG
TEXT_SOFT    = FG_SOFT
TEXT_MUTED   = MUTED
TEXT_DIM     = DIM


# ---------------------------------------------------------------------------
# Display scale (KDE reports 1.5 on a 150% desktop, for example)
# ---------------------------------------------------------------------------
SCALE: float = 1.0
IS_DARK: bool = True
KDE_ACTIVE: bool = False
KDE_SCHEME: str = ""


def px(value: float) -> int:
    """Scale a logical pixel size to the display scale factor."""
    return int(round(value * SCALE))


def _hex(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _mix(a: str, b: str, amount: float) -> str:
    """Blend colour ``a`` toward ``b`` by ``amount`` (0..1)."""
    ra, ga, ba = _hex(a)
    rb, gb, bb = _hex(b)
    r = int(ra + (rb - ra) * amount)
    g = int(ga + (gb - ga) * amount)
    b = int(ba + (bb - ba) * amount)
    return f"#{r:02X}{g:02X}{b:02X}"


def _luminance(color: str) -> float:
    r, g, b = _hex(color)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def _saturation(color: str) -> float:
    r, g, b = (v / 255.0 for v in _hex(color))
    mx, mn = max(r, g, b), min(r, g, b)
    return 0.0 if mx == 0 else (mx - mn) / mx


# ---------------------------------------------------------------------------
# Spacing scale (multiples of 4)
# ---------------------------------------------------------------------------
SP_XS = 4
SP_SM = 8
SP_MD = 14
SP_LG = 18
SP_XL = 24
SP_2XL = 36


# ---------------------------------------------------------------------------
# Corner radii
# ---------------------------------------------------------------------------
RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 14
RADIUS_PILL = 999


# ---------------------------------------------------------------------------
# Metrics taken from the reference application
# ---------------------------------------------------------------------------
HEADER_H = 46          # Adw.HeaderBar height
BUTTON_H = 34          # default button height
NAV_ROW_H = 64         # Adw.ActionRow height in the sidebar
SIDEBAR_MIN = 216
SIDEBAR_MAX = 240
COVER_W, COVER_H = 150, 225   # game card cover
CARD_PAD = 6           # .game-card padding
FLOW_COL_GAP = 14
FLOW_ROW_GAP = 16


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
# The reference is a GTK4/libadwaita app: it uses the Adwaita Sans family
# and pixel font sizes.  We mirror both exactly, then scale by the KDE
# display scale.
_UI_FAMILY_CANDIDATES = (
    "Adwaita Sans", "Cantarell", "Inter", "Inter Display", "Noto Sans",
    "Ubuntu", "Open Sans", "Fira Sans", "DejaVu Sans", "Liberation Sans",
)
_MONO_FAMILY_CANDIDATES = (
    "Adwaita Sans Mono", "JetBrains Mono", "Cascadia Code", "Fira Code",
    "SF Mono", "Ubuntu Mono", "Consolas", "DejaVu Sans Mono",
    "Liberation Mono",
)

_FAMILY_CACHE: dict[str, str] = {}


def _tk_available_families() -> set[str]:
    try:
        import tkinter.font as tkfont
        return set(tkfont.families())
    except Exception:
        return set()


def _pick_family(candidates) -> str:
    available = _tk_available_families()
    for candidate in candidates:
        if candidate in available:
            return candidate
    return "Sans"


def _kde_font_family() -> str | None:
    """The family configured in Plasma (``Family,Size,...``), if installed."""
    try:
        from . import kde_theme
        spec = kde_theme.read().get("font") or ""
        family = spec.split(",")[0].strip()
        if family and family in _tk_available_families():
            return family
    except Exception:
        pass
    return None


def _default_family() -> str:
    """Best-effort resolution of the system UI font. Safe to call before Tk
    exists (falls back to 'Sans')."""
    if "ui" in _FAMILY_CACHE:
        return _FAMILY_CACHE["ui"]
    fam = _kde_font_family() or _pick_family(_UI_FAMILY_CANDIDATES)
    _FAMILY_CACHE["ui"] = fam
    return fam


def _mono_family() -> str:
    """Pick the nicest available monospace family for log / path fields."""
    if "mono" in _FAMILY_CACHE:
        return _FAMILY_CACHE["mono"]
    fam = _pick_family(_MONO_FAMILY_CANDIDATES)
    if fam == "Sans":
        fam = "monospace"
    _FAMILY_CACHE["mono"] = fam
    return fam


def font(size: int = 13, weight: str = "normal", slant: str = "roman",
         mono: bool = False):
    """Build a Tk font tuple using **pixel** sizes (like CSS px).

    ``size`` is the logical pixel height (scaled by the KDE display
    factor); ``weight`` is ``normal`` / ``bold`` / ``heavy`` (800).
    """
    if isinstance(weight, bool):
        weight = "bold" if weight else "normal"
    family = _mono_family() if mono else _default_family()
    parts = []
    if weight in ("bold", "heavy", "800"):
        parts.append("bold")
    if slant != "roman":
        parts.append(slant)
    return (family, -max(1, int(round(abs(size) * SCALE))), " ".join(parts))


def _build_fonts() -> None:
    """(Re)build every named text style from the resolved families."""
    global FONT, FONT_SM, FONT_TINY, FONT_BODY, FONT_BUTTON, FONT_CAPTION
    global FONT_SECTION, FONT_SUBTITLE, FONT_TITLE, FONT_HERO
    global FONT_MONO, FONT_MONO_SM
    global FONT_H1, FONT_H2, FONT_SMALL
    global FONT_PILL, FONT_PLAY, FONT_DIM, FONT_LABEL

    FONT          = font(13)               # Adw body
    FONT_BODY     = font(13)
    FONT_BUTTON   = font(13)
    FONT_LABEL    = font(13)
    FONT_DIM      = font(13)
    FONT_SM       = font(12)               # Adw subtitle / dim-label
    FONT_SMALL    = font(12)
    FONT_TINY     = font(11)               # Adw caption
    FONT_CAPTION  = font(12, "bold")       # .card-caption — 12.5px bold
    FONT_SECTION  = font(14, "bold")       # preferences group title
    FONT_SUBTITLE = font(15, "bold")       # dialog / header title
    FONT_TITLE    = font(16, "bold")       # .title-4 brand title
    FONT_HERO     = font(19, "bold")       # .title-2 detail title
    FONT_PILL     = font(11, "bold")       # .pill — 11.5px bold
    FONT_PLAY     = font(15, "bold")       # .play-button — 15px / 800
    FONT_MONO     = font(12, mono=True)
    FONT_MONO_SM  = font(11, mono=True)

    # Legacy aliases some forms may still reference.
    FONT_H1    = FONT_HERO
    FONT_H2    = FONT_SUBTITLE


_build_fonts()


# ---------------------------------------------------------------------------
# KDE colour scheme → token mapping
# ---------------------------------------------------------------------------
def apply_kde_palette(kde: dict) -> bool:
    """Derive every colour token from the active KDE colour scheme.

    Returns True when KDE colours were applied, False when the reference
    palette should be kept (no KDE settings found).
    """
    global SCALE, IS_DARK, KDE_ACTIVE, KDE_SCHEME
    global WINDOW, SIDEBAR, SIDEBAR_ACTIVE, SIDEBAR_LINE
    global CARD, CARD_HOVER, FIELD, FIELD_HOVER
    global BORDER, BORDER_SOFT, BG, BG_SOFT, SURFACE, SURFACE_2, SURFACE_3
    global FG, FG_SOFT, MUTED, DIM
    global ACCENT, ACCENT_HOVER, ACCENT_DIM, ACCENT_SOFT
    global PRIMARY, PRIMARY_HOVER, LIGHT, LIGHT_HOVER, LIGHT_FG
    global SUCCESS, SUCCESS_BG, WARNING, WARNING_BG
    global DANGER, DANGER_HOVER, DANGER_BG
    global STROKE, COVER_PLACEHOLDER, BACKDROP
    global INK, INK_HOVER
    global BG_HOVER, INPUT_BG, BUTTON, BUTTON_HOVER, PANEL, PANEL_2
    global TEXT, TEXT_SOFT, TEXT_MUTED, TEXT_DIM
    global SP_XS, SP_SM, SP_MD, SP_LG, SP_XL, SP_2XL
    global RADIUS_SM, RADIUS_MD, RADIUS_LG
    global HEADER_H, BUTTON_H, NAV_ROW_H, SIDEBAR_MIN, SIDEBAR_MAX
    global COVER_W, COVER_H, CARD_PAD, FLOW_COL_GAP, FLOW_ROW_GAP

    palette = kde.get("palette") or {}
    if not kde.get("available"):
        SCALE = 1.0
        KDE_ACTIVE = False
        _build_fonts()
        return False

    SCALE = float(kde.get("scale") or 1.0)
    KDE_ACTIVE = True
    KDE_SCHEME = kde.get("scheme") or ""

    get = lambda key, default: palette.get(key) or default

    window = get("window_bg", "#121214")
    view   = get("view_bg", _mix(window, "#000000", 0.35))
    button = get("button_bg", _mix(window, "#FFFFFF", 0.04))
    select = get("select_bg", _mix(window, "#FFFFFF", 0.09))
    fg     = get("window_fg", "#E8EAEE")
    header = get("header_bg", window)

    IS_DARK = _luminance(view) < 0.5
    deep = fg if IS_DARK else "#2A2A2E"          # mix target for insets
    white = "#FFFFFF"

    WINDOW         = view
    SIDEBAR        = header
    SIDEBAR_ACTIVE = select
    SIDEBAR_LINE   = _mix(SIDEBAR, deep, 0.35)
    CARD           = button
    CARD_HOVER     = _mix(CARD, fg, 0.07)
    FIELD          = _mix(view, fg, 0.09)
    FIELD_HOVER    = _mix(FIELD, fg, 0.10)
    BORDER         = _mix(view, fg, 0.17)
    BORDER_SOFT    = _mix(view, fg, 0.10)

    FG     = fg
    FG_SOFT = _mix(fg, view, 0.10)
    MUTED  = get("inactive", _mix(fg, view, 0.45))
    DIM    = _mix(MUTED, view, 0.35)

    # accent: the system accent colour if set, else the launcher's steel
    accent = kde.get("accent") or ACCENT
    focus = get("focus", "")
    ACCENT = accent
    ACCENT_HOVER = _mix(ACCENT, white, 0.12)
    ACCENT_DIM   = _mix(view, ACCENT, 0.26)
    ACCENT_SOFT  = _mix(ACCENT, white, 0.50)

    # suggested action: a coloured focus/hover decoration means the scheme
    # carries its own accent; otherwise keep the dark slate action colour
    if kde.get("accent"):
        PRIMARY = accent
    elif focus and _saturation(focus) > 0.15 and _luminance(focus) > 0.25:
        PRIMARY = focus
    else:
        PRIMARY = "#46586A"
    PRIMARY_HOVER = _mix(PRIMARY, white, 0.10)

    if IS_DARK:
        LIGHT       = _mix(fg, view, 0.12)
        LIGHT_HOVER = _mix(fg, view, 0.05)
        LIGHT_FG    = view
    else:
        LIGHT       = _mix(button, "#000000", 0.03)
        LIGHT_HOVER = _mix(button, "#000000", 0.07)
        LIGHT_FG    = fg

    SUCCESS      = get("positive", "#27AE60")
    SUCCESS_BG   = _mix(view, SUCCESS, 0.20)
    WARNING      = get("neutral", "#F67400")
    WARNING_BG   = _mix(view, WARNING, 0.20)
    DANGER       = get("negative", "#DA4453") if not IS_DARK else \
        _mix(get("negative", "#DA4453"), white, 0.35)
    DANGER_HOVER = _mix(DANGER, white, 0.15)
    DANGER_BG    = _mix(view, get("negative", "#DA4453"), 0.22)

    STROKE            = _mix(fg, view, 0.14)
    COVER_PLACEHOLDER = _mix(view, fg, 0.05)
    BACKDROP          = _mix(view, "#000000", 0.55)

    INK, INK_HOVER = PRIMARY, PRIMARY_HOVER
    BG, BG_SOFT = WINDOW, SIDEBAR
    SURFACE, SURFACE_2, SURFACE_3 = CARD, FIELD, FIELD_HOVER
    BG_HOVER = SURFACE_3
    INPUT_BG, BUTTON, BUTTON_HOVER = FIELD, FIELD, FIELD_HOVER
    PANEL, PANEL_2 = CARD, SIDEBAR
    TEXT, TEXT_SOFT, TEXT_MUTED, TEXT_DIM = FG, FG_SOFT, MUTED, DIM

    # --- scaled metrics ------------------------------------------------------
    SP_XS, SP_SM, SP_MD = px(4), px(8), px(14)
    SP_LG, SP_XL, SP_2XL = px(18), px(24), px(36)
    RADIUS_SM, RADIUS_MD, RADIUS_LG = px(6), px(10), px(14)
    HEADER_H = px(46)
    BUTTON_H = px(34)
    NAV_ROW_H = px(64)
    SIDEBAR_MIN, SIDEBAR_MAX = px(216), px(240)
    COVER_W, COVER_H = px(150), px(225)
    CARD_PAD = px(6)
    FLOW_COL_GAP, FLOW_ROW_GAP = px(14), px(16)

    _build_fonts()
    return True


# ---------------------------------------------------------------------------
# Root setup: DPI calibration, default fonts, ttk theming
# ---------------------------------------------------------------------------
def calibrate_scaling(root):
    """Calibrate ``tk scaling`` so point sizes behave like pixel sizes."""
    import tkinter.font as tkfont

    try:
        scaling = float(root.tk.call("tk", "scaling"))
        probe = tkfont.Font(root=root, family="DejaVu Sans", size=-12)
        linespace = probe.metrics("linespace")
        root.tk.call("tk", "scaling", linespace * scaling / (12 * 1.21))
    except (tk.TclError, TypeError, ValueError):
        pass


def refresh_fonts(root=None):
    """Re-resolve font families now that a root window exists."""
    _FAMILY_CACHE.clear()
    _build_fonts()


def apply_root_defaults(root):
    """Seed Tk's option database with dark defaults (listboxes, menus)."""
    root.option_add("*TCombobox*Listbox.background", CARD)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_DIM)
    root.option_add("*TCombobox*Listbox.selectForeground", ACCENT_SOFT)
    root.option_add("*TCombobox*Listbox.font", FONT_SM)
    root.option_add("*TCombobox*Listbox.borderWidth", 0)
    root.option_add("*TCombobox*Listbox.relief", "flat")
    root.option_add("*Menu.background", CARD)
    root.option_add("*Menu.foreground", FG)
    root.option_add("*Menu.activeBackground", FIELD_HOVER)
    root.option_add("*Menu.activeForeground", FG)
    root.option_add("*Menu.borderWidth", 1)
    root.option_add("*Menu.relief", "flat")
    root.option_add("*Menu.font", FONT_BODY)


def apply_ttk_style(root):
    """Restyle every ttk widget (scrollbars, comboboxes, treeviews,
    progress bars) and adopt the KDE colour scheme + display scale.
    Call once after the root window exists."""
    from tkinter import ttk

    # KDE first: palette, accent and display scale (before fonts/metrics)
    try:
        from . import kde_theme
        apply_kde_palette(kde_theme.read())
    except Exception:
        pass

    calibrate_scaling(root)
    refresh_fonts(root)
    apply_root_defaults(root)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # --- scrollbars: slim, quiet ------------------------------------------
    style.layout("TScrollbar", [
        ("Vertical.Scrollbar.trough", {"children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})
        ], "sticky": "ns"})])
    style.layout("Horizontal.TScrollbar", [
        ("Horizontal.Scrollbar.trough", {"children": [
            ("Horizontal.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})
        ], "sticky": "ew"})])
    style.configure("TScrollbar",
                    background=SIDEBAR_ACTIVE, troughcolor=WINDOW,
                    bordercolor=WINDOW, arrowcolor=WINDOW,
                    relief="flat", borderwidth=0, arrowsize=0,
                    gripcount=0, width=px(6))
    style.map("TScrollbar", background=[("active", DIM)])

    # --- combobox ----------------------------------------------------------
    for name in ("TCombobox", "Dark.TCombobox"):
        style.configure(name,
                        fieldbackground=FIELD, background=FIELD,
                        foreground=FG, arrowcolor=MUTED,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        selectbackground=FIELD, selectforeground=FG,
                        padding=(px(12), px(7)), borderwidth=0, relief="flat")
        style.map(name,
                  fieldbackground=[("readonly", FIELD)],
                  foreground=[("readonly", FG)],
                  bordercolor=[("focus", ACCENT), ("hover", BORDER)])
    style.configure("Vertical.TScrollbar", gripcount=0)

    # --- treeview / table ---------------------------------------------------
    style.configure("Treeview",
                    background=CARD, fieldbackground=CARD,
                    foreground=FG_SOFT, bordercolor=CARD,
                    rowheight=px(34), font=FONT_BODY, borderwidth=0)
    style.map("Treeview",
              background=[("selected", ACCENT_DIM)],
              foreground=[("selected", ACCENT_SOFT)])
    style.configure("Treeview.Heading",
                    background=CARD, foreground=MUTED,
                    relief="flat", borderwidth=0, font=FONT_SM,
                    padding=(px(12), px(8)))
    style.map("Treeview.Heading", background=[("active", CARD_HOVER)])

    # --- progress bar --------------------------------------------------------
    style.configure("TProgressbar",
                    background=PRIMARY, troughcolor=FIELD,
                    bordercolor=FIELD, lightcolor=PRIMARY,
                    darkcolor=PRIMARY, borderwidth=0, thickness=px(6))

    # --- scales --------------------------------------------------------------
    style.configure("TScale", background=WINDOW, troughcolor=FIELD,
                    bordercolor=BORDER)

    # --- check / radio (legacy native ones, restyled) -------------------------
    style.configure("TCheckbutton", background=WINDOW, foreground=FG,
                    font=FONT_BODY, focuscolor=ACCENT)
    style.map("TCheckbutton",
              background=[("active", WINDOW)],
              foreground=[("disabled", DIM)])
    style.configure("TRadiobutton", background=WINDOW, foreground=FG,
                    font=FONT_BODY, focuscolor=ACCENT)
    style.map("TRadiobutton",
              background=[("active", WINDOW)],
              foreground=[("disabled", DIM)])

    style.configure("TFrame", background=WINDOW)
    style.configure("TLabel", background=WINDOW, foreground=FG, font=FONT_BODY)

    return style


# ---------------------------------------------------------------------------
# Convenience: a palette dict for anything that wants to iterate tokens
# ---------------------------------------------------------------------------
PALETTE = {
    "bg": BG, "surface": SURFACE, "surface_2": SURFACE_2,
    "border": BORDER, "fg": FG, "muted": MUTED,
    "accent": ACCENT, "primary": PRIMARY, "success": SUCCESS,
    "warning": WARNING, "danger": DANGER,
}
