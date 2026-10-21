# CineLocal

Local movie browser for Linux and Windows, with a Netflix-style black and blue look (night mode).
Fast and offline: the internet is only used to download posters and information for new movies
(or when you force an update).

## Download (no installation)

Get the file for your system from the [latest release](../../releases/latest):

- **Windows 10/11**: `CineLocal-windows-x86_64.exe` — double-click it. (Windows SmartScreen may warn about an
  unknown publisher: *More info → Run anyway*.)
- **Linux (x86_64)**: `CineLocal-linux-x86_64` — right-click → *Properties → Permissions → Allow executing*
  (or `chmod +x CineLocal-linux-x86_64`), then double-click it.

No Python needed. For the built-in player, VLC must be installed (see below); without it movies open in the
external player. If Linux complains about the Qt `xcb` plugin, run `sudo apt install libxcb-cursor0`.

**Automatic updates**: when it starts, CineLocal checks for a newer release and offers to update itself
(downloads the new file, replaces the current one and restarts). Turn it off in Settings → *Updates*.
Copies run from source or installed with `install.sh`/`install.bat` only get a link to the download page.

### Publishing a release (maintainers)

1. Set `UPDATE_REPO` (`"owner/repo"`) and `__version__` in `cinelocal/__init__.py` and commit.
2. `git tag v<version> && git push --tags` — GitHub Actions builds both executables with PyInstaller
   (`cinelocal.spec`) and attaches them to a new release. The tag must match `__version__`.
3. To build locally instead: `pip install pyinstaller && pyinstaller --noconfirm cinelocal.spec` (output in `dist/`).

## Installation (Linux Mint / Ubuntu / Debian)

```bash
unzip cinelocal.zip && cd cinelocal
./install.sh
```

The script installs any missing system libraries (it asks for the administrator password),
creates a virtual environment with PySide6 and adds **CineLocal** to the application menu.
To just try it without installing: `./run.sh`. To remove it: `./uninstall.sh` (`--purge` also deletes the data).

## Installation (Windows 10/11)

1. Install **Python 3.10 to 3.12** from [python.org/downloads/windows](https://www.python.org/downloads/windows/),
   checking **"Add python.exe to PATH"** in the installer.
2. Extract the CineLocal zip and double-click **`install.bat`** (or run `install.bat` in Command Prompt,
   inside the extracted folder).
3. To use the **built-in player**, also install 64-bit [VLC](https://www.videolan.org/vlc/)
   (`winget install VideoLAN.VLC`). Without it, CineLocal opens the movie in the Windows default player.
4. Open **CineLocal** from the Start Menu.

The script copies the app to `%LOCALAPPDATA%\Programs\cinelocal`, creates a virtual environment with PySide6
(needs internet, ~200 MB) and adds the Start Menu shortcut. It does not need administrator rights.
To just try it without installing: `run.bat`. To remove it: `uninstall.bat` (`--purge` also deletes the data).

## Uninstalling

Your movies are **never deleted**: the uninstaller only removes the app and, if you ask, CineLocal's data.

### Linux

1. Open a terminal in the extracted CineLocal folder (the same one as `install.sh`).
2. If you see `Permission denied`, make the script executable (some zip extractors lose that permission):

   ```bash
   chmod +x uninstall.sh
   ```

3. **Uninstall** — removes the app, the menu shortcut and the icon, but keeps the library, posters and settings
   (if you reinstall later, everything stays as it was):

   ```bash
   ./uninstall.sh
   ```

4. **Purge** (optional) — also removes all data. This deletes the library, the cached posters, the API key
   and the saved "Continue watching" positions, and cannot be undone:

   ```bash
   ./uninstall.sh --purge
   ```

   Folders removed by the purge: `~/.config/cinelocal`, `~/.local/share/cinelocal` and `~/.cache/cinelocal`.

### Windows

1. Open Command Prompt in the extracted CineLocal folder (the same one as `install.bat`). No `chmod`
   or administrator rights needed.
2. **Uninstall** — removes the app and the Start Menu shortcut, keeping the data:

   ```bat
   uninstall.bat
   ```

3. **Purge** (optional) — also removes the library, posters, API key and saved positions, with no way back:

   ```bat
   uninstall.bat --purge
   ```

   Folders removed by the purge: `%APPDATA%\cinelocal` and `%LOCALAPPDATA%\cinelocal`.

## Getting started

1. Open the app and click **Select movies folder** (the folder is read recursively).
2. Paste your **free TMDB key**: create an account at themoviedb.org → Settings → API →
   copy the "API Key" (or the "Read Access Token"). Use **Test** to validate it.
3. The app identifies each file by its name (ignoring `1080p`, `BluRay`, `[YTS]`... and using the year, if present),
   downloads the poster, synopsis, rating, cast, etc. in the background and stores everything locally.

## Usage

- **All movies** (default screen): with the "Continue watching" row above the grid (← → arrows to move through
  the movies); it disappears when empty or while searching, and scrolls together with the grid.
- **Grid**: click a poster to open the details (in the same window; `←  Back`, `Esc` or `Alt`+`←` return to the list
  exactly where you were). `Ctrl`/`Shift`+click selects several movies;
  right-click opens the menu (favorite, watched, collections, update, fix match).
- **Instant search** (`Ctrl+F`) by title, actor, director or genre; **sorting** by title, year,
  rating or recently added.
- **Sidebar**: All, Favorites, Watched/Unwatched, **Collections** (a movie can be in several),
  Genres and Years (decades). Right-click a collection to rename or delete it.
- **Watch** opens the **built-in player** (based on libVLC): `Space` pauses, `←`/`→` skip 10 s, `↑`/`↓` change the
  volume, `M` toggles mute, `F` toggles fullscreen and `Esc` goes back. It needs VLC installed (on Linux `install.sh` installs it) and,
  on Linux, X11 or XWayland (Wayland sessions run through XWayland automatically; a pure Wayland session without XWayland is not supported). Without that, or if you set a player in Settings (e.g. `mpv --fs`),
  the movie opens in the external player (`xdg-open` on Linux, the associated program on Windows).
  Past 95% the movie is marked as watched; at the end of an episode, the player offers the next one. On the grid, a
  bar on the poster shows how much has been watched, and **Continue watching** (sidebar) gathers what is half-watched
  (series included, with the episode in progress); "Watch from the start" is in the right-click menu.
  Volume and picture adjustments are remembered between movies; the player's gear (⚙) also has **speed** (0.5x to 2x) and **subtitle
  delay**, and the progress bar shows the time at the point under the mouse.
  In Settings you choose the **default player** (built-in or external); right-click a movie (or use the player's ⚙ gear)
  to open it in the other one. The built-in player remembers where you stopped and resumes from there, even after closing the app.
  In the player, the **⚙** gear gathers **Audio** and **Subtitles** (tracks that come in the file) and **Picture**
  (brightness, contrast, color and sharpness). In fullscreen, the controls and the pointer disappear after a few seconds without moving the mouse.
- **Series**: files with `S01E02`, `1x02` or `Season 1 Episode 2` in the name (or inside `Season N` folders)
  are grouped under a single series poster, which opens the list of seasons and episodes, each with its own metadata.
  (Portuguese names such as `Temporada 1 Episódio 2` are recognized too.)
  Series appear with a “Series” badge on the grid and are left out of collections.
- **Watchlist**: movies you want to watch in the future. Add them with the `Watchlist` button in the details or from the
  right-click menu; the list lives in the sidebar.
- **Metadata source** (Settings): TMDB (default) or OMDb. OMDb is free (1,000 requests/day), only has data in
  English and provides no backdrop image or trailer. When you switch sources, use **Metadata → Force update**
  to re-identify the movies already downloaded.
- **Rescan** (`F5`): runs when the app opens; detects new movies and removes the ones that disappeared from disk.
  Files moved to another subfolder keep their metadata, collections and flags.
- **Metadata**: fetch pending items, force an update of all (keeps confirmed matches)
  or review movies without a match. When the app is not sure (remakes, ambiguous title, nothing
  found), the movie gets a **Review** badge and you pick the right one in a dialog.
- Metadata **language**: default `en-US` (English is used as a fallback when a translation is missing);
  change it in Settings.

## Where the data lives

| What | Where |
|---|---|
| Library, collections, flags (SQLite) | `~/.local/share/cinelocal/library.db` |
| Posters, thumbnails and backdrops | `~/.cache/cinelocal/images/` |
| Settings (includes the TMDB key) | `~/.config/cinelocal/settings.json` (permission 600) |

On Windows: library in `%LOCALAPPDATA%\cinelocal\library.db`, posters in `%LOCALAPPDATA%\cinelocal\cache\images\`
and settings in `%APPDATA%\cinelocal\settings.json`.

Your video files are never modified.

## Code structure

```
main.py                     entry point
cinelocal/
  config.py                 paths, extensions, settings (JSON)
  db.py                     SQLite: movies, collections, flags
  scanner.py                folder scanning and filename cleanup
  library.py                syncs disk ↔ database (new, removed, moved)
  tmdb.py                   TMDB HTTP client
  omdb.py                   OMDb HTTP client (returns the same shape as TMDB)
  providers.py              picks the client for the configured source
  parsing.py                parses responses and picks the best match
  metadata_service.py       identifies the movie, downloads metadata and images
  images.py                 poster/thumbnail/backdrop cache
  workers.py                threads (parallel updates, background tasks)
  service.py                in-memory state + operations used by the interface
  filters.py                filters, search, sorting and counts
  player.py                 opens the movie in the external player
  updater.py                checks GitHub Releases and updates the packaged executable
  ui/                       theme (QSS), grid, sidebar, windows and dialogs
  ui/player_page.py         built-in player (libVLC)
tests/test_core.py          tests for the logic without a GUI
```

Tests: `python3 -m unittest discover -s tests`

## Notes

- This product uses the TMDB API but is not endorsed or certified by TMDB.
- Recognized formats: mkv, mp4, avi, mov, wmv, m4v, webm, flv, ts. To change them, edit `VIDEO_EXTENSIONS`
  in `cinelocal/config.py`.
