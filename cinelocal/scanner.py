"""Varredura da pasta de filmes e limpeza de nomes de arquivo (sem Qt)."""
from __future__ import annotations

import os
import re
from datetime import date

from .config import VIDEO_EXTENSIONS

# Termos típicos de nomes de release; o título termina antes do primeiro deles.
_JUNK = re.compile(
    r"\b(?:480p|576p|720p|1080p|1080i|2160p|4k|uhd|hdr10?|blu[ -]?ray|bdrip|brrip|bdremux|"
    r"remux|webrip|web[ -]dl|hdrip|dvdrip|dvdscr|hdtv|hdcam|x264|x265|h 264|h264|h 265|h265|"
    r"hevc|10bit|8bit|aac|ac3|eac3|dts|ddp5 1|ddp5|atmos|dual audio|dublado|legendado|"
    r"nacional|proper|repack|extended|unrated|directors cut|imax|yify|yts|rarbg|ettv|amzn)\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"(?<!\d)(1[89]\d{2}|20\d{2})(?!\d)")
_MIN_SAMPLE_SIZE = 80 * 1024 * 1024


def clean_filename(filename: str) -> tuple[str, int | None]:
    """Extrai (título, ano) de um nome de arquivo.

    'The.Matrix.1999.1080p.BluRay.x264-YTS.mkv' -> ('The Matrix', 1999)
    """
    stem = os.path.splitext(os.path.basename(filename))[0]
    s = re.sub(r"[._]+", " ", stem)
    s = re.sub(r"\[[^\]]*\]|\{[^}]*\}", " ", s)

    junk = _JUNK.search(s)
    if junk:
        s = s[: junk.start()]

    year = None
    max_year = date.today().year + 1
    candidates = [m for m in _YEAR.finditer(s) if m.start() > 0 and int(m.group(1)) <= max_year]
    if candidates:
        match = candidates[-1]
        year = int(match.group(1))
        s = s[: match.start()]

    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[\s\-–—:,;|(\[]+$", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -–—_.")
    if not s:
        s = re.sub(r"\s+", " ", re.sub(r"[._]+", " ", stem)).strip()
    return s, year


_EP_PATTERNS = (
    re.compile(r"(?<![a-z0-9])s(\d{1,2})[ ._-]?e(\d{1,4})(?!\d)", re.IGNORECASE),             # S01E02
    re.compile(r"(?<![a-z0-9])(\d{1,2})x(\d{2,3})(?![a-z0-9])", re.IGNORECASE),                # 1x02
    re.compile(r"(?<![a-z0-9])(?:season|temporada)[ ._-]*(\d{1,2})[ ._-]*"
               r"(?:episode|epis[oó]dio|ep)[ ._-]*(\d{1,3})(?!\d)", re.IGNORECASE),             # Temporada 1 Episódio 2
)
_SEASON_DIR = re.compile(r"^(?:season|temporada|temp|s)[ ._-]*(\d{1,2})$", re.IGNORECASE)
_EP_ONLY = re.compile(r"^(?:e|ep|episode|epis[oó]dio)?[ ._-]*(\d{1,3})(?!\d)", re.IGNORECASE)


def parse_episode(path: str, root: str | None = None) -> tuple[str, int | None, int, int] | None:
    """Reconhece episódios de série. Retorna (título da série, ano, temporada, episódio) ou None.

    'Breaking.Bad.S01E02.720p.mkv' -> ('Breaking Bad', None, 1, 2)
    'Show (2019)/Season 2/E05.mkv' -> ('Show', 2019, 2, 5)
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    folders = []   # pastas acima do arquivo, da mais próxima para a mais distante (até a raiz)
    current = os.path.dirname(path)
    root_norm = os.path.normcase(os.path.normpath(root)) if root else None
    while current and os.path.normcase(os.path.normpath(current)) != root_norm:
        parent, name = os.path.dirname(current), os.path.basename(current)
        if name:
            folders.append(name)
        if parent == current:
            break
        current = parent

    season = episode = None
    prefix = ""
    for pattern in _EP_PATTERNS:
        match = pattern.search(stem)
        if match:
            season, episode, prefix = int(match.group(1)), int(match.group(2)), stem[: match.start()]
            break
    if season is None and folders:   # '.../Temporada 2/05 - Título.mkv'
        folder_season = _SEASON_DIR.match(folders[0].strip())
        match = _EP_ONLY.match(stem.strip())
        if folder_season and match:
            season, episode = int(folder_season.group(1)), int(match.group(1))
    if season is None:
        return None

    title, year = clean_filename(prefix + ".mkv") if prefix.strip(" ._-") else ("", None)
    if not title:   # nome do arquivo sem o título da série: usa a pasta (ignorando 'Season N')
        for name in folders:
            if not _SEASON_DIR.match(name.strip()):
                title, year = clean_filename(name + ".mkv")
                break
    if not title:
        return None
    return title, year, season, episode


def search_attempts(title: str, year: int | None) -> list[tuple[str, int | None]]:
    """Consultas a tentar, em ordem. Cobre títulos que contêm número parecido com ano
    (ex.: 'Wonder Woman 1984')."""
    attempts: list[tuple[str, int | None]] = []
    if year:
        attempts.append((title, year))
        attempts.append((f"{title} {year}", None))
    attempts.append((title, None))
    seen, unique = set(), []
    for item in attempts:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def scan_folder(root: str) -> list[tuple[str, int]]:
    """Lista (caminho, tamanho) de todos os vídeos sob `root`, recursivamente."""
    found: list[tuple[str, int]] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            iterator = os.scandir(current)
        except OSError:
            continue
        with iterator:
            for entry in iterator:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if not entry.name.startswith("."):
                            stack.append(entry.path)
                    elif entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext not in VIDEO_EXTENSIONS:
                            continue
                        size = entry.stat().st_size
                        if "sample" in entry.name.lower() and size < _MIN_SAMPLE_SIZE:
                            continue
                        found.append((entry.path, size))
                except OSError:
                    continue
    return found
