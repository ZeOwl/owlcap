#!/bin/sh
# Removes what install.sh created. Your settings in ~/.config/owlcap.json are kept.
set -e
rm -f "$HOME/.local/bin/owlcap" \
      "${XDG_DATA_HOME:-$HOME/.local/share}/applications/owlcap.desktop"
echo "Uninstalled."
