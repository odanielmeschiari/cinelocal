# Third-party components

CineLocal's packaged builds (the Windows installer and portable zip, the Linux `.deb`, portable archive and AppImage)
include the components below. Each one keeps its own license; this file says what they are, which license applies and
where the source code and the full license text can be obtained. It is a notice, not legal advice.

All of them are shipped as separate shared libraries (`.dll` / `.so`) inside the application folder, so each can be
replaced by another build of the same library.

| Component | Used for | License | Source and license text |
|---|---|---|---|
| Qt 6 and PySide6 (Qt for Python) | the user interface | LGPL-3.0-only (also offered under GPL-2.0-only / GPL-3.0-only) | https://code.qt.io and https://pypi.org/project/PySide6/ |
| Python | the interpreter | Python Software Foundation License | https://www.python.org/downloads/source/ |
| PyInstaller (bootloader) | builds the executable | GPL-2.0-or-later with an exception that allows distributing the generated programs under any license | https://pyinstaller.org |
| libVLC and libvlccore (VLC 3) | fallback player, reading resolution and codecs of files | LGPL-2.1-or-later | https://www.videolan.org/vlc/download-sources.html |
| VLC plugins (the `plugins` folder) | codecs, demuxers and outputs of libVLC | each plugin has its own license; several are GPL-2.0-or-later (see the `copyright` file of VLC's source) | https://www.videolan.org/vlc/download-sources.html |
| python-vlc | Python binding of libVLC | LGPL-2.1-or-later | https://github.com/oaubert/python-vlc |
| libmpv (with FFmpeg, libplacebo and the other libraries linked into it) | main player engine (GPU upscaling) | see "libmpv" below | see "libmpv" below |
| python-mpv | Python binding of libmpv | GPL-2.0-or-later or LGPL-2.1-or-later (dual) | https://github.com/jaseg/python-mpv |

## libmpv

* **Windows**: the "mpv-dev-lgpl-x86_64" build of https://github.com/zhongfly/mpv-winbuild, the exact release pinned in
  `packaging/libmpv-windows.lock.json` (tag, file name and SHA-256). It is the build its author publishes as the LGPL
  flavour of mpv. Source of mpv: https://github.com/mpv-player/mpv. The source and build scripts of the components linked
  into that DLL are in the build repository above.
* **Linux** (only when the build is made with `BUNDLE_LINUX_LIBMPV=1`): the `libmpv` package of the Ubuntu release the
  build runs on, plus the libraries it needs. mpv's source code is mostly GPL-2.0-or-later or LGPL-2.1-or-later, but
  Debian and Ubuntu state that their *binaries* are distributed under GPL-3.0-or-later because they link to the
  GPL-3.0-or-later library libsmbclient (see `/usr/share/doc/libmpv2/copyright` on Ubuntu). Anyone who redistributes
  such a build must comply with the GPL for those binaries. Source packages: https://packages.ubuntu.com/source/noble/mpv
  and the source packages of each bundled library on the same site.
