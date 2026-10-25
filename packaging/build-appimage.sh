#!/usr/bin/env bash
# Builds dist/CineLocal-linux-x86_64.AppImage from the PyInstaller folder dist/CineLocal.
# Usage: bash packaging/build-appimage.sh      (first: BUNDLE_LINUX_LIBMPV=1 pyinstaller --noconfirm cinelocal.spec)
#
# The AppImage is the PyInstaller folder (which already carries Qt, libVLC and libmpv with the libraries they need)
# plus a tiny AppRun, a desktop entry and the icon, packed with appimagetool. It refuses to build when libmpv is not in
# the folder, because an AppImage that depends on the system's libmpv would defeat its purpose.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/dist/CineLocal"
OUT="$ROOT/dist/CineLocal-linux-x86_64.AppImage"
WORK="$ROOT/build/appimage"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"

[ -x "$APP/CineLocal" ] || { echo "dist/CineLocal not found: run pyinstaller --noconfirm cinelocal.spec first" >&2; exit 1; }
compgen -G "$APP/_internal/libmpv.so*" >/dev/null || { echo "libmpv is not in dist/CineLocal: build with BUNDLE_LINUX_LIBMPV=1" >&2; exit 1; }
[ -f "$APP/_internal/libvlc.so.5" ] || { echo "libVLC is not in dist/CineLocal" >&2; exit 1; }

mkdir -p "$WORK"
TOOL="$WORK/appimagetool-x86_64.AppImage"
if [ ! -x "$TOOL" ]; then
  echo "==> Downloading appimagetool 1.9.1"
  curl -fsSL -o "$TOOL.part" "$APPIMAGETOOL_URL"
  echo "$APPIMAGETOOL_SHA256  $TOOL.part" | sha256sum -c - >/dev/null || { rm -f "$TOOL.part"; echo "appimagetool does not match its pinned SHA-256" >&2; exit 1; }
  chmod +x "$TOOL.part" && mv "$TOOL.part" "$TOOL"
fi

echo "==> Assembling the AppDir"
APPDIR="$WORK/AppDir"
rm -rf "$APPDIR"
install -d "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp -a "$APP" "$APPDIR/usr/lib/cinelocal"
install -m 644 "$ROOT/assets/cinelocal.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/cinelocal.svg"
install -m 644 "$ROOT/assets/cinelocal.svg" "$APPDIR/cinelocal.svg"
cat > "$APPDIR/cinelocal.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=CineLocal
Comment=Browse the movies in your local folder
Exec=CineLocal
Icon=cinelocal
Terminal=false
Categories=AudioVideo;Video;Player;
StartupWMClass=CineLocal
DESKTOP
cp "$APPDIR/cinelocal.desktop" "$APPDIR/usr/share/applications/cinelocal.desktop"
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/cinelocal/CineLocal" "$@"
APPRUN
chmod 755 "$APPDIR/AppRun"
cp "$ROOT/THIRD_PARTY_NOTICES.md" "$APPDIR/usr/lib/cinelocal/THIRD_PARTY_NOTICES.md" 2>/dev/null || true

echo "==> Packing the AppImage"
rm -f "$OUT"
# APPIMAGE_EXTRACT_AND_RUN lets the tool itself run on machines (and CI runners) without FUSE.
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "$OUT"
chmod 755 "$OUT"
echo "==> $OUT"
