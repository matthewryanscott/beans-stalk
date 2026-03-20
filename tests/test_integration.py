"""End-to-end integration tests for the full stack."""

from beans import api

from beans_stalk.config import StalkConfig
from beans_stalk.data.store import StalkStore
from beans_stalk.graph.layout import build_dag, compute_layout
from beans_stalk.ui.dag_scene import DagScene


class TestDataToLayoutPipeline:
    def test_full_pipeline(self, tmp_beans_dir, store):
        """Data layer -> graph layer pipeline works end to end."""
        a = api.create_bean(store, "Task A")
        b = api.create_bean(store, "Task B")
        c = api.create_bean(store, "Task C")
        api.add_dep(store, a.id, b.id)
        api.add_dep(store, b.id, c.id)
        store.close()

        ss = StalkStore(tmp_beans_dir / "beans.db")
        beans, deps = ss.load_snapshot()
        ss.close()

        graph = build_dag(beans, deps)
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2

        positions = compute_layout(graph, {a.id, b.id, c.id})
        assert len(positions) == 3


class TestDataToScenePipeline:
    def test_full_pipeline_with_scene(self, tmp_beans_dir, store, qapp):
        """Data layer -> scene layer works end to end."""
        a = api.create_bean(store, "Task A")
        b = api.create_bean(store, "Task B")
        api.add_dep(store, a.id, b.id)
        store.close()

        ss = StalkStore(tmp_beans_dir / "beans.db")
        beans, deps = ss.load_snapshot()
        ss.close()

        config = StalkConfig()
        scene = DagScene(config)
        scene.update_snapshot(beans, deps)

        assert len(scene._nodes) == 2
        assert len(scene._edges) == 1


class TestDrillDownIntegration:
    def test_drill_down_round_trip(self, tmp_beans_dir, store, qapp):
        """Create parent+children, verify drill-down shows correct beans."""
        from beans import api

        from beans_stalk.config import StalkConfig
        from beans_stalk.data.store import StalkStore
        from beans_stalk.ui.dag_scene import DagScene

        parent = api.create_bean(store, "Epic")
        child_a = api.create_bean(store, "Task A", parent_id=parent.id)
        child_b = api.create_bean(store, "Task B", parent_id=parent.id)
        api.add_dep(store, child_a.id, child_b.id)
        store.close()

        ss = StalkStore(tmp_beans_dir / "beans.db")
        beans, deps = ss.load_snapshot()
        ss.close()

        config = StalkConfig()
        scene = DagScene(config)

        # Root view — only parent visible
        scene.update_snapshot(beans, deps)
        assert parent.id in scene._nodes
        assert child_a.id not in scene._nodes

        # Drill down — children visible
        scene.current_parent_id = parent.id
        scene.update_snapshot(beans, deps)
        assert child_a.id in scene._nodes
        assert child_b.id in scene._nodes
        assert parent.id not in scene._nodes

        # Back to root
        scene.current_parent_id = None
        scene.update_snapshot(beans, deps)
        assert parent.id in scene._nodes
        assert child_a.id not in scene._nodes
