from datetime import datetime, timezone, timedelta
from beans.models import Bean, BeanId, Dep
from beans_stalk.config import StalkConfig
from beans_stalk.data.store import StalkStore
from beans_stalk.ui.dag_scene import DagScene


def _bean(id_="bean-00000001", title="Test", status="open", assignee=None, closed_at=None):
    return Bean(id=BeanId(id_), title=title, status=status, assignee=assignee, closed_at=closed_at)


def _dep(from_id, to_id):
    return Dep(from_id=BeanId(from_id), to_id=BeanId(to_id))


class TestDagScene:
    def test_empty_shows_placeholder(self, qapp):
        scene = DagScene(StalkConfig())
        scene.update_snapshot([], [])
        assert scene._placeholder is not None
        assert len(scene._nodes) == 0

    def test_beans_create_nodes(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B")]
        scene.update_snapshot(beans, [])
        assert len(scene._nodes) == 2
        assert scene._placeholder is None

    def test_deps_create_edges(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B")]
        deps = [_dep("bean-00000001", "bean-00000002")]
        scene.update_snapshot(beans, deps)
        assert len(scene._edges) == 1

    def test_closed_beans_hidden_by_default(self, qapp):
        scene = DagScene(StalkConfig(fade_minutes=0))
        beans = [
            _bean("bean-00000001", "Open"),
            _bean("bean-00000002", "Closed", status="closed",
                  closed_at=datetime.now(timezone.utc) - timedelta(hours=1)),
        ]
        scene.update_snapshot(beans, [])
        assert "bean-00000001" in scene._nodes
        assert "bean-00000002" not in scene._nodes

    def test_recently_closed_shown_muted(self, qapp):
        scene = DagScene(StalkConfig(fade_minutes=10))
        beans = [
            _bean("bean-00000001", "Just closed", status="closed",
                  closed_at=datetime.now(timezone.utc) - timedelta(minutes=1)),
        ]
        scene.update_snapshot(beans, [])
        assert "bean-00000001" in scene._nodes
        assert scene._nodes["bean-00000001"].muted is True

    def test_show_completed_reveals_all(self, qapp):
        scene = DagScene(StalkConfig(fade_minutes=0))
        scene.show_completed = True
        beans = [
            _bean("bean-00000001", "Closed", status="closed",
                  closed_at=datetime.now(timezone.utc) - timedelta(hours=1)),
        ]
        scene.update_snapshot(beans, [])
        assert "bean-00000001" in scene._nodes

    def test_removed_beans_cleaned_up(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B")]
        scene.update_snapshot(beans, [])
        assert len(scene._nodes) == 2
        scene.update_snapshot([_bean("bean-00000001", "A")], [])
        assert len(scene._nodes) == 1
        assert "bean-00000002" not in scene._nodes

    def test_node_clicked_emits_signal(self, qtbot):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-00000001", "A")]
        scene.update_snapshot(beans, [])
        with qtbot.waitSignal(scene.node_clicked, timeout=1000):
            scene._on_node_clicked("bean-00000001")

    def test_selected_id_updates_selection(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-00000001", "A")]
        scene.update_snapshot(beans, [])
        scene.selected_id = "bean-00000001"
        assert scene._nodes["bean-00000001"].isSelected()
        scene.selected_id = None
        assert not scene._nodes["bean-00000001"].isSelected()

    def test_ready_state_applied_to_nodes(self, qapp, tmp_path):
        db_path = tmp_path / "beans.db"
        store = StalkStore(db_path)
        # Create two beans with a dep: A blocks B
        a = store.create_bean("A")
        b = store.create_bean("B")
        store.add_dep(a.id, b.id)
        beans, deps = store.load_snapshot()
        scene = DagScene(StalkConfig(), store=store)
        scene.update_snapshot(beans, deps)
        # A has no blockers so it should be ready; B is blocked by A
        assert scene._nodes[a.id].ready is True
        assert scene._nodes[b.id].ready is False
        store.close()

    def test_lr_direction_produces_horizontal_layout(self, qapp, tmp_beans_dir, store):
        from beans import api as beans_api
        a = beans_api.create_bean(store, "A")
        b = beans_api.create_bean(store, "B")
        beans_api.add_dep(store, a.id, b.id)
        store.close()
        stalk_store = StalkStore(tmp_beans_dir / "beans.db")
        config = StalkConfig()
        scene = DagScene(config, store=stalk_store)
        scene.direction = "LR"
        beans, deps = stalk_store.load_snapshot()
        scene.update_snapshot(beans, deps)
        assert scene._nodes[a.id].x() < scene._nodes[b.id].x()
        stalk_store.close()

    def test_child_count_applied_to_nodes(self, qapp, tmp_path):
        db_path = tmp_path / "beans.db"
        store = StalkStore(db_path)
        parent = store.create_bean("Parent")
        store.create_bean("Child 1", parent_id=parent.id)
        store.create_bean("Child 2", parent_id=parent.id)
        beans, deps = store.load_snapshot()
        scene = DagScene(StalkConfig(), store=store)
        scene.update_snapshot(beans, deps)
        assert scene._nodes[parent.id].child_count == 2
        store.close()
