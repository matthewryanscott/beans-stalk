import networkx as nx
from beans.models import Bean, Dep

# Spacing constants (pixels)
LAYER_GAP = 60   # vertical space between layers
NODE_GAP = 24    # horizontal space between nodes in a layer
VIRTUAL_WIDTH = 8  # width allocated for virtual routing nodes


def build_dag(beans: list[Bean], deps: list[Dep]) -> nx.DiGraph:
    g = nx.DiGraph()
    bean_ids = set()
    for bean in beans:
        g.add_node(bean.id, bean=bean)
        bean_ids.add(bean.id)
    for dep in deps:
        if dep.from_id in bean_ids and dep.to_id in bean_ids:
            g.add_edge(dep.from_id, dep.to_id, dep_type=dep.dep_type)
    return g


def _assign_layers(graph: nx.DiGraph) -> dict[str, int]:
    """Assign each node to a layer using longest-path-from-roots."""
    layers = {}
    try:
        order = list(nx.topological_sort(graph))
    except nx.NetworkXUnfeasible:
        order = list(graph.nodes())

    for node in order:
        preds = list(graph.predecessors(node))
        if not preds:
            layers[node] = 0
        else:
            layers[node] = max(layers.get(p, 0) for p in preds) + 1
    return layers


def _add_virtual_nodes(
    graph: nx.DiGraph,
    layer_assignment: dict[str, int],
) -> tuple[nx.DiGraph, dict[str, int], set[str]]:
    """Insert virtual nodes for edges that span more than one layer.

    Returns (augmented_graph, updated_layer_assignment, virtual_node_ids).
    """
    aug = graph.copy()
    virtual_ids = set()
    edges_to_split = []

    for u, v in graph.edges():
        u_layer = layer_assignment[u]
        v_layer = layer_assignment[v]
        span = v_layer - u_layer
        if span > 1:
            edges_to_split.append((u, v, span))

    for u, v, span in edges_to_split:
        edge_data = aug.edges[u, v]
        aug.remove_edge(u, v)

        prev = u
        for i in range(1, span):
            vid = f"_virtual_{u}_{v}_{i}"
            virtual_ids.add(vid)
            aug.add_node(vid)
            layer_assignment[vid] = layer_assignment[u] + i
            aug.add_edge(prev, vid, **edge_data)
            prev = vid
        aug.add_edge(prev, v, **edge_data)

    return aug, layer_assignment, virtual_ids


def _order_within_layers(
    graph: nx.DiGraph,
    layer_assignment: dict[str, int],
) -> list[list[str]]:
    """Order nodes within each layer to reduce edge crossings."""
    max_layer = max(layer_assignment.values()) if layer_assignment else 0
    layers: list[list[str]] = [[] for _ in range(max_layer + 1)]
    for node, layer in layer_assignment.items():
        layers[layer].append(node)

    # Initial order: sort by node id for determinism
    for layer in layers:
        layer.sort()

    # Barycenter heuristic with crossing-count selection
    best_layers = [list(layer) for layer in layers]
    best_crossings = _count_all_crossings(graph, best_layers)

    for _ in range(12):
        # Forward sweep
        for i in range(1, len(layers)):
            _sort_by_barycenter(graph, layers[i], layers[i - 1], predecessors=True)
        # Backward sweep
        for i in range(len(layers) - 2, -1, -1):
            _sort_by_barycenter(graph, layers[i], layers[i + 1], predecessors=False)

        crossings = _count_all_crossings(graph, layers)
        if crossings < best_crossings:
            best_crossings = crossings
            best_layers = [list(layer) for layer in layers]

    return best_layers


def _count_crossings(graph: nx.DiGraph, layer_a: list[str], layer_b: list[str]) -> int:
    """Count edge crossings between two adjacent layers."""
    pos_b = {node: i for i, node in enumerate(layer_b)}
    # Collect edges as (position_in_a, position_in_b)
    edges = []
    for i, node in enumerate(layer_a):
        for succ in graph.successors(node):
            if succ in pos_b:
                edges.append((i, pos_b[succ]))

    # Count inversions (crossings)
    crossings = 0
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            if (edges[i][0] - edges[j][0]) * (edges[i][1] - edges[j][1]) < 0:
                crossings += 1
    return crossings


def _count_all_crossings(graph: nx.DiGraph, layers: list[list[str]]) -> int:
    """Count total crossings across all layer pairs."""
    total = 0
    for i in range(len(layers) - 1):
        total += _count_crossings(graph, layers[i], layers[i + 1])
    return total


def _sort_by_barycenter(
    graph: nx.DiGraph,
    layer: list[str],
    ref_layer: list[str],
    predecessors: bool,
):
    """Sort nodes in `layer` by average position of connected nodes in `ref_layer`."""
    ref_pos = {node: i for i, node in enumerate(ref_layer)}

    def barycenter(node):
        if predecessors:
            connected = [p for p in graph.predecessors(node) if p in ref_pos]
        else:
            connected = [s for s in graph.successors(node) if s in ref_pos]
        if not connected:
            return float("inf")
        return sum(ref_pos[c] for c in connected) / len(connected)

    layer.sort(key=barycenter)


def _refine_x_positions(
    graph: nx.DiGraph,
    layers: list[list[str]],
    positions: dict[str, tuple[float, float]],
    sizes: dict[str, tuple[float, float]],
    default_size: tuple[float, float],
) -> dict[str, tuple[float, float]]:
    """Shift nodes horizontally toward their connected nodes' average X, avoiding overlaps."""
    for _ in range(4):
        # Compute target X for each node (average center X of neighbors)
        targets: dict[str, float] = {}
        for node in positions:
            w = sizes.get(node, default_size)[0]
            center = positions[node][0] + w / 2
            neighbors = list(graph.predecessors(node)) + list(graph.successors(node))
            connected = [n for n in neighbors if n in positions]
            if connected:
                avg = sum(
                    positions[n][0] + sizes.get(n, default_size)[0] / 2
                    for n in connected
                ) / len(connected)
                targets[node] = avg - w / 2
            else:
                targets[node] = positions[node][0]

        # Apply targets within each layer, resolving overlaps
        for layer in layers:
            if not layer:
                continue
            # Sort by current position
            layer_nodes = sorted(layer, key=lambda n: positions[n][0])
            # Apply targets
            new_xs = {n: targets.get(n, positions[n][0]) for n in layer_nodes}
            # Resolve overlaps left to right
            for i in range(1, len(layer_nodes)):
                prev = layer_nodes[i - 1]
                curr = layer_nodes[i]
                prev_right = new_xs[prev] + sizes.get(prev, default_size)[0] + NODE_GAP
                if new_xs[curr] < prev_right:
                    new_xs[curr] = prev_right
            # Also resolve right to left for balance
            for i in range(len(layer_nodes) - 2, -1, -1):
                curr = layer_nodes[i]
                nxt = layer_nodes[i + 1]
                max_x = new_xs[nxt] - sizes.get(curr, default_size)[0] - NODE_GAP
                if new_xs[curr] > max_x:
                    new_xs[curr] = max_x

            for n in layer_nodes:
                positions[n] = (new_xs[n], positions[n][1])

    return positions


def compute_layout(
    graph: nx.DiGraph,
    visible_ids: set[str],
    node_sizes: dict[str, tuple[float, float]] | None = None,
) -> dict[str, tuple[float, float]]:
    """Compute node positions using a custom Sugiyama-style layered layout."""
    if not visible_ids:
        return {}

    subgraph = graph.subgraph(visible_ids).copy()
    if len(subgraph) == 0:
        return {}

    sizes = dict(node_sizes) if node_sizes else {}
    default_size = (140.0, 30.0)

    # Step 1: Assign layers
    layer_assignment = _assign_layers(subgraph)

    # Step 2: Add virtual nodes for long edges
    aug_graph, layer_assignment, virtual_ids = _add_virtual_nodes(subgraph, layer_assignment)
    for vid in virtual_ids:
        sizes[vid] = (VIRTUAL_WIDTH, 0)

    # Step 3: Order within layers to reduce crossings
    layers = _order_within_layers(aug_graph, layer_assignment)

    # Step 4: Compute initial coordinates
    positions = {}
    y = 0.0
    for layer in layers:
        real_nodes = [n for n in layer if n not in virtual_ids]
        layer_height = max(
            (sizes.get(n, default_size)[1] for n in real_nodes),
            default=20,
        )

        total_width = sum(sizes.get(n, default_size)[0] for n in layer)
        total_width += NODE_GAP * (len(layer) - 1) if len(layer) > 1 else 0
        x = -total_width / 2

        for node in layer:
            w, h = sizes.get(node, default_size)
            node_y = y + (layer_height - h) / 2
            positions[node] = (x, node_y)
            x += w + NODE_GAP

        y += layer_height + LAYER_GAP

    # Step 5: Refine horizontal positions
    positions = _refine_x_positions(aug_graph, layers, positions, sizes, default_size)

    # Strip virtual nodes from output
    return {nid: pos for nid, pos in positions.items() if nid not in virtual_ids}


def stabilize_layout(
    new_positions: dict[str, tuple[float, float]],
    old_positions: dict[str, tuple[float, float]],
    anchor_id: str | None,
) -> dict[str, tuple[float, float]]:
    if (
        anchor_id is None
        or anchor_id not in new_positions
        or anchor_id not in old_positions
    ):
        return new_positions
    old_x, old_y = old_positions[anchor_id]
    new_x, new_y = new_positions[anchor_id]
    dx = old_x - new_x
    dy = old_y - new_y
    return {nid: (x + dx, y + dy) for nid, (x, y) in new_positions.items()}
