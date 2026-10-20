"""Abre o filme no player externo (padrão do sistema ou comando escolhido)."""
from __future__ import annotations

import os
import shlex
import subprocess


def _spawn(args: list[str]) -> None:
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def play(path: str, command: str = "") -> None:
    """Levanta OSError se o arquivo ou o player não existirem."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"O arquivo não foi encontrado:\n{path}")
    if command.strip():
        _spawn(shlex.split(command) + [path])
    else:
        _spawn(["xdg-open", path])


def show_in_folder(path: str) -> None:
    _spawn(["xdg-open", os.path.dirname(path)])
