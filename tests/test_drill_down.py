from datetime import datetime, timezone
from beans.models import Bean, BeanId, Dep
from beans_stalk.config import StalkConfig
from beans_stalk.ui.dag_scene import DagScene


def _bean(id_, title="Test", status="open", assignee=None, parent_id=None, **kwargs):
    return Bean(id=BeanId(id_), title=title, status=status, assignee=assignee, parent_id=parent_id, **kwargs)


def _dep(from_id, to_id):
    return Dep(from_id=BeanId(from_id), to_id=BeanId(to_id))


class TestDrillDownFiltering:
    def test_root_shows_only_parentless_beans(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Root task"),
            _bean("bean-002", "Child task", parent_id="bean-001"),
        ]
        scene.update_snapshot(beans, [])
        assert "bean-001" in scene._nodes
        assert "bean-002" not in scene._nodes

    def test_drill_down_shows_children(self, qapp):
        scene = DagScene(StalkConfig())
        scene.current_parent_id = "bean-001"
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child A", parent_id="bean-001"),
            _bean("bean-003", "Child B", parent_id="bean-001"),
        ]
        scene.update_snapshot(beans, [])
        assert "bean-001" not in scene._nodes
        assert "bean-002" in scene._nodes
        assert "bean-003" in scene._nodes

    def test_root_view_after_drill_down(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child", parent_id="bean-001"),
        ]
        scene.current_parent_id = "bean-001"
        scene.update_snapshot(beans, [])
        assert "bean-002" in scene._nodes

        scene.current_parent_id = None
        scene.update_snapshot(beans, [])
        assert "bean-001" in scene._nodes
        assert "bean-002" not in scene._nodes


class TestGhostNodes:
    def test_cross_level_dep_creates_ghost(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Root A"),
            _bean("bean-002", "Root B"),
            _bean("bean-003", "Child of A", parent_id="bean-001"),
        ]
        deps = [_dep("bean-003", "bean-002")]
        scene.current_parent_id = "bean-001"
        scene.update_snapshot(beans, deps)
        assert "bean-003" in scene._nodes
        assert not scene._nodes["bean-003"].ghost
        assert "bean-002" in scene._nodes
        assert scene._nodes["bean-002"].ghost

    def test_no_transitive_ghosts(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child", parent_id="bean-001"),
            _bean("bean-003", "External A"),
            _bean("bean-004", "External B"),
        ]
        deps = [
            _dep("bean-002", "bean-003"),
            _dep("bean-003", "bean-004"),
        ]
        scene.current_parent_id = "bean-001"
        scene.update_snapshot(beans, deps)
        assert "bean-003" in scene._nodes
        assert "bean-004" not in scene._nodes

    def test_ghost_to_ghost_edge_shown(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child", parent_id="bean-001"),
            _bean("bean-003", "External A"),
            _bean("bean-004", "External B"),
        ]
        deps = [
            _dep("bean-002", "bean-003"),
            _dep("bean-002", "bean-004"),
            _dep("bean-003", "bean-004"),
        ]
        scene.current_parent_id = "bean-001"
        scene.update_snapshot(beans, deps)
        assert ("bean-003", "bean-004") in scene._edges


class TestPulsingLogic:
    def test_claimed_bean_pulses(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-001", "Claimed", status="in_progress", assignee="alice")]
        scene.update_snapshot(beans, [])
        assert scene._nodes["bean-001"].pulsing

    def test_unclaimed_bean_does_not_pulse(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-001", "Open")]
        scene.update_snapshot(beans, [])
        assert not scene._nodes["bean-001"].pulsing

    def test_parent_pulses_when_child_claimed(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child", status="in_progress", assignee="alice", parent_id="bean-001"),
        ]
        scene.update_snapshot(beans, [])
        assert "bean-001" in scene._nodes
        assert scene._nodes["bean-001"].pulsing

    def test_grandparent_pulses_when_grandchild_claimed(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Grandparent"),
            _bean("bean-002", "Parent", parent_id="bean-001"),
            _bean("bean-003", "Child", status="in_progress", assignee="bob", parent_id="bean-002"),
        ]
        scene.update_snapshot(beans, [])
        assert scene._nodes["bean-001"].pulsing


class TestHasChildren:
    def test_parent_detected(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child", parent_id="bean-001"),
        ]
        scene.update_snapshot(beans, [])
        assert "bean-001" in scene._parent_ids

    def test_childless_not_parent(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-001", "Leaf")]
        scene.update_snapshot(beans, [])
        assert "bean-001" not in scene._parent_ids


class TestEmptyDrillDown:
    def test_all_children_closed_shows_message(self, qapp):
        scene = DagScene(StalkConfig(fade_minutes=0))
        scene.current_parent_id = "bean-001"
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child", status="closed", parent_id="bean-001",
                  closed_at=datetime(2020, 1, 1, tzinfo=timezone.utc)),
        ]
        scene.update_snapshot(beans, [])
        assert scene._placeholder is not None
        assert "closed" in scene._placeholder.toPlainText().lower()
