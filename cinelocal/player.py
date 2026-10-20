"""Abre o filme no player externo (padrão do sistema ou comando escolhido)."""
from __future__ import annotations

import os
import shlex
import subprocess


def _split(command: str) -> list[str]:
    if os.name != "nt":
        return shlex.split(command)
    # No Windows, shlex em modo POSIX come as barras invertidas dos caminhos.
    return [a[1:-1] if len(a) > 1 and a[0] == a[-1] == '"' else a
            for a in shlex.split(command, posix=False)]


def _spawn(args: list[str]) -> None:
    if os.name == "nt":
        subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        return
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def play(path: str, command: str = "") -> None:
    """Levanta OSError se o arquivo ou o player não existirem."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"O arquivo não foi encontrado:\n{path}")
    if command.strip():
        _spawn(_split(command) + [path])
    elif os.name == "nt":
        os.startfile(path)
    else:
        _spawn(["xdg-open", path])


def show_in_folder(path: str) -> None:
    if os.name == "nt":
        _spawn(["explorer", "/select,", os.path.normpath(path)])
        return
    _spawn(["xdg-open", os.path.dirname(path)])
