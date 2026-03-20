import networkx as nx
from beans.models import Bean, Dep

# Spacing constants (pixels)
LAYER_GAP = 60  # vertical space between layers
NODE_GAP = 20   # horizontal space between nodes in a layer


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
    # Process in topological order — if cyclic, fall back to arbitrary order
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


def _order_within_layers(
    graph: nx.DiGraph,
    layer_assignment: dict[str, int],
) -> list[list[str]]:
    """Order nodes within each layer to reduce edge crossings (barycenter heuristic)."""
    max_layer = max(layer_assignment.values()) if layer_assignment else 0
    layers: list[list[str]] = [[] for _ in range(max_layer + 1)]
    for node, layer in layer_assignment.items():
        layers[layer].append(node)

    # Initial order: sort by node id for determinism
    for layer in layers:
        layer.sort()

    # Barycenter heuristic: sweep down then up a few times
    for _ in range(4):
        # Forward sweep (top to bottom)
        for i in range(1, len(layers)):
            _sort_by_barycenter(graph, layers[i], layers[i - 1], predecessors=True)
        # Backward sweep (bottom to top)
        for i in range(len(layers) - 2, -1, -1):
            _sort_by_barycenter(graph, layers[i], layers[i + 1], predecessors=False)

    return layers


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


def compute_layout(
    graph: nx.DiGraph,
    visible_ids: set[str],
    node_sizes: dict[str, tuple[float, float]] | None = None,
) -> dict[str, tuple[float, float]]:
    """Compute node positions using a custom Sugiyama-style layered layout.

    Returns positions as {node_id: (x, y)} where (x, y) is the top-left corner
    of the node in screen coordinates (Y increases downward).
    """
    if not visible_ids:
        return {}

    subgraph = graph.subgraph(visible_ids).copy()
    if len(subgraph) == 0:
        return {}

    sizes = node_sizes or {}
    default_size = (140.0, 30.0)

    # Step 1: Assign layers
    layer_assignment = _assign_layers(subgraph)

    # Step 2: Order within layers to reduce crossings
    layers = _order_within_layers(subgraph, layer_assignment)

    # Step 3: Compute coordinates using actual node sizes
    positions = {}
    y = 0.0

    for layer in layers:
        # Compute layer height (tallest node in this layer)
        layer_height = max(sizes.get(n, default_size)[1] for n in layer)

        # Compute total width of this layer
        total_width = sum(sizes.get(n, default_size)[0] for n in layer)
        total_width += NODE_GAP * (len(layer) - 1) if len(layer) > 1 else 0

        # Center the layer horizontally (x=0 is center)
        x = -total_width / 2

        for node in layer:
            w, h = sizes.get(node, default_size)
            # Center node vertically within the layer
            node_y = y + (layer_height - h) / 2
            positions[node] = (x, node_y)
            x += w + NODE_GAP

        y += layer_height + LAYER_GAP

    return positions


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
