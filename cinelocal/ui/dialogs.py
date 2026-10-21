"""Shared dialogs and menus (collections)."""
from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QMessageBox, QMenu, QWidget

from ..service import LibraryService


def ask_new_collection(parent: QWidget, service: LibraryService) -> int | None:
    text = ""
    while True:
        name, ok = QInputDialog.getText(parent, "New collection", "Collection name:", text=text)
        if not ok:
            return None
        try:
            return service.create_collection(name)
        except ValueError as exc:
            QMessageBox.warning(parent, "Collection", str(exc))
            text = name


def ask_rename_collection(parent: QWidget, service: LibraryService, collection_id: int) -> None:
    text = service.collection_name(collection_id)
    while True:
        name, ok = QInputDialog.getText(parent, "Rename collection", "New name:", text=text)
        if not ok:
            return
        try:
            service.rename_collection(collection_id, name)
            return
        except ValueError as exc:
            QMessageBox.warning(parent, "Collection", str(exc))
            text = name


def confirm_delete_collection(parent: QWidget, service: LibraryService, collection_id: int) -> bool:
    name = service.collection_name(collection_id)
    answer = QMessageBox.question(
        parent, "Delete collection",
        f"Delete the collection “{name}”?\nThe movies will not be deleted, only removed from the collection.")
    if answer == QMessageBox.Yes:
        service.delete_collection(collection_id)
        return True
    return False


def populate_collections_menu(menu: QMenu, service: LibraryService,
                              movie_ids: list[int], parent: QWidget) -> None:
    """Fills `menu` with the collections; checking/unchecking adds/removes the movies."""
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
    new_action = menu.addAction("New collection…")

    def create_and_add():
        collection_id = ask_new_collection(parent, service)
        if collection_id is not None:
            service.set_in_collection(collection_id, ids, True)

    new_action.triggered.connect(create_and_add)
