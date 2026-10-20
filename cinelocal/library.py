"""Sincroniza o banco de dados com os arquivos existentes na pasta (sem Qt)."""
from __future__ import annotations

import os
import time

from .db import Database
from .scanner import clean_filename, scan_folder


def sync_library(db: Database, root: str) -> tuple[list[int], list[int]]:
    """Adiciona arquivos novos e remove os ausentes. Retorna (ids_adicionados, ids_removidos).

    Arquivos movidos de lugar (mesmo nome e tamanho) mantêm metadados, coleções e marcações.
    """
    if not os.path.isdir(root):
        raise FileNotFoundError(f"Pasta não encontrada: {root}")

    found = scan_folder(root)
    known = db.known_files()
    known_paths = {k["path"] for k in known}
    found_paths = {path for path, _ in found}

    gone: dict[tuple[str, int], list[dict]] = {}
    for k in known:
        if k["path"] not in found_paths:
            gone.setdefault((k["file_name"], k["size"]), []).append(k)

    new_rows, moved = [], []
    now = time.time()
    for path, size in found:
        if path in known_paths:
            continue
        name = os.path.basename(path)
        bucket = gone.get((name, size))
        if bucket:
            moved.append((bucket.pop()["id"], path))
            continue
        title, year = clean_filename(name)
        new_rows.append({"path": path, "file_name": name, "size": size,
                         "clean_title": title, "year_guess": year, "added_at": now})

    removed = [k["id"] for bucket in gone.values() for k in bucket]
    for movie_id, path in moved:
        db.update_path(movie_id, path)
    db.remove_movies(removed)
    added = db.add_movies(new_rows)
    return added, removed
