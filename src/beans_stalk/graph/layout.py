import networkx as nx
from beans.models import Bean, Dep


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


def compute_layout(
    graph: nx.DiGraph, visible_ids: set[str]
) -> dict[str, tuple[float, float]]:
    if not visible_ids:
        return {}
    subgraph = graph.subgraph(visible_ids).copy()
    if len(subgraph) == 0:
        return {}
    pos = nx.drawing.nx_agraph.graphviz_layout(subgraph, prog="dot")
    return {node_id: (float(x), float(y)) for node_id, (x, y) in pos.items()}


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
