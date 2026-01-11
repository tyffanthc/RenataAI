import os
import json
import uuid
from datetime import datetime

class LogbookManager:
    DEFAULT_FOLDERS = [
        ("Górnictwo",),
        ("Eksploracja",),
        ("Handel",),
        ("Ciekawe Miejsca",)
    ]

    def __init__(self, path="user_logbook.json"):
        self.path = path
        self.data = []
        self._index = {}
        self.load()

    def load(self):
        if not os.path.isfile(self.path):
            self._initialize_default()
            self.save()
        else:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        self._rebuild_index()
        return self.data

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def _initialize_default(self):
        """
        Tworzy domyślne drzewo dla pierwszego uruchomienia.
        Root zawiera 4 foldery: Górnictwo, Eksploracja, Handel, Ciekawe Miejsca.
        """
        self.data = []
        for (name,) in self.DEFAULT_FOLDERS:
            folder = self._make_folder(None, name)
            folder["children"] = []
            self.data.append(folder)

    def _make_folder(self, parent_id, name):
        node_id = str(uuid.uuid4())
        return {
            "id": node_id,
            "parent_id": parent_id,
            "type": "folder",
            "title": name,
            "content": None,
            "system": None,
            "body": None,
            "coords": None,
            "created_at": datetime.utcnow().isoformat()
        }

    def _make_entry(self, parent_id, title, content, system, body, coords):
        node_id = str(uuid.uuid4())
        return {
            "id": node_id,
            "parent_id": parent_id,
            "type": "note",
            "title": title,
            "content": content,
            "system": system,
            "body": body,
            "coords": coords,
            "created_at": datetime.utcnow().isoformat()
        }

    def _rebuild_index(self):
        self._index = {}
        def walk(nodes):
            for node in nodes:
                self._index[node["id"]] = node
                if node["type"] == "folder" and "children" in node:
                    walk(node["children"])
        walk(self.data)

    def add_folder(self, parent_id, name):
        folder = self._make_folder(parent_id, name)
        self._add_node(parent_id, folder)
        self.save()
        return folder

    def add_entry(self, parent_id, title, content, system, body, coords=None):
        entry = self._make_entry(parent_id, title, content, system, body, coords)
        self._add_node(parent_id, entry)
        self.save()
        return entry

    def _add_node(self, parent_id, node):
        if parent_id is None:
            self.data.append(node)
        else:
            parent = self._find_node(self.data, parent_id)
            if parent:
                if "children" not in parent:
                    parent["children"] = []
                parent["children"].append(node)
        self._rebuild_index()

    def _find_node(self, nodes, node_id):
        for node in nodes:
            if node["id"] == node_id:
                return node
            if node["type"] == "folder" and "children" in node:
                found = self._find_node(node["children"], node_id)
                if found:
                    return found
        return None

    def delete_node(self, node_id):
        """Usuwa węzeł (notatkę lub folder rekurencyjnie)."""
        def _delete(nodes, node_id):
            for i, node in enumerate(list(nodes)):
                if node["id"] == node_id:
                    del nodes[i]
                    return True
                if node.get("type") == "folder" and "children" in node:
                    if _delete(node["children"], node_id):
                        # jeśli po usunięciu folder pozostał pusty, to OK – nie kasujemy automatycznie rodzica
                        return True
            return False

        if not _delete(self.data, node_id):
            raise ValueError(f"Nie znaleziono węzła do usunięcia: {node_id}")
        self._rebuild_index()
        self.save()

    def move_node(self, node_id, new_parent_id):
        """
        Przenosi węzeł node_id pod new_parent_id (lub na root jeśli None).
        Zabezpieczenia:
        - nie pozwala przenieść folderu do jego własnego poddrzewa,
        - nowy rodzic musi być folderem (jeśli nie None).
        """
        # 1) Znajdź przenoszony węzeł
        node = self._find_node(self.data, node_id)
        if node is None:
            raise ValueError(f"Nie znaleziono węzła: {node_id}")

        # Nic do zrobienia, jeśli parent się nie zmienia
        if node.get("parent_id") == new_parent_id:
            return node

        # 2) Waliduj docelowego rodzica (jeśli podano)
        target_parent = None
        if new_parent_id is not None:
            target_parent = self._find_node(self.data, new_parent_id)
            if target_parent is None:
                raise ValueError(f"Nie znaleziono docelowego rodzica: {new_parent_id}")
            if target_parent.get("type") != "folder":
                raise ValueError("Docelowy rodzic nie jest folderem")

            # Zakaz przenoszenia do własnego poddrzewa
            # Sprawdzamy, czy new_parent_id nie jest potomkiem 'node'.
            def is_descendant(check_node, target_id):
                if check_node.get("type") == "folder" and "children" in check_node:
                    for ch in check_node["children"]:
                        if ch["id"] == target_id:
                            return True
                        if is_descendant(ch, target_id):
                            return True
                return False

            if is_descendant(node, new_parent_id):
                raise ValueError("Nie można przenieść folderu do jego własnego poddrzewa")

        # 3) Usuń węzeł z aktualnej lokalizacji (bez zapisu na dysk)
        def remove_in_place(nodes, target_id):
            for i, n in enumerate(list(nodes)):
                if n["id"] == target_id:
                    del nodes[i]
                    return True
                if n.get("type") == "folder" and "children" in n:
                    if remove_in_place(n["children"], target_id):
                        return True
            return False

        removed = remove_in_place(self.data, node_id)
        if not removed:
            # powinniśmy byli znaleźć i usunąć – jeśli nie, to błąd spójności
            raise RuntimeError("Nie udało się usunąć węzła ze starego miejsca")

        # 4) Ustaw nowego rodzica i wstaw do drzewa
        node["parent_id"] = new_parent_id
        if target_parent is None:
            # przeniesienie na root
            self.data.append(node)
        else:
            if "children" not in target_parent:
                target_parent["children"] = []
            target_parent["children"].append(node)

        # 5) Zaktualizuj indeks i zapisz
        self._rebuild_index()
        self.save()
        return node
