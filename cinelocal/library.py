"""Sincroniza o banco de dados com os arquivos existentes na pasta (sem Qt)."""
from __future__ import annotations

import os
import time

from .db import Database
from .scanner import clean_filename, parse_episode, scan_folder


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

    for k in known:   # arquivos já cadastrados como filme que na verdade são episódios
        if k["path"] in found_paths and k["kind"] != "episode":
            info = parse_episode(k["path"], root)
            if info:
                db.convert_to_episode(k["id"], db.ensure_series(info[0], info[1]), *info)

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
        row = {"path": path, "file_name": name, "size": size,
               "clean_title": title, "year_guess": year, "added_at": now}
        info = parse_episode(path, root)
        if info:
            row.update(clean_title=info[0], year_guess=info[1], kind="episode", season=info[2],
                       episode=info[3], series_id=db.ensure_series(info[0], info[1]))
        new_rows.append(row)

    removed = [k["id"] for bucket in gone.values() for k in bucket]
    for movie_id, path in moved:
        db.update_path(movie_id, path)
    db.remove_movies(removed)
    added = db.add_movies(new_rows)
    db.prune_series()
    return added, removed
