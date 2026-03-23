import pytest

from beans.models import Bean, BeanId, Dep
from beans_stalk.graph.layout import _assign_layers_late, build_dag
from beans_stalk.graph.layouts import PROVIDERS, get_provider


def _bean(id_: str, title: str) -> Bean:
    return Bean(id=BeanId(id_), title=title, status="open")


def _dep(from_id: str, to_id: str) -> Dep:
    return Dep(from_id=BeanId(from_id), to_id=BeanId(to_id))


class TestRegistry:
    def test_sugiyama_registered(self):
        assert "sugiyama" in PROVIDERS

    def test_get_provider_returns_module(self):
        provider = get_provider("sugiyama")
        assert provider.KEY == "sugiyama"
        assert provider.NAME == "Sugiyama"
        assert callable(provider.compute)

    def test_get_provider_fallback(self):
        provider = get_provider("nonexistent")
        assert provider.KEY == "sugiyama"


class TestSugiyamaProvider:
    def test_compute_returns_positions(self):
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B")]
        deps = [_dep("bean-00000001", "bean-00000002")]
        g = build_dag(beans, deps)
        provider = get_provider("sugiyama")
        positions = provider.compute(g, {"bean-00000001", "bean-00000002"})
        assert "bean-00000001" in positions
        assert "bean-00000002" in positions


class TestLateLayers:
    def test_late_assignment_pulls_nodes_down(self):
        """A -> C, B -> C: with late assignment, A and B should be on layer
        just above C, not at the top."""
        beans = [_bean("bean-a", "A"), _bean("bean-b", "B"), _bean("bean-c", "C")]
        deps = [_dep("bean-a", "bean-c"), _dep("bean-b", "bean-c")]
        g = build_dag(beans, deps)
        sub = g.subgraph({"bean-a", "bean-b", "bean-c"}).copy()
        layers = _assign_layers_late(sub)
        assert layers["bean-c"] > layers["bean-a"]
        assert layers["bean-c"] > layers["bean-b"]
        assert layers["bean-a"] == layers["bean-b"]
        assert max(layers.values()) == 1

    def test_late_vs_early_diamond(self):
        """root -> A -> C, root -> B -> C, root -> C."""
        beans = [_bean("bean-r", "Root"), _bean("bean-a", "A"), _bean("bean-b", "B"), _bean("bean-c", "C")]
        deps = [_dep("bean-r", "bean-a"), _dep("bean-r", "bean-b"), _dep("bean-a", "bean-c"), _dep("bean-b", "bean-c"), _dep("bean-r", "bean-c")]
        g = build_dag(beans, deps)
        sub = g.subgraph({"bean-r", "bean-a", "bean-b", "bean-c"}).copy()
        layers = _assign_layers_late(sub)
        assert layers["bean-r"] == 0
        assert layers["bean-a"] == 1
        assert layers["bean-b"] == 1
        assert layers["bean-c"] == 2


class TestSugiyamaCompactProvider:
    def test_registered(self):
        assert "sugiyama_compact" in PROVIDERS

    def test_compute_returns_positions(self):
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B")]
        deps = [_dep("bean-00000001", "bean-00000002")]
        g = build_dag(beans, deps)
        provider = get_provider("sugiyama_compact")
        positions = provider.compute(g, {"bean-00000001", "bean-00000002"})
        assert "bean-00000001" in positions
        assert "bean-00000002" in positions

    def test_compact_reduces_layers_for_independent_node(self):
        """Node with no predecessors but one successor should be placed just
        above that successor, not at layer 0."""
        beans = [_bean("bean-a", "A"), _bean("bean-b", "B"), _bean("bean-c", "C")]
        deps = [_dep("bean-a", "bean-c"), _dep("bean-b", "bean-c")]
        g = build_dag(beans, deps)
        provider_std = get_provider("sugiyama")
        provider_cmp = get_provider("sugiyama_compact")
        pos_std = provider_std.compute(g, {"bean-a", "bean-b", "bean-c"})
        pos_cmp = provider_cmp.compute(g, {"bean-a", "bean-b", "bean-c"})
        assert len(pos_std) == 3
        assert len(pos_cmp) == 3


class TestDirectionLR:
    """All providers must accept direction='LR' and swap axes."""

    def _chain_graph(self):
        beans = [_bean("bean-a", "A"), _bean("bean-b", "B"), _bean("bean-c", "C")]
        deps = [_dep("bean-a", "bean-b"), _dep("bean-b", "bean-c")]
        return build_dag(beans, deps), {"bean-a", "bean-b", "bean-c"}

    # -- Sugiyama --

    def test_sugiyama_tb_flows_downward(self):
        g, vis = self._chain_graph()
        pos = get_provider("sugiyama").compute(g, vis, direction="TB")
        # A above B above C  (smaller y = higher on screen)
        assert pos["bean-a"][1] < pos["bean-b"][1] < pos["bean-c"][1]

    def test_sugiyama_lr_flows_rightward(self):
        g, vis = self._chain_graph()
        pos = get_provider("sugiyama").compute(g, vis, direction="LR")
        # A left of B left of C  (smaller x = further left)
        assert pos["bean-a"][0] < pos["bean-b"][0] < pos["bean-c"][0]

    def test_sugiyama_lr_single_component(self):
        """Ensure LR works even for single-component graphs (no early return)."""
        beans = [_bean("bean-x", "X"), _bean("bean-y", "Y")]
        deps = [_dep("bean-x", "bean-y")]
        g = build_dag(beans, deps)
        pos = get_provider("sugiyama").compute(g, {"bean-x", "bean-y"}, direction="LR")
        assert pos["bean-x"][0] < pos["bean-y"][0]

    # -- Sugiyama Compact --

    def test_sugiyama_compact_tb_flows_downward(self):
        g, vis = self._chain_graph()
        pos = get_provider("sugiyama_compact").compute(g, vis, direction="TB")
        assert pos["bean-a"][1] < pos["bean-b"][1] < pos["bean-c"][1]

    def test_sugiyama_compact_lr_flows_rightward(self):
        g, vis = self._chain_graph()
        pos = get_provider("sugiyama_compact").compute(g, vis, direction="LR")
        assert pos["bean-a"][0] < pos["bean-b"][0] < pos["bean-c"][0]

    def test_sugiyama_compact_lr_single_component(self):
        beans = [_bean("bean-x", "X"), _bean("bean-y", "Y")]
        deps = [_dep("bean-x", "bean-y")]
        g = build_dag(beans, deps)
        pos = get_provider("sugiyama_compact").compute(g, {"bean-x", "bean-y"}, direction="LR")
        assert pos["bean-x"][0] < pos["bean-y"][0]

    # -- Graphviz dot --

    def test_graphviz_dot_lr_flows_rightward(self):
        pytest.importorskip("pygraphviz")
        g, vis = self._chain_graph()
        pos = get_provider("graphviz_dot").compute(g, vis, direction="LR")
        assert pos["bean-a"][0] < pos["bean-b"][0] < pos["bean-c"][0]

    def test_graphviz_dot_tb_default(self):
        pytest.importorskip("pygraphviz")
        g, vis = self._chain_graph()
        pos = get_provider("graphviz_dot").compute(g, vis)
        # Default is TB: A above B above C
        assert pos["bean-a"][1] < pos["bean-b"][1] < pos["bean-c"][1]


class TestGraphvizDotProvider:
    def test_registered_if_pygraphviz_available(self):
        pytest.importorskip("pygraphviz")
        assert "graphviz_dot" in PROVIDERS

    def test_compute_returns_positions(self):
        pytest.importorskip("pygraphviz")
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B")]
        deps = [_dep("bean-00000001", "bean-00000002")]
        g = build_dag(beans, deps)
        provider = get_provider("graphviz_dot")
        positions = provider.compute(g, {"bean-00000001", "bean-00000002"})
        assert "bean-00000001" in positions
        assert "bean-00000002" in positions
        # A should be above B (smaller Y)
        assert positions["bean-00000001"][1] < positions["bean-00000002"][1]

    def test_empty_graph(self):
        pytest.importorskip("pygraphviz")
        g = build_dag([], [])
        provider = get_provider("graphviz_dot")
        positions = provider.compute(g, set())
        assert positions == {}
