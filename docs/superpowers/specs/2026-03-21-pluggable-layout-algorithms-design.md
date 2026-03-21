# Pluggable Layout Algorithms

**Date:** 2026-03-21
**Status:** Draft

## Overview

Replace the single hardcoded layout algorithm with a pluggable system. A dropdown in the toolbar lets the user switch between algorithms. The selection is persisted in config.

## Layout Provider Interface

Each algorithm is a Python module with three module-level names:

```python
NAME: str   # Display name for dropdown (e.g. "Sugiyama")
KEY: str    # Config/registry key (e.g. "sugiyama")

def compute(
    graph: nx.DiGraph,
    visible_ids: set[str],
    node_sizes: dict[str, tuple[float, float]] | None,
) -> dict[str, tuple[float, float]]
```

This is a module-level contract — no base class or Protocol needed. The registry imports each module and accesses `.NAME`, `.KEY`, `.compute` directly. Simple, no ceremony.

Same contract as the current `compute_layout()`. Input: full DAG, set of visible node IDs, optional size hints. Output: `{node_id: (x, y)}` positions in screen coordinates (Y increases downward).

## Provider Registry

`src/beans_stalk/graph/layouts/__init__.py` maintains a `PROVIDERS: dict[str, module]` mapping keys to provider modules. A `get_provider(key)` function returns the module or falls back to the default.

Providers are registered explicitly (not via plugin discovery) — just import and add to the dict. If a provider's import fails (e.g. pygraphviz not installed), it is silently omitted.

## File Structure

```
src/beans_stalk/graph/
    layouts/
        __init__.py          # Registry: PROVIDERS, get_provider()
        _sugiyama.py         # Current algorithm (extracted from layout.py)
        _sugiyama_compact.py # Compact variant with latest-layer assignment
        _graphviz_dot.py     # Pygraphviz dot delegation
    layout.py                # Shared utilities: build_dag(), stabilize_layout()
```

`layout.py` retains `build_dag()`, `stabilize_layout()`, and all shared Sugiyama internals (`_assign_layers`, `_assign_layers_late`, `_add_virtual_nodes`, `_order_within_layers`, `_refine_x_positions`, `_layout_single_component`, component-packing logic, spacing constants). Both Sugiyama providers import these shared functions from `layout.py`. Only the top-level `compute()` orchestration and the choice of layer-assignment function differ between variants.

## Algorithms

### Sugiyama (current)

Key: `sugiyama`. The existing custom Sugiyama implementation — earliest-layer assignment, barycenter ordering with adjacent exchange, directional x-refinement sweeps, component separation, bottom-up final centering.

Extracted from `layout.py` into `_sugiyama.py` with no behavioral changes.

### Sugiyama Compact

Key: `sugiyama_compact`. Same as Sugiyama but with **latest possible layer** assignment instead of earliest. Nodes are placed as late (deep) as possible while still satisfying dependency ordering. This pulls nodes down to just above where they're needed, reducing long edges and crossings.

**Latest-layer algorithm:**
1. Topological sort in reverse
2. Leaf nodes (no successors) get the maximum layer
3. Each node gets `min(successor_layers) - 1`, working backwards
4. Shift all layers so minimum = 0

Shares all other code with `_sugiyama.py` — ordering, virtual nodes, x-refinement, component separation. Only the layer assignment function differs.

### Graphviz Dot

Key: `graphviz_dot`. Delegates to pygraphviz's `dot` layout engine. Converts the visible subgraph to an AGraph, sets node width/height from `node_sizes` (in inches at 72 DPI), runs `layout(prog='dot')`, parses positions back to pixel coordinates with Y-axis negation for Qt screen coords.

Hidden from the dropdown if `import pygraphviz` fails at startup.

## UI: Algorithm Dropdown

A `QComboBox` added to the right side of the `BreadcrumbBar`'s horizontal layout, after the stretch that pushes breadcrumb buttons left. The combo box is NOT managed by `_rebuild()` — it is created once in `__init__` and persists across breadcrumb navigation. `_rebuild()` only tears down and recreates the breadcrumb buttons/separators, leaving the combo box untouched.

Populated from the registry at startup (only showing providers that loaded successfully).

### Signal Flow

1. User selects algorithm in dropdown
2. `BreadcrumbBar` emits `layout_changed(str)` signal with the provider key
3. `MainWindow` saves key to `StalkConfig`, sets it on `DagScene`
4. `DagScene.update_snapshot()` uses the configured provider

### Config

`StalkConfig` gains a new field:

```python
layout_algorithm: str = "sugiyama"
```

Persisted in `beans-stalk.toml` under `layout_algorithm`. Both `load()` and `save()` must be updated to handle this field. If the config contains an unknown algorithm key, `get_provider()` falls back to `"sugiyama"` and the dropdown shows the fallback selection.

### DagScene Changes

- New property: `layout_provider` (set via key string)
- `update_snapshot()` calls `provider.compute(...)` instead of the hardcoded `compute_layout()`
- `stabilize_layout()` remains in the shared `layout.py` and is called by `DagScene` after the provider returns positions

## File Changes

### New Files

- `src/beans_stalk/graph/layouts/__init__.py` — provider registry
- `src/beans_stalk/graph/layouts/_sugiyama.py` — current algorithm extracted
- `src/beans_stalk/graph/layouts/_sugiyama_compact.py` — compact variant
- `src/beans_stalk/graph/layouts/_graphviz_dot.py` — graphviz delegation
- `tests/test_layout_providers.py` — tests for registry, each provider's compute(), and compact layer assignment

### Modified Files

- `src/beans_stalk/graph/layout.py` — keep `build_dag()`, `stabilize_layout()`, and shared Sugiyama internals; remove top-level `compute_layout()`
- `src/beans_stalk/ui/breadcrumb.py` — add `QComboBox` and `layout_changed` signal
- `src/beans_stalk/ui/dag_scene.py` — use provider from registry instead of hardcoded import
- `src/beans_stalk/ui/main_window.py` — wire dropdown signal, save config, set provider on scene
- `src/beans_stalk/config.py` — add `layout_algorithm` field
- `scripts/render_layout.py` — accept optional `--algorithm` flag for visual testing
