#!/usr/bin/env bash
#
# OnlineFix Linux Launcher — uninstaller
#
# Usage:
#   ./uninstall.sh                 remove the user installation (default)
#   ./uninstall.sh --system        remove a system-wide installation
#
# Your games, save files and the ~/.config/OFME-Linux settings are kept.

set -euo pipefail

APP_SLUG="onlinefix-launcher"
BOLD=$'\033[1m'; GREEN=$'\033[32m'; RESET=$'\033[0m'
info() { printf '%s==>%s %s\n' "$GREEN" "$RESET" "$*"; }

MODE="user"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --system) MODE="system" ;;
        -h|--help) sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) MODE="user" ;;
    esac
    shift
done

if [[ "$MODE" == "system" ]]; then
    if [[ $EUID -ne 0 ]]; then
        echo "[error] --system needs root. Re-run with sudo." >&2
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

# stop a running instance so files can be removed
pkill -f "onlinefix-launcher.*main.py" 2>/dev/null || true
pkill -f "$DATA_DIR/$APP_SLUG/main.py" 2>/dev/null || true

info "Removing the application files"
rm -rf "$DATA_DIR/$APP_SLUG"

info "Removing the command"
rm -f "$BIN_DIR/$APP_SLUG"

info "Removing the menu entry"
rm -f "$DATA_DIR/applications/$APP_SLUG.desktop"

info "Removing icons"
for size in 16 24 32 48 64 128 256; do
    rm -f "$DATA_DIR/icons/hicolor/${size}x${size}/apps/$APP_SLUG.png"
done

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DATA_DIR/applications" >/dev/null 2>&1 || true
fi
for tool in kbuildsycoca6 kbuildsycoca5; do
    if command -v "$tool" >/dev/null 2>&1; then "$tool" >/dev/null 2>&1 || true; break; fi
done

echo
info "${BOLD}OnlineFix Linux Launcher removed.${RESET}"
echo "Your games and settings (~/.config/OFME-Linux) were kept."
