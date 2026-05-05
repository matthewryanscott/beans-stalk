import sqlite3
from contextlib import contextmanager
from pathlib import Path

from beans import api
from beans.models import Bean, Dep
from beans.store import BeanStore, DepStore, JournalStore, Store


def _wrap_conn(conn: sqlite3.Connection) -> Store:
    """Build a beans Store on top of an existing connection without
    re-running executescript(SCHEMA) — the db already exists and the
    schema PRAGMAs are virtiofs-hostile."""
    store = object.__new__(Store)
    store.conn = conn
    store.bean = BeanStore(conn)
    store.dep = DepStore(conn)
    store.journal = JournalStore(conn)
    store.dry_run = False
    return store


@contextmanager
def _read_conn(db_path: str):
    """Lockless read-only connection via ?immutable=1.

    Bypasses WAL machinery entirely — no -shm mmap, no locks, no contention
    with any writer (Mac-side or VM-side). Sees whatever has been
    checkpointed to the main .db file.
    """
    conn = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _write_conn(db_path: str):
    """Short-lived write connection. EXCLUSIVE locking + WAL + autocheckpoint.

    Held only for the duration of one operation, then released on close.
    EXCLUSIVE locking lets WAL skip the -shm file (required on virtiofs).
    autocheckpoint=1 flushes writes to the main .db file on every commit
    so subsequent immutable=1 readers see the change immediately.

    Blocks other writers (incl. VM beans CLI) only for the few ms this
    context is open; busy_timeout=5000 covers any brief overlap.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA locking_mode=EXCLUSIVE")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=1")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()


def load_snapshot_readonly(db_path: str) -> tuple[list[Bean], list[Dep]]:
    """Read-only snapshot — used by the watcher's polling cycles."""
    with _read_conn(db_path) as conn:
        store = _wrap_conn(conn)
        return store.list(), store.list_all_deps()


class StalkStore:
    """Path-bound facade over the beans store.

    No long-lived sqlite connection. Each method opens a transient
    connection — read-only (immutable=1) for queries, short-lived
    EXCLUSIVE+WAL for writes — and closes it before returning. This lets
    a separate writer (e.g. beans CLI inside an OrbStack VM, accessing
    the same db over virtiofs) share the database reliably.
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)

    def close(self):
        """No-op — connections are transient."""

    # --- reads ---

    def load_snapshot(self) -> tuple[list[Bean], list[Dep]]:
        return load_snapshot_readonly(str(self.db_path))

    def ready_bean_ids(self) -> set[str]:
        with _read_conn(str(self.db_path)) as conn:
            return {b.id for b in api.ready_beans(_wrap_conn(conn))}

    def show_bean(self, bean_id: str) -> Bean:
        with _read_conn(str(self.db_path)) as conn:
            return api.show_bean(_wrap_conn(conn), bean_id)

    # --- writes ---

    def create_bean(self, title: str, **fields) -> Bean:
        with _write_conn(str(self.db_path)) as conn:
            return api.create_bean(_wrap_conn(conn), title, **fields)

    def update_bean(self, bean_id: str, **fields) -> Bean:
        with _write_conn(str(self.db_path)) as conn:
            return api.update_bean(_wrap_conn(conn), bean_id, **fields)

    def close_bean(self, bean_id: str, reason: str | None = None) -> Bean:
        with _write_conn(str(self.db_path)) as conn:
            return api.close_bean(_wrap_conn(conn), bean_id, reason=reason)

    def claim_bean(self, bean_id: str, actor: str) -> Bean:
        with _write_conn(str(self.db_path)) as conn:
            return api.claim_bean(_wrap_conn(conn), bean_id, actor)

    def release_bean(self, bean_id: str, actor: str) -> Bean:
        with _write_conn(str(self.db_path)) as conn:
            return api.release_bean(_wrap_conn(conn), bean_id, actor)

    def add_dep(self, from_id: str, to_id: str, dep_type: str = "blocks") -> Dep:
        with _write_conn(str(self.db_path)) as conn:
            return api.add_dep(_wrap_conn(conn), from_id, to_id, dep_type=dep_type)

    def remove_dep(self, from_id: str, to_id: str) -> int:
        with _write_conn(str(self.db_path)) as conn:
            return api.remove_dep(_wrap_conn(conn), from_id, to_id)

    def delete_bean(self, bean_id: str) -> Bean:
        with _write_conn(str(self.db_path)) as conn:
            return api.delete_bean(_wrap_conn(conn), bean_id)
