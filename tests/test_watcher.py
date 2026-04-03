from beans import api
from beans.store import Store
from beans_stalk.data.watcher import DataWatcher, _DbFileHandler


class TestDataWatcher:
    def test_emits_initial_snapshot(self, tmp_beans_dir, store, qtbot):
        api.create_bean(store, "Existing bean")
        watcher = DataWatcher(db_path=tmp_beans_dir / "beans.db", poll_interval_seconds=10)
        with qtbot.waitSignal(watcher.snapshot_changed, timeout=1000) as blocker:
            watcher.start()
        watcher.stop()
        beans, deps = blocker.args
        assert any(b.title == "Existing bean" for b in beans)

    def test_detects_change_on_poll(self, tmp_beans_dir, store, qtbot):
        watcher = DataWatcher(db_path=tmp_beans_dir / "beans.db", poll_interval_seconds=0.1)
        watcher.start()
        qtbot.waitSignal(watcher.snapshot_changed, timeout=1000)
        api.create_bean(store, "New bean")
        with qtbot.waitSignal(watcher.snapshot_changed, timeout=2000) as blocker:
            pass
        watcher.stop()
        beans, deps = blocker.args
        assert any(b.title == "New bean" for b in beans)

    def test_no_spurious_signals_without_changes(self, tmp_beans_dir, qtbot):
        watcher = DataWatcher(db_path=tmp_beans_dir / "beans.db", poll_interval_seconds=0.1)
        signals = []
        watcher.snapshot_changed.connect(lambda b, d: signals.append((b, d)))
        watcher.start()
        qtbot.wait(500)
        watcher.stop()
        assert len(signals) == 1  # only initial

    def test_stop_is_idempotent(self, tmp_beans_dir):
        watcher = DataWatcher(db_path=tmp_beans_dir / "beans.db", poll_interval_seconds=1)
        watcher.start()
        watcher.stop()
        watcher.stop()  # Should not raise

    def test_detects_external_write_without_waiting_for_long_poll(
        self, tmp_beans_dir, store, qtbot
    ):
        watcher = DataWatcher(db_path=tmp_beans_dir / "beans.db", poll_interval_seconds=60)
        watcher.start()
        qtbot.waitSignal(watcher.snapshot_changed, timeout=1000)

        api.create_bean(store, "Fast external bean")

        with qtbot.waitSignal(watcher.snapshot_changed, timeout=1500) as blocker:
            pass

        watcher.stop()
        beans, deps = blocker.args
        assert any(b.title == "Fast external bean" for b in beans)

    def test_detects_atomic_db_replacement_from_same_directory(self, tmp_beans_dir, qtbot):
        original_db = tmp_beans_dir / "beans.db"
        watcher = DataWatcher(db_path=original_db, poll_interval_seconds=60)
        watcher.start()
        qtbot.waitSignal(watcher.snapshot_changed, timeout=1000)

        replacement_db = tmp_beans_dir / "beans-replacement.db"
        replacement_store = Store.from_path(str(replacement_db))
        try:
            api.create_bean(replacement_store, "Replaced bean")
        finally:
            replacement_store.close()

        replacement_db.replace(original_db)

        with qtbot.waitSignal(watcher.snapshot_changed, timeout=1500) as blocker:
            pass

        watcher.stop()
        beans, deps = blocker.args
        assert any(b.title == "Replaced bean" for b in beans)

    def test_file_handler_triggers_when_db_is_moved_into_place(self, tmp_path):
        triggered = []
        handler = _DbFileHandler(tmp_path / "beans.db", lambda: triggered.append(True))

        class Event:
            is_directory = False
            src_path = str(tmp_path / "beans.tmp")
            dest_path = str(tmp_path / "beans.db")

        handler.on_moved(Event())

        assert triggered == [True]
