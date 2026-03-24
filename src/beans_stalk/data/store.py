import sqlite3
from pathlib import Path

from beans import api
from beans.models import Bean, Dep
from beans.store import Store


class StalkStore:
    """Wraps beans Store for Beans Stalk read/write operations."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA busy_timeout=5000")
        self.store = Store(conn)

    def close(self):
        self.store.close()

    def load_snapshot(self) -> tuple[list[Bean], list[Dep]]:
        beans = self.store.list()
        deps = self.store.list_all_deps()
        return beans, deps

    def data_version(self) -> int:
        row = self.store.conn.execute("SELECT total_changes()").fetchone()
        return row[0]

    def create_bean(self, title: str, **fields) -> Bean:
        return api.create_bean(self.store, title, **fields)

    def update_bean(self, bean_id: str, **fields) -> Bean:
        return api.update_bean(self.store, bean_id, **fields)

    def close_bean(self, bean_id: str, reason: str | None = None) -> Bean:
        return api.close_bean(self.store, bean_id, reason=reason)

    def claim_bean(self, bean_id: str, actor: str) -> Bean:
        return api.claim_bean(self.store, bean_id, actor)

    def release_bean(self, bean_id: str, actor: str) -> Bean:
        return api.release_bean(self.store, bean_id, actor)

    def add_dep(self, from_id: str, to_id: str, dep_type: str = "blocks") -> Dep:
        return api.add_dep(self.store, from_id, to_id, dep_type=dep_type)

    def remove_dep(self, from_id: str, to_id: str) -> int:
        return api.remove_dep(self.store, from_id, to_id)

    def delete_bean(self, bean_id: str) -> Bean:
        return api.delete_bean(self.store, bean_id)

    def ready_bean_ids(self) -> set[str]:
        return {b.id for b in api.ready_beans(self.store)}

    def show_bean(self, bean_id: str) -> Bean:
        return api.show_bean(self.store, bean_id)

