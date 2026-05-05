import logging
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from beans_stalk.data.store import load_snapshot_readonly

log = logging.getLogger(__name__)


class _DbFileHandler(FileSystemEventHandler):
    def __init__(self, db_path: Path, trigger_poll: callable):
        self._watched_names = {
            db_path.name,
            f"{db_path.name}-wal",
            f"{db_path.name}-shm",
        }
        self._trigger_poll = trigger_poll

    def _maybe_trigger(self, path: str | None):
        if path is None:
            return
        if Path(path).name in self._watched_names:
            self._trigger_poll()

    def on_modified(self, event):
        if event.is_directory:
            return
        self._maybe_trigger(event.src_path)

    def on_created(self, event):
        self.on_modified(event)

    def on_deleted(self, event):
        self.on_modified(event)

    def on_moved(self, event):
        if event.is_directory:
            return
        self._maybe_trigger(event.src_path)
        self._maybe_trigger(event.dest_path)


class DataWatcher(QObject):
    """Polls for DB changes using fresh connections.

    Uses a fresh SQLite connection each poll cycle so it always sees the
    current on-disk state — critical for virtiofs mounts where persistent
    connections, PRAGMA data_version, and shared-memory files are unreliable.
    Watchdog FSEvents provide opportunistic fast-path notification for local
    writes.
    """

    snapshot_changed = Signal(list, list)
    _poll_requested = Signal()

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
        self._observer: Observer | PollingObserver | None = None
        self._handler: _DbFileHandler | None = None
        self._poll_timer: QTimer | None = None
        self._debounce_timer: QTimer | None = None
        self._last_snapshot: tuple[list, list] | None = None
        self._poll_requested.connect(self._on_poll_requested)

    def start(self):
        beans, deps = self._load_fresh()
        self._last_snapshot = (beans, deps)
        self.snapshot_changed.emit(beans, deps)

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._debounce_timer.timeout.connect(self._check_for_changes)

        self._watch_dir = str(self._db_path.parent.resolve())
        self._handler = _DbFileHandler(self._db_path, self._trigger_debounced_poll)
        self._start_observer()

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
        self._stop_observer()
        self._handler = None
        self._watch_dir = None

    def _load_fresh(self):
        """Read snapshot via a lockless immutable=1 connection.

        Avoids contending with the main StalkStore's EXCLUSIVE lock, and
        works on virtiofs where WAL machinery is unavailable.
        """
        return load_snapshot_readonly(str(self._db_path))

    def _trigger_debounced_poll(self):
        self._poll_requested.emit()

    def request_poll(self):
        """Public nudge — call right after a local write to refresh the UI
        without waiting for the file-watch / poll cycle to fire."""
        self._poll_requested.emit()

    @Slot()
    def _on_poll_requested(self):
        timer = self._debounce_timer
        if timer is not None:
            timer.start()

    def _observer_factory(self, use_polling: bool = False):
        if sys.platform == "darwin":
            use_polling = True
        if use_polling:
            timeout_seconds = 0.25
            return PollingObserver(timeout=timeout_seconds)
        return Observer()

    def _start_observer(self):
        if self._watch_dir is None or self._handler is None:
            return

        for use_polling in (False, True):
            observer = self._observer_factory(use_polling=use_polling)
            try:
                observer.schedule(self._handler, self._watch_dir, recursive=False)
                observer.start()
                self._observer = observer
                if use_polling:
                    log.warning(
                        "native file observer unavailable for %s; using PollingObserver",
                        self._db_path,
                    )
                return
            except Exception:
                mode = "PollingObserver" if use_polling else "native Observer"
                log.exception("failed to start %s for %s", mode, self._db_path)
                try:
                    observer.stop()
                    observer.join(timeout=1)
                except Exception:
                    pass

        self._observer = None

    def _stop_observer(self):
        observer = self._observer
        self._observer = None
        if observer is None:
            return
        observer.stop()
        observer.join()

    def _ensure_observer_running(self):
        observer = self._observer
        if observer is None or observer.is_alive():
            return
        log.warning("file observer stopped for %s; restarting", self._db_path)
        self._stop_observer()
        self._start_observer()

    def _check_for_changes(self):
        self._ensure_observer_running()
        try:
            beans, deps = self._load_fresh()
        except Exception:
            log.exception("poll failed for %s, will retry next cycle", self._db_path)
            return

        if (beans, deps) != self._last_snapshot:
            self._last_snapshot = (beans, deps)
            self.snapshot_changed.emit(beans, deps)
