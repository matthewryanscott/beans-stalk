# DAG Direction Toggle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a direction toggle (Top-Down / Left-Right) to the breadcrumb bar that pivots the entire DAG layout, edges, and port computation.

**Architecture:** A `layout_direction` field flows from config through DagScene to layout providers and edge routing. Graphviz uses native `rankdir=LR`. Sugiyama providers swap x/y in post-processing. Edge routing and port computation swap axes based on direction.

**Tech Stack:** PySide6, pygraphviz, networkx, pytest + pytest-qt

**Spec:** `docs/superpowers/specs/2026-03-22-dag-direction-design.md`

---

### Task 1: Config — add layout_direction

**Files:**
- Modify: `src/beans_stalk/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

In `tests/test_config.py`, add:

```python
def test_layout_direction_default(self, tmp_path):
    config = StalkConfig()
    assert config.layout_direction == "TB"

def test_layout_direction_persists(self, tmp_path):
    beans_dir = tmp_path / ".beans"
    beans_dir.mkdir()
    config = StalkConfig(layout_direction="LR")
    config.save(beans_dir)
    loaded = StalkConfig.load(beans_dir)
    assert loaded.layout_direction == "LR"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v -k "layout_direction"`
Expected: FAIL

- [ ] **Step 3: Implement**

In `config.py`, add field to `StalkConfig`:

```python
layout_direction: str = "TB"
```

In `load()`, add to the constructor call:

```python
layout_direction=data.get("layout_direction", "TB"),
```

In `save()`, add to the data dict:

```python
"layout_direction": self.layout_direction,
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/config.py tests/test_config.py
git commit -m "feat: add layout_direction to StalkConfig"
```

---

### Task 2: Layout providers — direction parameter

**Files:**
- Modify: `src/beans_stalk/graph/layouts/_graphviz_dot.py`
- Modify: `src/beans_stalk/graph/layouts/_sugiyama.py`
- Modify: `src/beans_stalk/graph/layouts/_sugiyama_compact.py`
- Test: `tests/test_layout_providers.py`

- [ ] **Step 1: Write failing tests**

In `tests/test_layout_providers.py`, add:

```python
def test_graphviz_dot_lr_direction(self):
    """LR direction should produce horizontally-arranged positions."""
    G = nx.DiGraph()
    G.add_edge("a", "b")
    positions = _graphviz_dot.compute(G, {"a", "b"}, direction="LR")
    # In LR mode, a should be to the left of b (lower x)
    assert positions["a"][0] < positions["b"][0]
    # Y positions should be similar (same rank)
    assert abs(positions["a"][1] - positions["b"][1]) < 50

def test_sugiyama_lr_direction(self):
    """LR direction should swap axes compared to TB."""
    G = nx.DiGraph()
    G.add_edge("a", "b")
    tb = _sugiyama.compute(G, {"a", "b"}, direction="TB")
    lr = _sugiyama.compute(G, {"a", "b"}, direction="LR")
    # In TB: a is above b (lower y). In LR: a is left of b (lower x).
    assert tb["a"][1] < tb["b"][1]  # TB: a above b
    assert lr["a"][0] < lr["b"][0]  # LR: a left of b
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_layout_providers.py -v -k "lr_direction"`
Expected: FAIL

- [ ] **Step 3: Implement graphviz_dot direction**

In `_graphviz_dot.py`, update `compute` signature and add `rankdir`:

```python
def compute(
    graph: nx.DiGraph,
    visible_ids: set[str],
    node_sizes: dict[str, tuple[float, float]] | None = None,
    direction: str = "TB",
) -> dict[str, tuple[float, float]]:
```

After `ag = pgv.AGraph(directed=True)`, add:

```python
    if direction == "LR":
        ag.graph_attr["rankdir"] = "LR"
```

- [ ] **Step 4: Implement sugiyama direction**

In `_sugiyama.py`, update `compute` signature:

```python
def compute(
    graph: nx.DiGraph,
    visible_ids: set[str],
    node_sizes: dict[str, tuple[float, float]] | None = None,
    direction: str = "TB",
) -> dict[str, tuple[float, float]]:
```

Add a helper at the end of the function to apply the swap. **Important:** the single-component path returns early on line 38, so the swap must be applied to BOTH code paths. Restructure the function to collect positions into `all_positions` in both branches, then apply the swap once at the end:

Replace the early return `return _layout_single_component(...)` with:

```python
    if len(components) == 1:
        all_positions = _layout_single_component(subgraph, sizes, default_size)
    else:
        # ... existing multi-component code stays the same ...
```

Then at the very end of the function, before returning:

```python
    if direction == "LR":
        all_positions = {nid: (y, x) for nid, (x, y) in all_positions.items()}

    return all_positions
```

Do the same restructuring for `_sugiyama_compact.py` (which has the same early-return pattern with `layer_fn=_assign_layers_late`).

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_layout_providers.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/beans_stalk/graph/layouts/_graphviz_dot.py src/beans_stalk/graph/layouts/_sugiyama.py src/beans_stalk/graph/layouts/_sugiyama_compact.py tests/test_layout_providers.py
git commit -m "feat: add direction parameter to layout providers"
```

---

### Task 3: DepEdge — LR bezier path

**Files:**
- Modify: `src/beans_stalk/ui/dep_edge.py`
- Test: `tests/test_dep_edge.py`

- [ ] **Step 1: Write failing test**

In `tests/test_dep_edge.py`, add:

```python
def test_lr_path_exits_right_enters_left(self, qapp):
    edge = DepEdge("a", "b")
    edge.update_path(
        QPointF(0, 0), (160, 40),
        QPointF(300, 0), (160, 40),
        direction="LR",
    )
    path = edge.path()
    start = path.elementAt(0)
    end = path.elementAt(path.elementCount() - 1)
    # Start should be at right side of source (x ~ 160)
    assert start.x > 100
    # End should be at left side of target (x ~ 300)
    assert end.x < 350
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dep_edge.py -v -k "lr_path"`
Expected: FAIL

- [ ] **Step 3: Implement LR path**

In `dep_edge.py`, add `direction="TB"` parameter to `update_path` and add the LR branch:

```python
def update_path(self, from_pos: QPointF, from_size: tuple[float, float],
                to_pos: QPointF, to_size: tuple[float, float],
                from_port_frac: float = 0.5, to_port_frac: float = 0.5,
                direction: str = "TB"):
    from_w, from_h = from_size
    to_w, to_h = to_size

    if direction == "LR":
        # Edges exit right side, enter left side
        # port_frac maps top-to-bottom of node
        from_margin = min(8, from_h * 0.1)
        to_margin = min(8, to_h * 0.1)
        from_y = from_pos.y() + from_margin + (from_h - 2 * from_margin) * from_port_frac
        to_y = to_pos.y() + to_margin + (to_h - 2 * to_margin) * to_port_frac
        start = QPointF(from_pos.x() + from_w, from_y)
        end = QPointF(to_pos.x(), to_y)
        dx = abs(end.x() - start.x()) / 2
        ctrl1 = QPointF(start.x() + dx, start.y())
        ctrl2 = QPointF(end.x() - dx, end.y())
    else:
        # TB: edges exit bottom, enter top
        from_margin = min(8, from_w * 0.1)
        to_margin = min(8, to_w * 0.1)
        from_x = from_pos.x() + from_margin + (from_w - 2 * from_margin) * from_port_frac
        to_x = to_pos.x() + to_margin + (to_w - 2 * to_margin) * to_port_frac
        start = QPointF(from_x, from_pos.y() + from_h)
        end = QPointF(to_x, to_pos.y())
        dx_val = abs(end.y() - start.y()) / 2
        ctrl1 = QPointF(start.x(), start.y() + dx_val)
        ctrl2 = QPointF(end.x(), end.y() - dx_val)

    path = QPainterPath(start)
    path.cubicTo(ctrl1, ctrl2, end)
    self.setPath(path)
```

Note: the existing `dy` variable is renamed to `dx_val` to avoid confusion; keep the variable name `dy` if you prefer, just preserve the existing TB logic exactly.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_dep_edge.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/ui/dep_edge.py tests/test_dep_edge.py
git commit -m "feat: add LR bezier path to DepEdge"
```

---

### Task 4: DagScene — direction-aware layout and edge routing

**Files:**
- Modify: `src/beans_stalk/ui/dag_scene.py`

- [ ] **Step 1: Add direction property to DagScene**

In `__init__`, after `self._layout_algorithm = "sugiyama"`:

```python
self._direction = "TB"
```

Add property:

```python
@property
def direction(self) -> str:
    return self._direction

@direction.setter
def direction(self, value: str):
    self._direction = value
```

- [ ] **Step 2: Pass direction to layout provider**

In `update_snapshot`, change the provider call:

```python
new_positions = provider.compute(graph, visible_ids, node_sizes=node_sizes, direction=self._direction)
```

- [ ] **Step 3: Update port computation for direction**

In `update_snapshot`, update `_center_x`, `_center_y`, `_aim_frac`, port sorting, and `_find_obstacle_side` to swap axes when `self._direction == "LR"`:

For `_aim_frac`: swap dx/dy meaning:

```python
def _aim_frac(anchor_id, peer_id):
    anchor_cx = _center_x(anchor_id)
    peer_cx = _center_x(peer_id)
    if self._direction == "LR":
        # In LR, ports distribute vertically; aim based on Y offset
        dx = _center_y(peer_id) - _center_y(anchor_id)
        dy = abs(peer_cx - anchor_cx)
    else:
        dx = peer_cx - anchor_cx
        dy = abs(_center_y(peer_id) - _center_y(anchor_id))
    if dy < 1:
        dy = 1
    angle = math.atan2(dx, dy)
    raw = 0.5 + angle / math.pi
    return max(0.0, min(1.0, raw))
```

For port sorting, swap to sort by Y in LR mode:

```python
sort_key = _center_y if self._direction == "LR" else _center_x
for src, targets in outgoing.items():
    targets.sort(key=sort_key)
for tgt, sources in incoming.items():
    sources.sort(key=sort_key)
```

For `_find_obstacle_side`, swap the axis checks. In LR mode: check if obstacle's Y range overlaps the edge's Y band (instead of X range overlapping the bezier midpoint):

```python
def _find_obstacle_side(from_id, to_id, from_frac, to_frac):
    fx, fy = new_positions[from_id]
    fw, fh = node_sizes.get(from_id, (140, 40))
    tx, ty = new_positions[to_id]
    tw, th = node_sizes.get(to_id, (140, 40))

    if self._direction == "LR":
        from_margin = min(8, fh * 0.1)
        to_margin = min(8, th * 0.1)
        start_y = fy + from_margin + (fh - 2 * from_margin) * from_frac
        end_y = ty + to_margin + (th - 2 * to_margin) * to_frac
        mid_y = (start_y + end_y) / 2
        min_x = min(fx + fw, tx) + 5
        max_x = max(fx + fw, tx) - 5
        if min_x >= max_x:
            return None
        for nid, nx_, ny_, nw, nh in node_rects:
            if nid == from_id or nid == to_id:
                continue
            if nx_ + nw < min_x or nx_ > max_x:
                continue
            margin = 15
            if ny_ - margin <= mid_y <= ny_ + nh + margin:
                node_cy = ny_ + nh / 2
                return "left" if mid_y <= node_cy else "right"
        return None
    else:
        # existing TB logic unchanged
        ...
```

- [ ] **Step 4: Pass direction to edge update_path**

In the edge update loop, pass direction:

```python
edge.update_path(
    ...,
    from_port_frac=from_frac,
    to_port_frac=to_frac,
    direction=self._direction,
)
```

- [ ] **Step 5: Write smoke test for DagScene direction**

In `tests/test_dag_scene.py`, add:

```python
def test_lr_direction_produces_horizontal_layout(self, qapp, tmp_beans_dir, store):
    from beans import api as beans_api
    a = beans_api.create_bean(store, "A")
    b = beans_api.create_bean(store, "B")
    beans_api.add_dep(store, a.id, b.id)
    store.close()
    stalk_store = StalkStore(tmp_beans_dir / "beans.db")
    config = StalkConfig()
    scene = DagScene(config, store=stalk_store)
    scene.direction = "LR"
    beans, deps = stalk_store.load_snapshot()
    scene.update_snapshot(beans, deps)
    # In LR mode, A should be to the left of B
    assert scene._nodes[a.id].x() < scene._nodes[b.id].x()
    stalk_store.close()
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add src/beans_stalk/ui/dag_scene.py tests/test_dag_scene.py
git commit -m "feat: direction-aware layout and edge routing in DagScene"
```

---

### Task 5: BreadcrumbBar — direction combobox

**Files:**
- Modify: `src/beans_stalk/ui/breadcrumb.py`
- Test: `tests/test_breadcrumb.py`

- [ ] **Step 1: Write failing test**

In `tests/test_breadcrumb.py`, add:

```python
def test_direction_changed_signal(self, qtbot):
    bar = BreadcrumbBar()
    qtbot.addWidget(bar)
    signals = []
    bar.direction_changed.connect(lambda d: signals.append(d))
    bar._direction_combo.setCurrentIndex(1)  # "Left-Right"
    assert signals == ["LR"]

def test_set_direction(self, qtbot):
    bar = BreadcrumbBar()
    qtbot.addWidget(bar)
    bar.set_direction("LR")
    assert bar._direction_combo.currentData() == "LR"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_breadcrumb.py -v -k "direction"`
Expected: FAIL

- [ ] **Step 3: Implement**

In `breadcrumb.py`, add signal:

```python
direction_changed = Signal(str)
```

In `__init__`, before the `_layout_combo` creation, add:

```python
self._direction_combo = QComboBox()
self._direction_combo.setStyleSheet(
    "QComboBox { border: 1px solid #555; color: #ccc; background: #333; "
    "font-size: 11px; padding: 1px 4px; min-width: 80px; }"
)
self._direction_combo.addItem("Top-Down", "TB")
self._direction_combo.addItem("Left-Right", "LR")
self._direction_combo.currentIndexChanged.connect(self._on_direction_changed)
```

In `_rebuild`, add the direction combo before the layout combo:

```python
self._layout.addWidget(self._direction_combo)
self._layout.addWidget(self._layout_combo)
```

(Remove the existing `self._layout.addWidget(self._layout_combo)` line that's already there.)

Add handler:

```python
def _on_direction_changed(self, index: int):
    key = self._direction_combo.itemData(index)
    if key:
        self.direction_changed.emit(key)

def set_direction(self, key: str):
    index = self._direction_combo.findData(key)
    if index >= 0:
        self._direction_combo.blockSignals(True)
        self._direction_combo.setCurrentIndex(index)
        self._direction_combo.blockSignals(False)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_breadcrumb.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/ui/breadcrumb.py tests/test_breadcrumb.py
git commit -m "feat: add direction combobox to BreadcrumbBar"
```

---

### Task 6: MainWindow — wire direction signal and persist

**Files:**
- Modify: `src/beans_stalk/ui/main_window.py`

- [ ] **Step 1: Connect signal and set initial state**

In `_setup_ui`, after `self._breadcrumb.layout_changed.connect(...)`:

```python
self._breadcrumb.set_direction(self._config.layout_direction)
self._breadcrumb.direction_changed.connect(self._on_direction_changed)
```

After `self._scene.layout_algorithm = self._config.layout_algorithm`:

```python
self._scene.direction = self._config.layout_direction
```

- [ ] **Step 2: Add handler**

```python
@Slot(str)
def _on_direction_changed(self, key: str):
    self._config.layout_direction = key
    self._config.save(self._beans_dir)
    self._scene.direction = key
    self._scene.update_snapshot(self._beans, self._deps)
    self._view.update_scene_rect()
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add src/beans_stalk/ui/main_window.py
git commit -m "feat: wire direction toggle to config and scene"
```
