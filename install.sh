#!/bin/sh
# Installs OwlCap for the current user (no root needed).
# The program is symlinked, so updates to this folder take effect immediately.
set -e
cd "$(dirname "$0")"
BIN="$HOME/.local/bin"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

mkdir -p "$BIN" "$APPS"
chmod +x owlcap.py
ln -sf "$PWD/owlcap.py" "$BIN/owlcap"
# absolute path, because launchers don't always have ~/.local/bin in PATH
sed "s|^Exec=.*|Exec=\"$BIN/owlcap\"|" owlcap.desktop > "$APPS/owlcap.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true

echo "Installed. Start \"OwlCap\" from your app menu or run: owlcap"
