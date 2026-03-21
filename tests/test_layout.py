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
        # Each node should be on a different layer (different Y)
        ys = [positions[nid][1] for nid in sorted(visible)]
        assert len(set(ys)) == 3
        # Y should increase (top to bottom in screen coords)
        assert ys[0] < ys[1] < ys[2]

    def test_parallel_nodes_same_layer(self):
        beans = [_bean("bean-00000001", "Root"), _bean("bean-00000002", "A"), _bean("bean-00000003", "B")]
        deps = [_dep("bean-00000001", "bean-00000002"), _dep("bean-00000001", "bean-00000003")]
        g = build_dag(beans, deps)
        visible = {"bean-00000001", "bean-00000002", "bean-00000003"}
        positions = compute_layout(g, visible)
        # A and B should be on the same layer
        assert positions["bean-00000002"][1] == positions["bean-00000003"][1]
        # But different X
        assert positions["bean-00000002"][0] != positions["bean-00000003"][0]

    def test_nodes_do_not_overlap(self):
        beans = [_bean(f"bean-0000000{i}", f"Task {i}") for i in range(5)]
        deps = [_dep("bean-00000000", f"bean-0000000{i}") for i in range(1, 5)]
        g = build_dag(beans, deps)
        visible = {b.id for b in beans}
        sizes = {b.id: (140.0, 30.0) for b in beans}
        positions = compute_layout(g, visible, node_sizes=sizes)
        # Check no horizontal overlap within layers
        from collections import defaultdict
        by_y = defaultdict(list)
        for nid, (x, y) in positions.items():
            by_y[y].append((x, sizes[nid][0]))
        for y, nodes_in_row in by_y.items():
            nodes_in_row.sort()
            for i in range(len(nodes_in_row) - 1):
                x1, w1 = nodes_in_row[i]
                x2, _ = nodes_in_row[i + 1]
                assert x2 >= x1 + w1, f"Overlap at y={y}: {x1}+{w1} vs {x2}"


    def test_two_clusters_stay_separated(self):
        """Two independent subgraphs should not collapse horizontally."""
        # Cluster A: a1 -> a2 -> a3
        # Cluster B: b1 -> b2 -> b3
        # No edges between clusters
        beans = [
            _bean("bean-a0000001", "A1"), _bean("bean-a0000002", "A2"), _bean("bean-a0000003", "A3"),
            _bean("bean-b0000001", "B1"), _bean("bean-b0000002", "B2"), _bean("bean-b0000003", "B3"),
        ]
        deps = [
            _dep("bean-a0000001", "bean-a0000002"), _dep("bean-a0000002", "bean-a0000003"),
            _dep("bean-b0000001", "bean-b0000002"), _dep("bean-b0000002", "bean-b0000003"),
        ]
        g = build_dag(beans, deps)
        visible = {b.id for b in beans}
        sizes = {b.id: (140.0, 30.0) for b in beans}
        positions = compute_layout(g, visible, node_sizes=sizes)

        # In each shared layer, the two cluster nodes should not overlap
        # Layer 0: a1, b1  Layer 1: a2, b2  Layer 2: a3, b3
        for a_id, b_id in [
            ("bean-a0000001", "bean-b0000001"),
            ("bean-a0000002", "bean-b0000002"),
            ("bean-a0000003", "bean-b0000003"),
        ]:
            ax = positions[a_id][0]
            bx = positions[b_id][0]
            gap = abs(bx - ax)
            assert gap >= 140.0, f"Clusters too close: {a_id} at {ax}, {b_id} at {bx}"

    def test_long_edge_virtual_nodes_not_through_real_nodes(self):
        """An edge spanning multiple layers should route around real nodes."""
        # root -> A, root -> B, A -> C (all on consecutive layers)
        # root -> C spans 2 layers, gets a virtual node on layer 1
        # Virtual node should not occupy same x-space as A or B
        beans = [
            _bean("bean-00000001", "Root"),
            _bean("bean-00000002", "A"),
            _bean("bean-00000003", "B"),
            _bean("bean-00000004", "C"),
        ]
        deps = [
            _dep("bean-00000001", "bean-00000002"),
            _dep("bean-00000001", "bean-00000003"),
            _dep("bean-00000002", "bean-00000004"),
            _dep("bean-00000001", "bean-00000004"),  # long edge: root -> C
        ]
        g = build_dag(beans, deps)
        visible = {b.id for b in beans}
        sizes = {b.id: (140.0, 30.0) for b in beans}
        positions = compute_layout(g, visible, node_sizes=sizes)

        # All visible nodes should exist
        assert len(positions) == 4
        # Nodes in the same layer should not overlap (already tested above,
        # but this graph specifically has a virtual node competing with real nodes)
        from collections import defaultdict
        by_y = defaultdict(list)
        for nid, (x, y) in positions.items():
            by_y[y].append((x, sizes[nid][0]))
        for y, nodes_in_row in by_y.items():
            nodes_in_row.sort()
            for i in range(len(nodes_in_row) - 1):
                x1, w1 = nodes_in_row[i]
                x2, _ = nodes_in_row[i + 1]
                assert x2 >= x1 + w1, f"Overlap at y={y}: {x1}+{w1} vs {x2}"

    def test_layout_is_deterministic(self):
        """Same input should always produce the exact same layout."""
        beans = [_bean(f"bean-0000000{i}", f"Task {i}") for i in range(6)]
        deps = [
            _dep("bean-00000000", "bean-00000001"),
            _dep("bean-00000000", "bean-00000002"),
            _dep("bean-00000001", "bean-00000003"),
            _dep("bean-00000002", "bean-00000004"),
            _dep("bean-00000003", "bean-00000005"),
            _dep("bean-00000004", "bean-00000005"),
        ]
        g = build_dag(beans, deps)
        visible = {b.id for b in beans}
        sizes = {b.id: (140.0, 30.0) for b in beans}

        pos1 = compute_layout(g, visible, node_sizes=sizes)
        pos2 = compute_layout(g, visible, node_sizes=sizes)
        assert pos1 == pos2


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
