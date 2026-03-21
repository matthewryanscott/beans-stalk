import networkx as nx
from beans.models import Bean, Dep

# Spacing constants (pixels)
LAYER_GAP = 60   # vertical space between layers
NODE_GAP = 24    # horizontal space between nodes in a layer
VIRTUAL_WIDTH = 24  # width allocated for virtual routing nodes (edge buffer)


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

    for _ in range(24):
        # Forward sweep
        for i in range(1, len(layers)):
            _sort_by_barycenter(graph, layers[i], layers[i - 1], predecessors=True)
        # Backward sweep
        for i in range(len(layers) - 2, -1, -1):
            _sort_by_barycenter(graph, layers[i], layers[i + 1], predecessors=False)

        # Adjacent exchange pass — swap neighbors if it reduces crossings
        for i in range(len(layers) - 1):
            _adjacent_exchange(graph, layers[i], layers[i + 1])
        for i in range(len(layers) - 2, -1, -1):
            _adjacent_exchange(graph, layers[i + 1], layers[i])

        crossings = _count_all_crossings(graph, layers)
        if crossings < best_crossings:
            best_crossings = crossings
            best_layers = [list(layer) for layer in layers]

    return best_layers


def _adjacent_exchange(
    graph: nx.DiGraph,
    layer: list[str],
    neighbor_layer: list[str],
):
    """Swap adjacent nodes in `layer` if it reduces crossings with `neighbor_layer`."""
    improved = True
    while improved:
        improved = False
        for i in range(len(layer) - 1):
            before = _count_crossings(graph, layer, neighbor_layer)
            layer[i], layer[i + 1] = layer[i + 1], layer[i]
            after = _count_crossings(graph, layer, neighbor_layer)
            if after < before:
                improved = True
            else:
                layer[i], layer[i + 1] = layer[i + 1], layer[i]


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


def _median(values: list[float]) -> float:
    """Return the median of a list of floats."""
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def _global_center_shift(
    positions: dict[str, tuple[float, float]],
    sizes: dict[str, tuple[float, float]],
    default_size: tuple[float, float],
) -> None:
    """Shift all positions so the graph bounding box is centered at x=0."""
    if not positions:
        return
    all_xs = []
    all_rights = []
    for nid, (x, _) in positions.items():
        all_xs.append(x)
        all_rights.append(x + sizes.get(nid, default_size)[0])
    global_center = (min(all_xs) + max(all_rights)) / 2
    for nid in positions:
        x, y = positions[nid]
        positions[nid] = (x - global_center, y)


def _sweep_layer(
    graph: nx.DiGraph,
    layer: list[str],
    positions: dict[str, tuple[float, float]],
    sizes: dict[str, tuple[float, float]],
    default_size: tuple[float, float],
    virtual_ids: set[str],
    direction: str,
):
    """Position nodes in a layer based on connected nodes in the reference direction.

    direction='down': use predecessors (parent positions determine child positions)
    direction='up': use successors (child positions gently adjust parent positions)
    """
    real_damping = 0.5 if direction == "down" else 0.08
    virtual_damping = 0.8 if direction == "down" else 0.3

    layer_nodes = sorted(layer, key=lambda n: positions[n][0])
    new_xs: dict[str, float] = {}

    for node in layer_nodes:
        w = sizes.get(node, default_size)[0]
        current_x = positions[node][0]
        damping = virtual_damping if node in virtual_ids else real_damping

        if direction == "down":
            ref_nodes = [p for p in graph.predecessors(node) if p in positions]
        else:
            ref_nodes = [s for s in graph.successors(node) if s in positions]

        # Fallback: if no refs in primary direction, use the other direction
        # This centers root nodes above their children, and leaf nodes under parents
        if not ref_nodes:
            if direction == "down":
                ref_nodes = [s for s in graph.successors(node) if s in positions]
            else:
                ref_nodes = [p for p in graph.predecessors(node) if p in positions]

        if ref_nodes:
            ref_centers = [
                positions[n][0] + sizes.get(n, default_size)[0] / 2
                for n in ref_nodes
            ]
            target_center = _median(ref_centers)
            target_x = target_center - w / 2
            new_xs[node] = current_x + (target_x - current_x) * damping
        else:
            new_xs[node] = current_x

    # Resolve overlaps left to right
    for i in range(1, len(layer_nodes)):
        prev = layer_nodes[i - 1]
        curr = layer_nodes[i]
        min_x = new_xs[prev] + sizes.get(prev, default_size)[0] + NODE_GAP
        if new_xs[curr] < min_x:
            new_xs[curr] = min_x

    # Resolve overlaps right to left
    for i in range(len(layer_nodes) - 2, -1, -1):
        curr = layer_nodes[i]
        nxt = layer_nodes[i + 1]
        max_x = new_xs[nxt] - sizes.get(curr, default_size)[0] - NODE_GAP
        if new_xs[curr] > max_x:
            new_xs[curr] = max_x

    for n in layer_nodes:
        positions[n] = (new_xs[n], positions[n][1])


def _refine_x_positions(
    graph: nx.DiGraph,
    layers: list[list[str]],
    positions: dict[str, tuple[float, float]],
    sizes: dict[str, tuple[float, float]],
    default_size: tuple[float, float],
    virtual_ids: set[str],
) -> dict[str, tuple[float, float]]:
    """Refine horizontal positions using directional sweeps.

    Forward sweep (top→bottom): children align under predecessors (strong pull).
    Backward sweep (bottom→top): parents gently adjust toward successors (weak pull).
    This prevents downstream drift while still allowing upward feedback.
    """
    for _ in range(8):
        # Forward sweep: top to bottom — children position under parents
        for layer in layers:
            if layer:
                _sweep_layer(graph, layer, positions, sizes, default_size, virtual_ids, "down")

        # Backward sweep: bottom to top — parents gently adjust toward children
        for layer in reversed(layers):
            if layer:
                _sweep_layer(graph, layer, positions, sizes, default_size, virtual_ids, "up")

        # Re-center after each iteration to prevent drift
        _global_center_shift(positions, sizes, default_size)

    # Final pass: clean placement in two phases.
    # Phase 1: top-down for non-root layers (each node placed under predecessors)
    # Phase 2: position root nodes above their now-updated successors
    # Final centering: position real nodes only (skip virtual routing nodes).
    # Bottom-up: parents centered above children.
    # Top-down: children placed under parents.
    def _place_real_nodes(layer, use_predecessors):
        real_nodes = [n for n in layer if n not in virtual_ids]
        if not real_nodes:
            return
        real_nodes.sort(key=lambda n: positions[n][0])
        new_xs: dict[str, float] = {}
        for node in real_nodes:
            w = sizes.get(node, default_size)[0]
            if use_predecessors:
                ref = [p for p in graph.predecessors(node) if p in positions and p not in virtual_ids]
            else:
                ref = [s for s in graph.successors(node) if s in positions and s not in virtual_ids]
            if ref:
                centers = [
                    positions[n][0] + sizes.get(n, default_size)[0] / 2
                    for n in ref
                ]
                new_xs[node] = _median(centers) - w / 2
            else:
                new_xs[node] = positions[node][0]
        # Resolve overlaps
        for i in range(1, len(real_nodes)):
            prev = real_nodes[i - 1]
            curr = real_nodes[i]
            min_x = new_xs[prev] + sizes.get(prev, default_size)[0] + NODE_GAP
            if new_xs[curr] < min_x:
                new_xs[curr] = min_x
        for i in range(len(real_nodes) - 2, -1, -1):
            curr = real_nodes[i]
            nxt = real_nodes[i + 1]
            max_x = new_xs[nxt] - sizes.get(curr, default_size)[0] - NODE_GAP
            if new_xs[curr] > max_x:
                new_xs[curr] = max_x
        for n in real_nodes:
            positions[n] = (new_xs[n], positions[n][1])

    # Bottom-up: each parent centered above its real children
    for layer in reversed(layers):
        _place_real_nodes(layer, use_predecessors=False)

    _global_center_shift(positions, sizes, default_size)

    return positions


COMPONENT_GAP = 80  # horizontal gap between disconnected components


def _layout_single_component(
    subgraph: nx.DiGraph,
    sizes: dict[str, tuple[float, float]],
    default_size: tuple[float, float],
) -> dict[str, tuple[float, float]]:
    """Layout a single connected component using Sugiyama-style algorithm."""
    layer_assignment = _assign_layers(subgraph)
    aug_graph, layer_assignment, virtual_ids = _add_virtual_nodes(subgraph, layer_assignment)
    for vid in virtual_ids:
        sizes[vid] = (VIRTUAL_WIDTH, 0)

    layers = _order_within_layers(aug_graph, layer_assignment)

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

    positions = _refine_x_positions(aug_graph, layers, positions, sizes, default_size, virtual_ids)

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
