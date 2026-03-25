import logging
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
    """Polls for DB changes using fresh connections.

    Uses a fresh SQLite connection each poll cycle so it always sees the
    current on-disk state — critical for virtiofs mounts where persistent
    connections, PRAGMA data_version, and shared-memory files are unreliable.
    Watchdog FSEvents provide opportunistic fast-path notification for local
    writes.
    """

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
        self._watch_dir: str | None = None
        self._poll_timer: QTimer | None = None
        self._debounce_timer: QTimer | None = None
        self._last_snapshot: tuple[list, list] | None = None

    def start(self):
        beans, deps = self._load_fresh()
        self._last_snapshot = (beans, deps)
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

    def _load_fresh(self):
        """Open a fresh connection, read snapshot, close connection."""
        store = StalkStore(self._db_path)
        try:
            return store.load_snapshot()
        finally:
            store.close()

    def _trigger_debounced_poll(self):
        timer = self._debounce_timer
        if timer is not None:
            QTimer.singleShot(0, timer.start)

    def _check_for_changes(self):
        try:
            beans, deps = self._load_fresh()
        except Exception:
            log.exception("poll failed for %s, will retry next cycle", self._db_path)
            return

        if (beans, deps) != self._last_snapshot:
            self._last_snapshot = (beans, deps)
            self.snapshot_changed.emit(beans, deps)
