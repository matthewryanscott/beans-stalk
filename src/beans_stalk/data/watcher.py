from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from beans_stalk.data.store import StalkStore


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
        self._observer: Observer | None = None
        self._poll_timer: QTimer | None = None
        self._last_data_version: int | None = None
        self._debounce_timer: QTimer | None = None

    def start(self):
        self._store = StalkStore(self._db_path)
        self._last_data_version = self._pragma_data_version()
        beans, deps = self._store.load_snapshot()
        self.snapshot_changed.emit(beans, deps)

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._debounce_timer.timeout.connect(self._check_for_changes)

        handler = _DbFileHandler(self._db_path, self._trigger_debounced_poll)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._db_path.parent), recursive=False)
        self._observer.start()

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
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        if self._store is not None:
            self._store.close()
            self._store = None

    def _pragma_data_version(self) -> int:
        """Use PRAGMA data_version to detect cross-connection changes."""
        row = self._store.store.conn.execute("PRAGMA data_version").fetchone()
        return row[0]

    def _trigger_debounced_poll(self):
        QTimer.singleShot(0, self._debounce_timer.start)

    def _check_for_changes(self):
        if self._store is None:
            return
        current_version = self._pragma_data_version()
        if current_version != self._last_data_version:
            self._last_data_version = current_version
            beans, deps = self._store.load_snapshot()
            self.snapshot_changed.emit(beans, deps)
