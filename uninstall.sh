#!/usr/bin/env bash
# Removes CineLocal. Use --purge to also delete the library, posters and settings.
set -euo pipefail
rm -rf "$HOME/.local/opt/cinelocal"
rm -f "$HOME/.local/bin/cinelocal" \
      "$HOME/.local/share/applications/cinelocal.desktop" \
      "$HOME/.local/share/icons/hicolor/scalable/apps/cinelocal.svg"
if [ "${1:-}" = "--purge" ]; then
    rm -rf "$HOME/.config/cinelocal" "$HOME/.local/share/cinelocal" "$HOME/.cache/cinelocal"
    echo "Removed, including data and settings."
else
    echo "Removed. Your data is still in ~/.local/share/cinelocal (use --purge to delete it)."
fi
