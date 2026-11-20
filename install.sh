#!/usr/bin/env bash
#
# OnlineFix Linux Launcher — installer
#
# Usage:
#   ./install.sh                 install for the current user (default)
#   ./install.sh --system        install system-wide (needs sudo)
#   ./install.sh --uninstall     remove the launcher
#   ./install.sh --help
#
# What it does:
#   * copies the application into ~/.local/share/onlinefix-launcher
#   * creates a private virtualenv there (Pillow, tkinterweb)
#   * puts an `onlinefix-launcher` command on your PATH
#   * adds a menu entry (KDE/GNOME application launcher)
#   * installs the application icon into the hicolor icon theme

set -euo pipefail

APP_NAME="OnlineFix Launcher"
APP_SLUG="onlinefix-launcher"
WM_CLASS="OnlineFixLauncher"

MODE="user"

BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; RESET=$'\033[0m'
info()  { printf '%s==>%s %s\n' "$GREEN" "$RESET" "$*"; }
warn()  { printf '%s[warning]%s %s\n' "$YELLOW" "$RESET" "$*" >&2; }
error() { printf '%s[error]%s %s\n' "$RED" "$RESET" "$*" >&2; }
hint()  { printf '%s%s%s\n' "$DIM" "$*" "$RESET"; }

usage() { sed -n '3,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --user)     MODE="user" ;;
        --system)   MODE="system" ;;
        --uninstall) exec "$(dirname "$(readlink -f "$0")")/uninstall.sh" "${2:-}" ;;
        -h|--help)  usage ;;
        *)          error "Unknown option: $1"; usage ;;
    esac
    shift
done

REPO_OWNER="nizar2004"
REPO_NAME="onlinefix-project"

# When the script is piped from curl there is no project folder next to it —
# download the repository tarball instead.
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]:-$0}")")" && pwd)"
if [[ ! -f "$SCRIPT_DIR/main.py" ]]; then
    if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
        error "curl or wget is required to download the launcher."
        exit 1
    fi
    TMP_DIR="$(mktemp -d)"
    info "Downloading the launcher source…"
    TAR_URL="https://codeload.github.com/$REPO_OWNER/$REPO_NAME/tar.gz/refs/heads/main"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$TAR_URL" | tar -xz -C "$TMP_DIR"
    else
        wget -qO- "$TAR_URL" | tar -xz -C "$TMP_DIR"
    fi
    SCRIPT_DIR="$TMP_DIR/$REPO_NAME-main"
    if [[ ! -f "$SCRIPT_DIR/main.py" ]]; then
        error "Could not download the launcher source from GitHub."
        exit 1
    fi
fi

if [[ "$MODE" == "system" ]]; then
    if [[ $EUID -ne 0 ]]; then
        error "--system needs root. Re-run with sudo: sudo ./install.sh --system"
        exit 1
    fi
    PREFIX="/usr/local"
    BIN_DIR="$PREFIX/bin"
    DATA_DIR="$PREFIX/share"
else
    PREFIX="$HOME/.local"
    BIN_DIR="$PREFIX/bin"
    DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
fi

APP_DIR="$DATA_DIR/$APP_SLUG"
APPS_DIR="$DATA_DIR/applications"
ICONS_DIR="$DATA_DIR/icons/hicolor"

# ---------------------------------------------------------------- checks
if ! command -v python3 >/dev/null 2>&1; then
    error "python3 is required but was not found."
    exit 1
fi
if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    warn "python3-tk (Tkinter) is missing — install it with your package manager:"
    warn "  Debian/Ubuntu: sudo apt install python3-tk"
    warn "  Arch:          sudo pacman -S tk"
    warn "  Fedora:        sudo dnf install python3-tkinter"
    exit 1
fi

# ---------------------------------------------------------------- app files
info "Installing application files to $APP_DIR"
rm -rf "$APP_DIR"          # clean install — removes any stale files
mkdir -p "$APP_DIR" "$BIN_DIR" "$APPS_DIR"

rsync_bin=""
if command -v rsync >/dev/null 2>&1; then rsync_bin="yes"; fi

copy_app() {
    local src="$1" dest="$2"
    if [[ -n "$rsync_bin" ]]; then
        rsync -a --delete \
            --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
            --exclude '.git' "$src/" "$dest/"
    else
        mkdir -p "$dest"
        cp -r "$src/app" "$src/assets" "$src/locale" "$dest/" 2>/dev/null || true
        find "$dest" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
        cp "$src/main.py" "$src/requirements.txt" "$src/onlinefix-linux-launcher" "$dest/"
    fi
}

copy_app "$SCRIPT_DIR" "$APP_DIR"
chmod +x "$APP_DIR/onlinefix-linux-launcher"

# ---------------------------------------------------------------- python env
info "Preparing the Python environment"
if [[ -d "$SCRIPT_DIR/.venv" && -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    # reuse the development virtualenv (offline, fast)
    rm -rf "$APP_DIR/.venv"
    cp -a "$SCRIPT_DIR/.venv" "$APP_DIR/.venv"
    info "  reused the existing .venv"
else
    python3 -m venv "$APP_DIR/.venv" 2>/dev/null || \
        python3 -m venv --without-pip "$APP_DIR/.venv"
    "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip >/dev/null 2>&1 || true
    "$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt" >/dev/null
    info "  created a fresh virtualenv and installed dependencies"
fi

"$APP_DIR/.venv/bin/python" -c "import PIL" 2>/dev/null || {
    warn "Pillow is missing in the installed environment — installing…"
    "$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt" >/dev/null
}

# ---------------------------------------------------------------- command
info "Installing the command: $BIN_DIR/$APP_SLUG"
cat > "$BIN_DIR/$APP_SLUG" <<EOF
#!/bin/sh
# OnlineFix Linux Launcher
DIR="\$(dirname "\$(readlink -f "\$0")")"
APP_DIR="$APP_DIR"
if [ -x "\$APP_DIR/.venv/bin/python" ]; then
    PYTHON="\$APP_DIR/.venv/bin/python"
else
    PYTHON=python3
fi
cd "\$APP_DIR"
exec "\$PYTHON" "\$APP_DIR/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/$APP_SLUG"

# ---------------------------------------------------------------- desktop entry
info "Installing the menu entry"
mkdir -p "$APPS_DIR"
cat > "$APPS_DIR/$APP_SLUG.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=Game Launcher
Comment=Run games with community multiplayer fixes on Linux
Exec=$BIN_DIR/$APP_SLUG
TryExec=$BIN_DIR/$APP_SLUG
Icon=$APP_SLUG
Terminal=false
Categories=Game;ActionGame;
Keywords=games;onlinefix;proton;wine;
StartupWMClass=$WM_CLASS
EOF

# ---------------------------------------------------------------- icons
info "Installing icons"
for size in 16 24 32 48 64 128 256; do
    icon_src="$SCRIPT_DIR/assets/img/oficon-$size.png"
    [[ -f "$icon_src" ]] || continue
    dir="$ICONS_DIR/${size}x${size}/apps"
    mkdir -p "$dir"
    cp "$icon_src" "$dir/$APP_SLUG.png"
done
# scalable fallback so the icon resolves before the cache refreshes
mkdir -p "$ICONS_DIR/256x256/apps"
[[ -f "$SCRIPT_DIR/assets/img/oficon-256.png" ]] && \
    cp "$SCRIPT_DIR/assets/img/oficon-256.png" "$ICONS_DIR/256x256/apps/$APP_SLUG.png"

# ---------------------------------------------------------------- caches
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi
for tool in kbuildsycoca6 kbuildsycoca5; do
    if command -v "$tool" >/dev/null 2>&1; then
        "$tool" >/dev/null 2>&1 || true
        break
    fi
done
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$ICONS_DIR" >/dev/null 2>&1 || true
fi

echo
info "${BOLD}$APP_NAME installed.${RESET}"
hint "Launch it from your application menu, or run: $BIN_DIR/$APP_SLUG"
hint "Game shortcuts keep working — they now point at the installed copy."
