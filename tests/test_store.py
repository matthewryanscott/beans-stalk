from beans.models import Bean, Dep
from beans import api
from beans_stalk.data.store import StalkStore


class TestStalkStore:
    def test_open_and_close(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        assert ss.store is not None
        ss.close()

    def test_load_snapshot_empty(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        beans, deps = ss.load_snapshot()
        assert beans == []
        assert deps == []
        ss.close()

    def test_load_snapshot_with_beans(self, tmp_beans_dir, store):
        api.create_bean(store, "Task A")
        api.create_bean(store, "Task B")
        store.close()
        ss = StalkStore(tmp_beans_dir / "beans.db")
        beans, deps = ss.load_snapshot()
        assert len(beans) == 2
        titles = {b.title for b in beans}
        assert titles == {"Task A", "Task B"}
        ss.close()

    def test_load_snapshot_with_deps(self, tmp_beans_dir, store):
        a = api.create_bean(store, "Task A")
        b = api.create_bean(store, "Task B")
        api.add_dep(store, a.id, b.id)
        store.close()
        ss = StalkStore(tmp_beans_dir / "beans.db")
        beans, deps = ss.load_snapshot()
        assert len(deps) == 1
        assert deps[0].from_id == a.id
        assert deps[0].to_id == b.id
        ss.close()

    def test_create_bean(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        bean = ss.create_bean("New Task", type="bug", priority=1)
        assert bean.title == "New Task"
        assert bean.type == "bug"
        assert bean.priority == 1
        ss.close()

    def test_update_bean(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        bean = ss.create_bean("Original")
        updated = ss.update_bean(bean.id, title="Updated")
        assert updated.title == "Updated"
        ss.close()

    def test_close_bean(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        bean = ss.create_bean("To close")
        closed = ss.close_bean(bean.id, reason="Done")
        assert closed.status == "closed"
        assert closed.close_reason == "Done"
        ss.close()

    def test_add_and_remove_dep(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        a = ss.create_bean("A")
        b = ss.create_bean("B")
        dep = ss.add_dep(a.id, b.id)
        assert dep.from_id == a.id
        ss.remove_dep(a.id, b.id)
        _, deps = ss.load_snapshot()
        assert len(deps) == 0
        ss.close()

    def test_claim_and_release(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        bean = ss.create_bean("Claimable")
        claimed = ss.claim_bean(bean.id, "alice")
        assert claimed.assignee == "alice"
        assert claimed.status == "in_progress"
        released = ss.release_bean(bean.id, "alice")
        assert released.assignee is None
        assert released.status == "open"
        ss.close()

    def test_delete_bean(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        bean = ss.create_bean("To delete")
        ss.delete_bean(bean.id)
        beans, _ = ss.load_snapshot()
        assert len(beans) == 0
        ss.close()

    def test_ready_bean_ids(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        a = ss.create_bean("Ready A")
        b = ss.create_bean("Ready B")
        blocker = ss.create_bean("Blocker")
        ss.add_dep(blocker.id, b.id)  # blocker blocks b
        ready = ss.ready_bean_ids()
        assert a.id in ready
        assert b.id not in ready  # blocked
        assert blocker.id in ready
        ss.close()

    def test_data_version(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        v1 = ss.data_version()
        ss.create_bean("Trigger change")
        v2 = ss.data_version()
        assert v2 != v1
        ss.close()
