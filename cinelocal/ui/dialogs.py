"""Diálogos e menus compartilhados (coleções)."""
from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QMessageBox, QMenu, QWidget

from ..service import LibraryService


def ask_new_collection(parent: QWidget, service: LibraryService) -> int | None:
    text = ""
    while True:
        name, ok = QInputDialog.getText(parent, "Nova coleção", "Nome da coleção:", text=text)
        if not ok:
            return None
        try:
            return service.create_collection(name)
        except ValueError as exc:
            QMessageBox.warning(parent, "Coleção", str(exc))
            text = name


def ask_rename_collection(parent: QWidget, service: LibraryService, collection_id: int) -> None:
    text = service.collection_name(collection_id)
    while True:
        name, ok = QInputDialog.getText(parent, "Renomear coleção", "Novo nome:", text=text)
        if not ok:
            return
        try:
            service.rename_collection(collection_id, name)
            return
        except ValueError as exc:
            QMessageBox.warning(parent, "Coleção", str(exc))
            text = name


def confirm_delete_collection(parent: QWidget, service: LibraryService, collection_id: int) -> bool:
    name = service.collection_name(collection_id)
    answer = QMessageBox.question(
        parent, "Excluir coleção",
        f"Excluir a coleção “{name}”?\nOs filmes não serão apagados, apenas removidos da coleção.")
    if answer == QMessageBox.Yes:
        service.delete_collection(collection_id)
        return True
    return False


def populate_collections_menu(menu: QMenu, service: LibraryService,
                              movie_ids: list[int], parent: QWidget) -> None:
    """Preenche `menu` com as coleções; marcar/desmarcar adiciona/remove os filmes."""
    ids = list(movie_ids)
    id_set = set(ids)
    for collection in service.collections:
        members = service.membership.get(collection["id"], set())
        all_in = id_set <= members
        action = menu.addAction(collection["name"])
        action.setCheckable(True)
        action.setChecked(all_in)
        action.triggered.connect(
            lambda _checked=False, cid=collection["id"], present=not all_in:
            service.set_in_collection(cid, ids, present))
    if service.collections:
        menu.addSeparator()
    new_action = menu.addAction("Nova coleção…")

    def create_and_add():
        collection_id = ask_new_collection(parent, service)
        if collection_id is not None:
            service.set_in_collection(collection_id, ids, True)

    new_action.triggered.connect(create_and_add)
