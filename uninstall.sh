#!/bin/sh
# Removes what install.sh created. Your settings in ~/.config/capture-card.json are kept.
set -e
rm -f "$HOME/.local/bin/capture-card" \
      "${XDG_DATA_HOME:-$HOME/.local/share}/applications/capture-card.desktop"
echo "Uninstalled."
