#!/usr/bin/env bash
# Remove o CineLocal. Use --purge para apagar também biblioteca, capas e configurações.
set -euo pipefail
rm -rf "$HOME/.local/opt/cinelocal"
rm -f "$HOME/.local/bin/cinelocal" \
      "$HOME/.local/share/applications/cinelocal.desktop" \
      "$HOME/.local/share/icons/hicolor/scalable/apps/cinelocal.svg"
if [ "${1:-}" = "--purge" ]; then
    rm -rf "$HOME/.config/cinelocal" "$HOME/.local/share/cinelocal" "$HOME/.cache/cinelocal"
    echo "Removido, incluindo dados e configurações."
else
    echo "Removido. Seus dados continuam em ~/.local/share/cinelocal (use --purge para apagar)."
fi
