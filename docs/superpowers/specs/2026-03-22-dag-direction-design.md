# DAG Direction: Top-Down / Left-Right

Add a direction toggle to switch the DAG between top-down and left-right layout.

## Breadcrumb Bar

New combobox to the left of the existing layout algorithm combobox. Two options: "Top-Down" and "Left-Right". Styled identically to the layout combobox. Emits `direction_changed(str)` signal with values `"TB"` or `"LR"`.

## Config

New `layout_direction` field in `StalkConfig`, defaulting to `"TB"`. Persisted to `.beans/beans-stalk.toml`. Restored on launch and applied to the breadcrumb combobox.

## Layout Providers

Each provider's `compute()` gets an optional `direction="TB"` parameter.

- **Graphviz dot:** Sets `rankdir=LR` on the AGraph when direction is `"LR"`. No other changes needed — graphviz handles LR natively.
- **Sugiyama / Sugiyama compact:** After computing positions in TB mode, swap x/y coordinates when direction is `"LR"`. This is a simple post-processing step since these are custom layout implementations.

## Edge Routing

`DepEdge.update_path` gets a `direction="TB"` parameter.

- **TB mode (current):** Edges exit the bottom of the source node and enter the top of the target. Bezier control points offset vertically.
- **LR mode:** Edges exit the right side of the source and enter the left side of the target. Bezier control points offset horizontally.

Port fractions in LR mode distribute vertically (top-to-bottom of node) rather than horizontally.

## Port Computation in DagScene

The `_aim_frac` and `_find_obstacle_side` logic swaps its x/y reasoning when direction is LR:
- `_aim_frac`: angle computed from vertical offset instead of horizontal.
- `_find_obstacle_side`: checks horizontal overlap instead of vertical overlap.
- Port sorting: by Y position instead of X position.

## Signal Flow

`BreadcrumbBar.direction_changed` -> `MainWindow._on_direction_changed` -> updates `config.layout_direction`, saves config, stores direction on scene, re-renders snapshot.

`DagScene` stores `self._direction` and passes it to providers and edge routing.

## Files Changed

- `src/beans_stalk/config.py` — add `layout_direction` field
- `src/beans_stalk/ui/breadcrumb.py` — add direction combobox + `direction_changed` signal
- `src/beans_stalk/graph/layouts/_graphviz_dot.py` — `rankdir` parameter
- `src/beans_stalk/graph/layouts/_sugiyama.py` — x/y swap post-processing
- `src/beans_stalk/graph/layouts/_sugiyama_compact.py` — x/y swap post-processing
- `src/beans_stalk/ui/dag_scene.py` — pass direction to providers and edge routing
- `src/beans_stalk/ui/dep_edge.py` — LR bezier path variant
- `src/beans_stalk/ui/main_window.py` — wire `direction_changed` signal, persist config
