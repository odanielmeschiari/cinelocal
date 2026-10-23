#!/usr/bin/env bash
# Builds dist/CineLocal-linux-x86_64.deb from the PyInstaller folder dist/CineLocal.
# Usage: packaging/build-deb.sh <version>      (run "pyinstaller --noconfirm cinelocal.spec" first)
set -euo pipefail

VERSION="${1:?usage: build-deb.sh <version>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="$(mktemp -d)"
chmod 755 "$PKG"
trap 'rm -rf "$PKG"' EXIT

install -d "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/scalable/apps"
cp -r "$ROOT/dist/CineLocal" "$PKG/opt/cinelocal"
chmod -R u+rwX,go+rX,go-w "$PKG/opt"
ln -s /opt/cinelocal/CineLocal "$PKG/usr/bin/cinelocal"
install -m 644 "$ROOT/assets/cinelocal.svg" "$PKG/usr/share/icons/hicolor/scalable/apps/cinelocal.svg"

cat > "$PKG/usr/share/applications/cinelocal.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=CineLocal
Comment=Browse the movies in your local folder
Exec=cinelocal
Icon=cinelocal
Terminal=false
Categories=AudioVideo;Video;Player;
StartupWMClass=CineLocal
DESKTOP

# The Qt libraries and libVLC are bundled; these are the system libraries Qt's xcb platform plugin loads.
cat > "$PKG/DEBIAN/control" <<CONTROL
Package: cinelocal
Version: $VERSION
Architecture: amd64
Section: video
Priority: optional
Maintainer: odanielmeschiari <odanielmeschiari@users.noreply.github.com>
Homepage: https://github.com/odanielmeschiari/cinelocal
Depends: libc6, libegl1, libgl1, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0
Description: Local movie and series browser and player
 Browse and play the movies and series in your local folders, with posters
 and metadata. Includes a built-in player (libVLC is bundled).
CONTROL

dpkg-deb --root-owner-group --build "$PKG" "$ROOT/dist/CineLocal-linux-x86_64.deb"
