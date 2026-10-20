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
