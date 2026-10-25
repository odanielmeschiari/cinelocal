#!/usr/bin/env bash
# Installs CineLocal for the current user (Linux Mint / Ubuntu / Debian).
# Creates a virtual environment, a `cinelocal` command and an application menu entry.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$HOME/.local/opt/cinelocal"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"

echo "==> Checking system dependencies"
PKGS=(python3 python3-venv python3-pip xdg-utils libegl1 libgl1 libxkbcommon-x11-0
      libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0
      libxcb-shape0 libxcb-xinerama0 vlc)
missing=()
for pkg in "${PKGS[@]}"; do
    dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if ((${#missing[@]})); then
    echo "    Installing: ${missing[*]} (may ask for your password)"
    # Third-party repositories with an invalid key (e.g. Spotify) make the update fail;
    # this does not prevent installing the packages from the existing lists.
    sudo apt-get update -qq || echo "    warning: apt-get update reported errors (probably a third-party repository); continuing"
    for pkg in "${missing[@]}"; do
        sudo apt-get install -y "$pkg" || echo "    warning: could not install $pkg"
    done
fi

echo "==> Copying files to $PREFIX"
mkdir -p "$PREFIX" "$BIN" "$APPS" "$ICONS"
rm -rf "$PREFIX/cinelocal" "$PREFIX/assets"
cp -r "$SRC/cinelocal" "$SRC/assets" "$SRC/main.py" "$SRC/requirements.txt" "$PREFIX/"
find "$PREFIX" -name "__pycache__" -type d -prune -exec rm -rf {} +

echo "==> Creating the virtual environment and installing PySide6 (needs internet, ~200 MB)"
[ -x "$PREFIX/venv/bin/python" ] || python3 -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/pip" install --upgrade pip >/dev/null
"$PREFIX/venv/bin/pip" install -r "$PREFIX/requirements.txt"

echo "==> Creating shortcuts"
cat > "$BIN/cinelocal" <<LAUNCHER
#!/usr/bin/env bash
exec "$PREFIX/venv/bin/python" "$PREFIX/main.py" "\$@"
LAUNCHER
chmod +x "$BIN/cinelocal"

cp "$SRC/assets/cinelocal.svg" "$ICONS/cinelocal.svg"
cat > "$APPS/cinelocal.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=CineLocal
Comment=Browse the movies in your local folder
Exec=$BIN/cinelocal
Icon=cinelocal
Terminal=false
Categories=AudioVideo;Video;Player;
StartupWMClass=CineLocal
DESKTOP

command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" || true

echo
echo "Done! Open CineLocal from the application menu (Sound & Video category)"
echo "or type: cinelocal   (if the command is not found, log out and back in)."
