import networkx as nx

from beans_stalk.graph.layout import (
    COMPONENT_GAP,
    NODE_GAP,
    _assign_layers_late,
    _global_center_shift,
    _layout_single_component,
)

NAME = "Sugiyama Compact"
KEY = "sugiyama_compact"


def compute(
    graph: nx.DiGraph,
    visible_ids: set[str],
    node_sizes: dict[str, tuple[float, float]] | None = None,
    direction: str = "TB",
) -> dict[str, tuple[float, float]]:
    """Compute node positions using a compact Sugiyama-style layered layout.

    Like the standard Sugiyama layout, but assigns nodes to the latest possible
    layer (closest to their dependents), reducing long edges.
    Disconnected components are laid out independently and packed side by side.
    """
    if not visible_ids:
        return {}

    subgraph = graph.subgraph(visible_ids).copy()
    if len(subgraph) == 0:
        return {}

    sizes = dict(node_sizes) if node_sizes else {}
    default_size = (140.0, 30.0)

    # Detect weakly connected components
    undirected = subgraph.to_undirected()
    components = list(nx.connected_components(undirected))

    if len(components) == 1:
        all_positions = _layout_single_component(subgraph, sizes, default_size, layer_fn=_assign_layers_late)
    else:
        # Separate multi-node components from singletons (isolated nodes)
        multi_components = [c for c in components if len(c) > 1]
        singletons = [c for c in components if len(c) == 1]

        # Sort multi-components: largest first for visual stability
        multi_components.sort(key=len, reverse=True)

        # Layout each multi-node component independently, then pack side by side
        all_positions: dict[str, tuple[float, float]] = {}
        component_bounds: list[tuple[float, float, float, float]] = []  # (left, top, right, bottom)
        current_x = 0.0

        for comp_nodes in multi_components:
            comp_subgraph = subgraph.subgraph(comp_nodes).copy()
            comp_sizes = {nid: sizes.get(nid, default_size) for nid in comp_nodes}
            comp_positions = _layout_single_component(
                comp_subgraph, comp_sizes, default_size, layer_fn=_assign_layers_late,
            )

            if not comp_positions:
                continue

            comp_xs = [x for x, _ in comp_positions.values()]
            comp_ys = [y for _, y in comp_positions.values()]
            comp_rights = [x + sizes.get(nid, default_size)[0] for nid, (x, _) in comp_positions.items()]
            comp_bottoms = [y + sizes.get(nid, default_size)[1] for nid, (_, y) in comp_positions.items()]
            comp_left = min(comp_xs)
            comp_right = max(comp_rights)

            shift_x = current_x - comp_left
            for nid in comp_positions:
                x, y = comp_positions[nid]
                all_positions[nid] = (x + shift_x, y)

            component_bounds.append((
                current_x,
                min(comp_ys),
                current_x + (comp_right - comp_left),
                max(comp_bottoms),
            ))
            current_x += (comp_right - comp_left) + COMPONENT_GAP

        # Tuck singletons beside the last component's bottom-right gap
        if singletons and component_bounds:
            last_left, last_top, last_right, last_bottom = component_bounds[-1]
            singleton_x = last_right + NODE_GAP
            singleton_y = last_bottom - len(singletons) * (default_size[1] + NODE_GAP)
            # Don't place above the component's midpoint
            min_y = (last_top + last_bottom) / 2
            singleton_y = max(singleton_y, min_y)

            for comp_nodes in singletons:
                nid = next(iter(comp_nodes))
                w, h = sizes.get(nid, default_size)
                all_positions[nid] = (singleton_x, singleton_y)
                singleton_y += h + NODE_GAP
        elif singletons:
            # No multi-components — just place singletons
            y = 0.0
            for comp_nodes in singletons:
                nid = next(iter(comp_nodes))
                w, h = sizes.get(nid, default_size)
                all_positions[nid] = (0.0, y)
                y += h + NODE_GAP

        # Global centering
        _global_center_shift(all_positions, sizes, default_size)

    if direction == "LR":
        all_positions = {nid: (y, x) for nid, (x, y) in all_positions.items()}

    return all_positions
