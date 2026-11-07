#!/bin/sh
# Installs Capture Card for the current user (no root needed).
# The program is symlinked, so updates to this folder take effect immediately.
set -e
cd "$(dirname "$0")"
BIN="$HOME/.local/bin"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

mkdir -p "$BIN" "$APPS"
chmod +x capture-card.py
ln -sf "$PWD/capture-card.py" "$BIN/capture-card"
# absolute path, because launchers don't always have ~/.local/bin in PATH
sed "s|^Exec=.*|Exec=\"$BIN/capture-card\"|" capture-card.desktop > "$APPS/capture-card.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true

echo "Installed. Start \"Capture Card\" from your app menu or run: capture-card"
