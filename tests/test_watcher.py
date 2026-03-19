from beans import api
from beans_stalk.data.watcher import DataWatcher


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
