"""On-disk image cache: original poster, thumbnail (for the grid) and backdrop."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from .config import CACHE_DIR, DATA_DIR
from .tmdb import TMDBClient

THUMB_WIDTH = 300
COVER_WIDTH = 400
_ROOT = CACHE_DIR / "images"
_COVERS = DATA_DIR / "collection_covers"   # chosen by the user: not part of the cache


def _file(kind: str, movie_id: int) -> Path:
    return _ROOT / kind / f"{movie_id}.jpg"


def poster_file(movie_id: int) -> Path:
    return _file("posters", movie_id)


def thumb_file(movie_id: int) -> Path:
    return _file("thumbs", movie_id)


def backdrop_file(movie_id: int) -> Path:
    return _file("backdrops", movie_id)


def collection_cover_file(collection_id: int) -> Path:
    return _COVERS / f"{collection_id}.jpg"


def collection_cover(collection_id: int) -> tuple[str, float] | None:
    """(path, modification time) of the poster the user chose for a collection, if there is one."""
    path = collection_cover_file(collection_id)
    return (str(path), path.stat().st_mtime) if path.is_file() else None


def store_collection_cover(collection_id: int, source: str) -> bool:
    """Copies an image chosen by the user as the poster of a collection. False if it is not an image."""
    image = QImage(source)
    if image.isNull():
        return False
    if image.width() > COVER_WIDTH:
        image = image.scaledToWidth(COVER_WIDTH, Qt.SmoothTransformation)
    dest = collection_cover_file(collection_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.stem + ".tmp.jpg")
    image.save(str(tmp), "JPEG", 90)
    os.replace(tmp, dest)
    return True


def delete_collection_cover(collection_id: int) -> None:
    try:
        collection_cover_file(collection_id).unlink()
    except OSError:
        pass


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def save_poster(client: TMDBClient, movie_id: int, tmdb_path: str) -> bool:
    return store_poster(movie_id, client.download_image("w500", tmdb_path))


def store_poster(movie_id: int, data: bytes) -> bool:
    """Saves image bytes as the poster (and its thumbnail). False if the data is not an image."""
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


def delete_all_images() -> None:
    shutil.rmtree(_ROOT, ignore_errors=True)
