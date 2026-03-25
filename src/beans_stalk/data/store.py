import sqlite3
from pathlib import Path

from beans import api
from beans.models import Bean, Dep
from beans.store import BeanStore, DepStore, JournalStore, Store


def _open_store(db_path: str) -> Store:
    """Open an existing beans DB without executescript(SCHEMA).

    Store.__init__ always runs executescript(SCHEMA) which requires an
    exclusive lock to set journal_mode=WAL.  On virtiofs mounts the lock
    handshake can fail with "disk I/O error".  Since the DB already exists
    we just set the PRAGMAs individually with execute() (which respects
    busy_timeout) and wire up the sub-stores directly.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    store = object.__new__(Store)
    store.conn = conn
    store.bean = BeanStore(conn)
    store.dep = DepStore(conn)
    store.journal = JournalStore(conn)
    store.dry_run = False
    return store


class StalkStore:
    """Wraps beans Store for Beans Stalk read/write operations."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.store = _open_store(str(self.db_path))

    def close(self):
        self.store.close()

    def load_snapshot(self) -> tuple[list[Bean], list[Dep]]:
        beans = self.store.list()
        deps = self.store.list_all_deps()
        return beans, deps

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

