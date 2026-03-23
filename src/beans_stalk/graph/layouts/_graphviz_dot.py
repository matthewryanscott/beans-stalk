import networkx as nx
import pygraphviz as pgv

NAME = "Graphviz dot"
KEY = "graphviz_dot"

DPI = 72.0  # graphviz default


def compute(
    graph: nx.DiGraph,
    visible_ids: set[str],
    node_sizes: dict[str, tuple[float, float]] | None = None,
    direction: str = "TB",
) -> dict[str, tuple[float, float]]:
    """Compute layout by delegating to Graphviz dot engine."""
    if not visible_ids:
        return {}

    subgraph = graph.subgraph(visible_ids).copy()
    if len(subgraph) == 0:
        return {}

    sizes = dict(node_sizes) if node_sizes else {}
    default_size = (140.0, 30.0)

    ag = pgv.AGraph(directed=True)
    if direction == "LR":
        ag.graph_attr["rankdir"] = "LR"
    for node in subgraph.nodes():
        w_px, h_px = sizes.get(node, default_size)
        # Graphviz uses inches; 72 points per inch
        ag.add_node(node, width=str(w_px / DPI), height=str(h_px / DPI),
                    fixedsize="true")
    for u, v in subgraph.edges():
        ag.add_edge(u, v)

    ag.layout(prog="dot")

    positions = {}
    for node in subgraph.nodes():
        gv_node = ag.get_node(node)
        pos_str = gv_node.attr["pos"]
        x_pt, y_pt = pos_str.split(",")
        # Convert points to pixels and negate Y for Qt screen coords
        x = float(x_pt)
        y = -float(y_pt)
        # Graphviz positions are center-based; adjust to top-left
        w, h = sizes.get(node, default_size)
        positions[node] = (x - w / 2, y - h / 2)

    return positions
