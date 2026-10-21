"""On-disk image cache: original poster, thumbnail (for the grid) and backdrop."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from .config import CACHE_DIR
from .tmdb import TMDBClient

THUMB_WIDTH = 300
_ROOT = CACHE_DIR / "images"


def _file(kind: str, movie_id: int) -> Path:
    return _ROOT / kind / f"{movie_id}.jpg"


def poster_file(movie_id: int) -> Path:
    return _file("posters", movie_id)


def thumb_file(movie_id: int) -> Path:
    return _file("thumbs", movie_id)


def backdrop_file(movie_id: int) -> Path:
    return _file("backdrops", movie_id)


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def save_poster(client: TMDBClient, movie_id: int, tmdb_path: str) -> bool:
    data = client.download_image("w500", tmdb_path)
    image = QImage.fromData(data)
    if image.isNull():
        return False
    _write_atomic(poster_file(movie_id), data)

    thumb = image.scaledToWidth(THUMB_WIDTH, Qt.SmoothTransformation)
    dest = thumb_file(movie_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.stem + ".tmp.jpg")
    thumb.save(str(tmp), "JPEG", 88)
    os.replace(tmp, dest)
    return True


def save_backdrop(client: TMDBClient, movie_id: int, tmdb_path: str) -> bool:
    data = client.download_image("w780", tmdb_path)
    if QImage.fromData(data).isNull():
        return False
    _write_atomic(backdrop_file(movie_id), data)
    return True


def delete_images(movie_id: int, poster: bool = True, backdrop: bool = True) -> None:
    kinds = (("posters", "thumbs") if poster else ()) + (("backdrops",) if backdrop else ())
    for kind in kinds:
        try:
            _file(kind, movie_id).unlink()
        except OSError:
            pass
