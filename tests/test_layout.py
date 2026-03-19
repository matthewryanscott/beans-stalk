from beans.models import Bean, BeanId, Dep
from beans_stalk.graph.layout import build_dag, compute_layout, stabilize_layout


def _bean(id_: str, title: str, status: str = "open", assignee: str | None = None) -> Bean:
    return Bean(id=BeanId(id_), title=title, status=status, assignee=assignee)


def _dep(from_id: str, to_id: str) -> Dep:
    return Dep(from_id=BeanId(from_id), to_id=BeanId(to_id))


class TestBuildDag:
    def test_empty(self):
        g = build_dag([], [])
        assert len(g.nodes) == 0
        assert len(g.edges) == 0

    def test_single_bean(self):
        beans = [_bean("bean-00000001", "Task A")]
        g = build_dag(beans, [])
        assert list(g.nodes) == ["bean-00000001"]
        assert g.nodes["bean-00000001"]["bean"].title == "Task A"

    def test_with_dependency(self):
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B")]
        deps = [_dep("bean-00000001", "bean-00000002")]
        g = build_dag(beans, deps)
        assert ("bean-00000001", "bean-00000002") in g.edges

    def test_ignores_deps_for_missing_beans(self):
        beans = [_bean("bean-00000001", "A")]
        deps = [_dep("bean-00000001", "bean-99999999")]
        g = build_dag(beans, deps)
        assert len(g.edges) == 0


class TestComputeLayout:
    def test_empty(self):
        g = build_dag([], [])
        positions = compute_layout(g, set())
        assert positions == {}

    def test_single_node(self):
        beans = [_bean("bean-00000001", "A")]
        g = build_dag(beans, [])
        positions = compute_layout(g, {"bean-00000001"})
        assert "bean-00000001" in positions
        x, y = positions["bean-00000001"]
        assert isinstance(x, float)
        assert isinstance(y, float)

    def test_filters_to_visible_ids(self):
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B")]
        g = build_dag(beans, [])
        positions = compute_layout(g, {"bean-00000001"})
        assert "bean-00000001" in positions
        assert "bean-00000002" not in positions

    def test_chain_layout_is_vertical(self):
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B"), _bean("bean-00000003", "C")]
        deps = [_dep("bean-00000001", "bean-00000002"), _dep("bean-00000002", "bean-00000003")]
        g = build_dag(beans, deps)
        visible = {"bean-00000001", "bean-00000002", "bean-00000003"}
        positions = compute_layout(g, visible)
        ys = [positions[nid][1] for nid in sorted(visible)]
        assert len(set(ys)) == 3


class TestStabilizeLayout:
    def test_anchors_selected_node(self):
        old = {"a": (100.0, 200.0), "b": (150.0, 250.0)}
        new = {"a": (50.0, 100.0), "b": (100.0, 150.0)}
        result = stabilize_layout(new, old, anchor_id="a")
        assert result["a"] == (100.0, 200.0)
        assert result["b"] == (150.0, 250.0)

    def test_no_anchor_returns_unchanged(self):
        new = {"a": (50.0, 100.0)}
        result = stabilize_layout(new, {}, anchor_id=None)
        assert result == new

    def test_missing_anchor_returns_unchanged(self):
        new = {"a": (50.0, 100.0)}
        old = {"b": (100.0, 200.0)}
        result = stabilize_layout(new, old, anchor_id="x")
        assert result == new
