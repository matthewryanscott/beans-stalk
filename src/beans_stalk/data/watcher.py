import logging
import os
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from beans_stalk.data.store import StalkStore

log = logging.getLogger(__name__)

# Shared observer: one per watched directory, refcounted across DataWatcher instances.
# Key: resolved directory path. Value: (Observer, handler_count).
_shared_observers: dict[str, tuple[Observer, int]] = {}


class _DbFileHandler(FileSystemEventHandler):
    def __init__(self, db_path: Path, trigger_poll: callable):
        self._db_name = db_path.name
        self._wal_name = f"{db_path.name}-wal"
        self._trigger_poll = trigger_poll

    def on_modified(self, event):
        if event.is_directory:
            return
        name = Path(event.src_path).name
        if name in (self._db_name, self._wal_name):
            self._trigger_poll()

    def on_created(self, event):
        self.on_modified(event)


def _acquire_observer(watch_dir: str, handler: FileSystemEventHandler) -> bool:
    """Schedule a handler on the shared observer for watch_dir. Returns True if successful."""
    if watch_dir in _shared_observers:
        observer, count = _shared_observers[watch_dir]
        observer.schedule(handler, watch_dir, recursive=False)
        _shared_observers[watch_dir] = (observer, count + 1)
        return True

    observer = Observer()
    observer.schedule(handler, watch_dir, recursive=False)
    observer.start()
    _shared_observers[watch_dir] = (observer, 1)
    return True


def _release_observer(watch_dir: str):
    """Decrement refcount for watch_dir's observer; stop it when no handlers remain."""
    if watch_dir not in _shared_observers:
        return
    observer, count = _shared_observers[watch_dir]
    if count <= 1:
        observer.stop()
        observer.join()
        del _shared_observers[watch_dir]
    else:
        _shared_observers[watch_dir] = (observer, count - 1)


class DataWatcher(QObject):
    """Hybrid watchdog + poll change detector. All Store access on main thread."""

    snapshot_changed = Signal(list, list)

    def __init__(
        self,
        db_path: Path | str,
        poll_interval_seconds: float,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._db_path = Path(db_path)
        self._poll_interval_ms = int(poll_interval_seconds * 1000)
        self._store: StalkStore | None = None
        self._watch_dir: str | None = None
        self._poll_timer: QTimer | None = None
        self._last_data_version: int | None = None
        self._debounce_timer: QTimer | None = None
        self._last_wal_stat: tuple[float, int] | None = None  # (mtime, size)

    def start(self):
        self._store = StalkStore(self._db_path)
        self._last_wal_stat = self._wal_stat()
        self._last_data_version = self._pragma_data_version()
        beans, deps = self._store.load_snapshot()
        self.snapshot_changed.emit(beans, deps)

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._debounce_timer.timeout.connect(self._check_for_changes)

        self._watch_dir = str(self._db_path.parent.resolve())
        handler = _DbFileHandler(self._db_path, self._trigger_debounced_poll)
        _acquire_observer(self._watch_dir, handler)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._poll_interval_ms)
        self._poll_timer.timeout.connect(self._check_for_changes)
        self._poll_timer.start()

    def stop(self):
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
            self._debounce_timer = None
        if self._watch_dir is not None:
            _release_observer(self._watch_dir)
            self._watch_dir = None
        if self._store is not None:
            self._store.close()
            self._store = None

    def _wal_stat(self) -> tuple[float, int] | None:
        """Return (mtime, size) of the WAL file, or None if absent."""
        wal = self._db_path.with_suffix(self._db_path.suffix + "-wal")
        try:
            st = os.stat(wal)
            return (st.st_mtime, st.st_size)
        except FileNotFoundError:
            return None

    def _files_changed(self) -> bool:
        """Detect on-disk changes via WAL file stat.

        This catches writes from processes that bypass SQLite's shared
        memory protocol (e.g. virtiofs-mounted databases written by a VM).
        """
        current = self._wal_stat()
        if current != self._last_wal_stat:
            self._last_wal_stat = current
            return True
        return False

    def _pragma_data_version(self) -> int:
        """Use PRAGMA data_version to detect cross-connection changes.

        Commit first to close any implicit read transaction — SQLite docs
        say data_version behaviour is undefined inside an open transaction.
        """
        self._store.store.conn.commit()
        row = self._store.store.conn.execute("PRAGMA data_version").fetchone()
        return row[0]

    def _trigger_debounced_poll(self):
        timer = self._debounce_timer
        if timer is not None:
            QTimer.singleShot(0, timer.start)

    def _check_for_changes(self):
        if self._store is None:
            return
        try:
            # Reconnect when WAL file stats change — a fresh connection
            # is needed to see writes that bypassed SQLite's shared-memory
            # protocol (e.g. virtiofs mounts across a VM boundary).
            if self._files_changed():
                self._store.close()
                self._store = StalkStore(self._db_path)
                self._last_data_version = None

            current_version = self._pragma_data_version()
            if current_version != self._last_data_version:
                self._last_data_version = current_version
                beans, deps = self._store.load_snapshot()
                self.snapshot_changed.emit(beans, deps)
        except Exception:
            log.exception("poll failed, reconnecting to %s", self._db_path)
            try:
                self._store.close()
            except Exception:
                pass
            self._store = StalkStore(self._db_path)
            self._last_data_version = None
