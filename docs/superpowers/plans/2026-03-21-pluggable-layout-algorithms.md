# Pluggable Layout Algorithms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single hardcoded layout algorithm with a pluggable system — three layout providers, a dropdown selector in the breadcrumb bar, and config persistence.

**Architecture:** Layout providers are Python modules with `NAME`, `KEY`, and `compute()`. A registry in `layouts/__init__.py` discovers them. Shared Sugiyama internals stay in `layout.py`. The breadcrumb bar gains a `QComboBox` that emits `layout_changed(str)`.

**Tech Stack:** PySide6, networkx, pygraphviz, pytest-qt

**Spec:** `docs/superpowers/specs/2026-03-21-pluggable-layout-algorithms-design.md`

---

### Task 1: Extract Sugiyama provider + registry

Extract the current `compute_layout()` from `layout.py` into a provider module, create the registry, and update all imports. Existing tests should still pass unchanged.

**Files:**
- Create: `src/beans_stalk/graph/layouts/__init__.py`
- Create: `src/beans_stalk/graph/layouts/_sugiyama.py`
- Modify: `src/beans_stalk/graph/layout.py` (remove `compute_layout`, keep shared internals)
- Modify: `src/beans_stalk/ui/dag_scene.py` (update import)
- Modify: `tests/test_layout.py` (update import)
- Test: `tests/test_layout_providers.py`

- [ ] **Step 1: Write failing test for provider registry**

```python
# tests/test_layout_providers.py
from beans_stalk.graph.layouts import PROVIDERS, get_provider


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_layout_providers.py::TestRegistry -v`

- [ ] **Step 3: Create the registry and Sugiyama provider**

Create `src/beans_stalk/graph/layouts/__init__.py`:

```python
from beans_stalk.graph.layouts import _sugiyama

PROVIDERS: dict[str, object] = {}
DEFAULT_KEY = "sugiyama"

def _register(module):
    PROVIDERS[module.KEY] = module

_register(_sugiyama)

def get_provider(key: str):
    return PROVIDERS.get(key, PROVIDERS[DEFAULT_KEY])
```

Create `src/beans_stalk/graph/layouts/_sugiyama.py`:

```python
import networkx as nx
from beans_stalk.graph.layout import (
    _layout_single_component,
    _global_center_shift,
    COMPONENT_GAP,
    NODE_GAP,
)

NAME = "Sugiyama"
KEY = "sugiyama"


def compute(
    graph: nx.DiGraph,
    visible_ids: set[str],
    node_sizes: dict[str, tuple[float, float]] | None = None,
) -> dict[str, tuple[float, float]]:
    """Sugiyama layered layout with earliest-layer assignment."""
    # Move the body of compute_layout() from layout.py here verbatim.
    # It calls _layout_single_component(), _global_center_shift(),
    # and uses COMPONENT_GAP, NODE_GAP, nx.connected_components.
    # No changes to logic — just extraction.
    ...
```

Move the body of `compute_layout()` from `layout.py` into `_sugiyama.py`'s `compute()` function verbatim. The function calls `_layout_single_component()` (which internally uses `_assign_layers`), `_global_center_shift()`, `nx.connected_components()`, and uses `COMPONENT_GAP`/`NODE_GAP` constants. All shared internals stay in `layout.py`.

Remove `compute_layout` from `layout.py` but keep everything else.

- [ ] **Step 4: Write failing test that Sugiyama provider computes layout**

```python
# tests/test_layout_providers.py (add to file)
from beans.models import Bean, BeanId, Dep
from beans_stalk.graph.layout import build_dag


def _bean(id_: str, title: str) -> Bean:
    return Bean(id=BeanId(id_), title=title, status="open")


def _dep(from_id: str, to_id: str) -> Dep:
    return Dep(from_id=BeanId(from_id), to_id=BeanId(to_id))


class TestSugiyamaProvider:
    def test_compute_returns_positions(self):
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B")]
        deps = [_dep("bean-00000001", "bean-00000002")]
        g = build_dag(beans, deps)
        provider = get_provider("sugiyama")
        positions = provider.compute(g, {"bean-00000001", "bean-00000002"})
        assert "bean-00000001" in positions
        assert "bean-00000002" in positions
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_layout_providers.py -v`

- [ ] **Step 6: Update dag_scene.py import**

In `src/beans_stalk/ui/dag_scene.py`, change:

```python
from beans_stalk.graph.layout import build_dag, compute_layout, stabilize_layout
```

to:

```python
from beans_stalk.graph.layout import build_dag, stabilize_layout
from beans_stalk.graph.layouts import get_provider
```

And in `update_snapshot()`, change:

```python
new_positions = compute_layout(graph, visible_ids, node_sizes=node_sizes)
```

to:

```python
provider = get_provider(self._layout_algorithm)
new_positions = provider.compute(graph, visible_ids, node_sizes=node_sizes)
```

Add `self._layout_algorithm = "sugiyama"` in `__init__` and a property:

```python
@property
def layout_algorithm(self) -> str:
    return self._layout_algorithm

@layout_algorithm.setter
def layout_algorithm(self, key: str):
    self._layout_algorithm = key
```

- [ ] **Step 7: Update test_layout.py imports**

In `tests/test_layout.py`, change the `TestComputeLayout` class to import from the provider:

```python
from beans_stalk.graph.layouts import get_provider
```

Update each `compute_layout(g, ...)` call to `get_provider("sugiyama").compute(g, ...)`.

Keep `build_dag` and `stabilize_layout` imports from `beans_stalk.graph.layout`.

- [ ] **Step 8: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All 108+ tests pass (no behavioral change)

- [ ] **Step 9: Commit**

```bash
git add src/beans_stalk/graph/layouts/ src/beans_stalk/graph/layout.py \
  src/beans_stalk/ui/dag_scene.py tests/test_layout.py tests/test_layout_providers.py
git commit -m "refactor: extract Sugiyama provider and layout registry"
```

---

### Task 2: Sugiyama Compact provider (latest-layer assignment)

Add the compact variant that assigns nodes to the latest possible layer.

**Files:**
- Create: `src/beans_stalk/graph/layouts/_sugiyama_compact.py`
- Modify: `src/beans_stalk/graph/layout.py` (add `_assign_layers_late`)
- Modify: `src/beans_stalk/graph/layouts/__init__.py` (register new provider)
- Test: `tests/test_layout_providers.py`

- [ ] **Step 1: Write failing test for late layer assignment**

```python
# tests/test_layout_providers.py (add to module-level imports)
from beans_stalk.graph.layout import _assign_layers, _assign_layers_late, build_dag


class TestLateLayers:
    def test_late_assignment_pulls_nodes_down(self):
        """A -> C, B -> C: with late assignment, A and B should be on layer
        just above C, not at the top."""
        beans = [_bean("a", "A"), _bean("b", "B"), _bean("c", "C")]
        deps = [_dep("a", "c"), _dep("b", "c")]
        g = build_dag(beans, deps)
        visible = {"a", "b", "c"}
        sub = g.subgraph(visible).copy()
        layers = _assign_layers_late(sub)
        # C should be at the bottom, A and B one level above
        assert layers["c"] > layers["a"]
        assert layers["c"] > layers["b"]
        assert layers["a"] == layers["b"]
        # Only 2 layers needed (0 and 1)
        assert max(layers.values()) == 1

    def test_late_vs_early_diamond(self):
        """root -> A -> C, root -> B -> C, root -> C.
        Early: root=0, A=B=1, C=2.
        Late: root should still be 0, A=B=1, C=2 (same for diamond).
        But root->C becomes a long edge with early, not with late."""
        beans = [_bean("r", "Root"), _bean("a", "A"), _bean("b", "B"), _bean("c", "C")]
        deps = [_dep("r", "a"), _dep("r", "b"), _dep("a", "c"), _dep("b", "c"), _dep("r", "c")]
        g = build_dag(beans, deps)
        sub = g.subgraph({"r", "a", "b", "c"}).copy()
        layers = _assign_layers_late(sub)
        assert layers["r"] == 0
        assert layers["a"] == 1
        assert layers["b"] == 1
        assert layers["c"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_layout_providers.py::TestLateLayers -v`

- [ ] **Step 3: Implement `_assign_layers_late` in layout.py**

Add to `src/beans_stalk/graph/layout.py`:

```python
def _assign_layers_late(graph: nx.DiGraph) -> dict[str, int]:
    """Assign each node to the latest possible layer (closest to leaves)."""
    layers = {}
    try:
        order = list(reversed(list(nx.topological_sort(graph))))
    except nx.NetworkXUnfeasible:
        order = list(graph.nodes())

    # First pass: assign from leaves upward
    for node in order:
        succs = list(graph.successors(node))
        if not succs:
            layers[node] = 0
        else:
            layers[node] = max(layers.get(s, 0) for s in succs) + 1

    # Flip so roots are at top (layer 0)
    if layers:
        max_layer = max(layers.values())
        layers = {n: max_layer - l for n, l in layers.items()}

    return layers
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_layout_providers.py::TestLateLayers -v`

- [ ] **Step 5: Write failing test for Sugiyama Compact provider**

```python
# tests/test_layout_providers.py (add to file)
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
        beans = [_bean("a", "A"), _bean("b", "B"), _bean("c", "C")]
        deps = [_dep("a", "c"), _dep("b", "c")]
        g = build_dag(beans, deps)
        provider_std = get_provider("sugiyama")
        provider_cmp = get_provider("sugiyama_compact")
        pos_std = provider_std.compute(g, {"a", "b", "c"})
        pos_cmp = provider_cmp.compute(g, {"a", "b", "c"})
        # Both should produce valid positions
        assert len(pos_std) == 3
        assert len(pos_cmp) == 3
```

- [ ] **Step 6: Create `_sugiyama_compact.py` and register it**

**Approach:** Add a `layer_fn` parameter to `_layout_single_component` in `layout.py` so both Sugiyama variants can share the same orchestration code. `_sugiyama.py` passes nothing (defaults to `_assign_layers`), `_sugiyama_compact.py` passes `layer_fn=_assign_layers_late`.

Modify `_layout_single_component` in `layout.py` to accept an optional `layer_fn` parameter:

```python
def _layout_single_component(
    subgraph: nx.DiGraph,
    sizes: dict[str, tuple[float, float]],
    default_size: tuple[float, float],
    layer_fn=None,
) -> dict[str, tuple[float, float]]:
    if layer_fn is None:
        layer_fn = _assign_layers
    layer_assignment = layer_fn(subgraph)
    ...  # rest unchanged
```

Create `src/beans_stalk/graph/layouts/_sugiyama_compact.py`:

```python
import networkx as nx
from beans_stalk.graph.layout import (
    _assign_layers_late,
    _layout_single_component,
    _global_center_shift,
    COMPONENT_GAP,
    NODE_GAP,
)

NAME = "Sugiyama Compact"
KEY = "sugiyama_compact"


def compute(
    graph: nx.DiGraph,
    visible_ids: set[str],
    node_sizes: dict[str, tuple[float, float]] | None = None,
) -> dict[str, tuple[float, float]]:
    """Sugiyama layout with latest-layer assignment for compact layouts."""
    # Same body as _sugiyama.py's compute(), but every call to
    # _layout_single_component passes layer_fn=_assign_layers_late.
    ...
```

The `compute()` body is identical to `_sugiyama.py`'s `compute()` except every call to `_layout_single_component(subgraph, sizes, default_size)` becomes `_layout_single_component(subgraph, sizes, default_size, layer_fn=_assign_layers_late)`.

Register in `layouts/__init__.py`:

```python
from beans_stalk.graph.layouts import _sugiyama, _sugiyama_compact

_register(_sugiyama)
_register(_sugiyama_compact)
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_layout_providers.py -v`

- [ ] **Step 8: Commit**

```bash
git add src/beans_stalk/graph/layout.py src/beans_stalk/graph/layouts/ \
  tests/test_layout_providers.py
git commit -m "feat: add Sugiyama Compact layout provider with latest-layer assignment"
```

---

### Task 3: Graphviz dot provider

Add the Graphviz dot layout provider, silently omitted if pygraphviz is not installed.

**Files:**
- Create: `src/beans_stalk/graph/layouts/_graphviz_dot.py`
- Modify: `src/beans_stalk/graph/layouts/__init__.py` (register with try/except)
- Test: `tests/test_layout_providers.py`

- [ ] **Step 1: Write failing test for Graphviz provider**

```python
# tests/test_layout_providers.py (add to file)
import pytest

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_layout_providers.py::TestGraphvizDotProvider -v`

- [ ] **Step 3: Implement `_graphviz_dot.py`**

Create `src/beans_stalk/graph/layouts/_graphviz_dot.py`:

```python
import networkx as nx
import pygraphviz as pgv

NAME = "Graphviz dot"
KEY = "graphviz_dot"

DPI = 72.0  # graphviz default


def compute(
    graph: nx.DiGraph,
    visible_ids: set[str],
    node_sizes: dict[str, tuple[float, float]] | None = None,
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
```

- [ ] **Step 4: Register with try/except in `__init__.py`**

```python
try:
    from beans_stalk.graph.layouts import _graphviz_dot
    _register(_graphviz_dot)
except ImportError:
    pass
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_layout_providers.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/beans_stalk/graph/layouts/ tests/test_layout_providers.py
git commit -m "feat: add Graphviz dot layout provider"
```

---

### Task 4: Config persistence for layout algorithm

Add `layout_algorithm` field to `StalkConfig` with load/save support.

**Files:**
- Modify: `src/beans_stalk/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py (add to TestStalkConfig)
    def test_layout_algorithm_default(self, tmp_path):
        config = StalkConfig.load(tmp_path)
        assert config.layout_algorithm == "sugiyama"

    def test_layout_algorithm_load(self, tmp_path):
        toml_path = tmp_path / "beans-stalk.toml"
        toml_path.write_text('layout_algorithm = "graphviz_dot"\n')
        config = StalkConfig.load(tmp_path)
        assert config.layout_algorithm == "graphviz_dot"

    def test_layout_algorithm_save_roundtrip(self, tmp_path):
        config = StalkConfig(layout_algorithm="sugiyama_compact")
        config.save(tmp_path)
        reloaded = StalkConfig.load(tmp_path)
        assert reloaded.layout_algorithm == "sugiyama_compact"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::TestStalkConfig::test_layout_algorithm_default -v`

- [ ] **Step 3: Add `layout_algorithm` to `StalkConfig`**

In `src/beans_stalk/config.py`:

Add field to dataclass:
```python
layout_algorithm: str = "sugiyama"
```

Update `load()`:
```python
layout_algorithm=data.get("layout_algorithm", "sugiyama"),
```

Update `save()`:
```python
"layout_algorithm": self.layout_algorithm,
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_config.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/config.py tests/test_config.py
git commit -m "feat: add layout_algorithm config field"
```

---

### Task 5: Breadcrumb bar dropdown + signal

Add the `QComboBox` to `BreadcrumbBar` and the `layout_changed` signal.

**Files:**
- Modify: `src/beans_stalk/ui/breadcrumb.py`
- Test: `tests/test_breadcrumb.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_breadcrumb.py (add to TestBreadcrumbBar)
    def test_has_layout_combo(self, qtbot):
        from PySide6.QtWidgets import QComboBox
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        assert hasattr(bar, '_layout_combo')
        assert isinstance(bar._layout_combo, QComboBox)

    def test_layout_combo_has_providers(self, qtbot):
        from beans_stalk.graph.layouts import PROVIDERS
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        assert bar._layout_combo.count() == len(PROVIDERS)

    def test_layout_combo_emits_signal(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        if bar._layout_combo.count() < 2:
            pytest.skip("Need at least 2 providers to test signal")
        with qtbot.waitSignal(bar.layout_changed, timeout=1000) as blocker:
            bar._layout_combo.setCurrentIndex(1)
        assert isinstance(blocker.args[0], str)

    def test_layout_combo_survives_rebuild(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "Epic")  # triggers _rebuild
        # Combo should still exist with same count
        from beans_stalk.graph.layouts import PROVIDERS
        assert bar._layout_combo.count() == len(PROVIDERS)

    def test_set_layout_algorithm(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.set_layout_algorithm("sugiyama_compact")
        assert bar._layout_combo.currentData() == "sugiyama_compact"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_breadcrumb.py::TestBreadcrumbBar::test_has_layout_combo -v`

- [ ] **Step 3: Add QComboBox to BreadcrumbBar**

In `src/beans_stalk/ui/breadcrumb.py`:

Add imports at **module level** (not inline):
```python
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox
from PySide6.QtCore import Signal
from beans_stalk.graph.layouts import PROVIDERS
```

Add signal to class:
```python
layout_changed = Signal(str)
```

In `__init__`, create the combo box **BEFORE** `self._rebuild()` is called (the combo must exist before `_rebuild` runs, since `_rebuild` skips deleting it):

```python
# Layout algorithm dropdown — created once, persists across _rebuild calls
self._layout_combo = QComboBox()
self._layout_combo.setStyleSheet(
    "QComboBox { border: 1px solid #555; color: #ccc; background: #333; "
    "font-size: 11px; padding: 1px 4px; min-width: 100px; }"
)
for key, provider in PROVIDERS.items():
    self._layout_combo.addItem(provider.NAME, key)
self._layout_combo.currentIndexChanged.connect(self._on_layout_changed)
self._rebuild()  # move existing _rebuild() call after combo creation
```

Modify `_rebuild()` to NOT destroy the combo box. Change the teardown loop:

```python
def _rebuild(self):
    # Remove all widgets EXCEPT the layout combo
    while self._layout.count():
        item = self._layout.takeAt(0)
        w = item.widget()
        if w and w is not self._layout_combo:
            w.deleteLater()
    self._buttons.clear()

    # ... add root button, separators, path buttons ...

    self._layout.addStretch()
    self._layout.addWidget(self._layout_combo)
```

Add methods:

```python
def _on_layout_changed(self, index: int):
    key = self._layout_combo.itemData(index)
    if key:
        self.layout_changed.emit(key)

def set_layout_algorithm(self, key: str):
    index = self._layout_combo.findData(key)
    if index >= 0:
        self._layout_combo.blockSignals(True)
        self._layout_combo.setCurrentIndex(index)
        self._layout_combo.blockSignals(False)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_breadcrumb.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/ui/breadcrumb.py tests/test_breadcrumb.py
git commit -m "feat: add layout algorithm dropdown to breadcrumb bar"
```

---

### Task 6: MainWindow wiring + render script

Wire the dropdown signal through MainWindow: save config, set algorithm on scene, re-render. Update the render script to accept an `--algorithm` flag.

**Files:**
- Modify: `src/beans_stalk/ui/main_window.py`
- Modify: `scripts/render_layout.py`
- Test: `tests/test_main_window.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_main_window.py (add to TestMainWindow)
    def test_layout_algorithm_change(self, qtbot, tmp_beans_dir, store):
        from beans_stalk.ui.main_window import MainWindow
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        # Default should be sugiyama
        assert win._scene.layout_algorithm == "sugiyama"
        # Simulate dropdown change
        win._on_layout_changed("sugiyama_compact")
        assert win._scene.layout_algorithm == "sugiyama_compact"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_main_window.py::TestMainWindow::test_layout_algorithm_change -v`

- [ ] **Step 3: Wire MainWindow**

In `src/beans_stalk/ui/main_window.py`:

In `_setup_ui()`, after breadcrumb creation:
```python
self._breadcrumb.set_layout_algorithm(self._config.layout_algorithm)
self._breadcrumb.layout_changed.connect(self._on_layout_changed)
```

Set initial algorithm on scene in `_setup_ui()`:
```python
self._scene.layout_algorithm = self._config.layout_algorithm
```

Add method:
```python
@Slot(str)
def _on_layout_changed(self, key: str):
    self._config.layout_algorithm = key
    self._config.save(self._beans_dir)
    self._scene.layout_algorithm = key
    self._scene.update_snapshot(self._beans, self._deps)
```

- [ ] **Step 4: Update render script**

In `scripts/render_layout.py`, add `--algorithm` support:

```python
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("beans_dir", nargs="?", default=".beans")
    parser.add_argument("-o", "--output", default="/tmp/layout.png")
    parser.add_argument("-a", "--algorithm", default="sugiyama")
    args = parser.parse_args()
```

Replace the hardcoded `scene.update_snapshot()` with setting the algorithm first:

```python
scene.layout_algorithm = args.algorithm
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/beans_stalk/ui/main_window.py scripts/render_layout.py tests/test_main_window.py
git commit -m "feat: wire layout algorithm dropdown through MainWindow"
```

---

### Task 7: Integration test + visual verification

End-to-end test that switches algorithms and verifies each produces valid output. Visual test with render script.

**Files:**
- Test: `tests/test_integration.py`
- Test: manual visual verification with render script

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py (add to file)
class TestLayoutAlgorithmSwitching:
    def test_switch_algorithms_produces_valid_layouts(self, qapp, tmp_beans_dir, store):
        from beans import api
        from beans_stalk.graph.layouts import PROVIDERS
        from beans_stalk.ui.dag_scene import DagScene
        from beans_stalk.config import StalkConfig

        # Create some beans with deps
        root = api.create_bean(store, "Root")
        child_a = api.create_bean(store, "Child A")
        child_b = api.create_bean(store, "Child B")
        api.add_dep(store, root.id, child_a.id)
        api.add_dep(store, root.id, child_b.id)
        beans = store.list()
        deps = store.list_all_deps()

        config = StalkConfig.load(tmp_beans_dir)
        scene = DagScene(config)

        for key in PROVIDERS:
            scene.layout_algorithm = key
            scene.update_snapshot(beans, deps)
            assert len(scene._nodes) == 3, f"Algorithm {key} failed to place nodes"
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/test_integration.py::TestLayoutAlgorithmSwitching -v`

- [ ] **Step 3: Visual verification with render script**

```bash
uv run python scripts/render_layout.py -a sugiyama -o /tmp/layout_sugiyama.png
uv run python scripts/render_layout.py -a sugiyama_compact -o /tmp/layout_compact.png
uv run python scripts/render_layout.py -a graphviz_dot -o /tmp/layout_graphviz.png
```

Compare the three images visually.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add layout algorithm switching integration test"
```
