# Delete Bean, Ready Highlighting, Child Count Badge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add delete-bean functionality, visually highlight ready beans with a blue border, and show a child-count badge on parent nodes.

**Architecture:** Three independent features layered onto the existing signal-based architecture. StalkStore gets two new methods (`delete_bean`, `ready_bean_ids`). BeanNode gets two new visual properties (`ready`, `child_count`). DagScene computes ready/child-count state during `update_snapshot`. DagView adds delete triggers (key + context menu). MainWindow wires delete with a confirmation dialog.

**Tech Stack:** PySide6, beans library (api module), pytest + pytest-qt

**Spec:** `docs/superpowers/specs/2026-03-22-delete-ready-childcount-design.md`

---

### Task 1: StalkStore — delete_bean and ready_bean_ids

**Files:**
- Modify: `src/beans_stalk/data/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write failing test for delete_bean**

In `tests/test_store.py`, add:

```python
def test_delete_bean(self, tmp_beans_dir):
    ss = StalkStore(tmp_beans_dir / "beans.db")
    bean = ss.create_bean("To delete")
    ss.delete_bean(bean.id)
    beans, _ = ss.load_snapshot()
    assert len(beans) == 0
    ss.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store.py::TestStalkStore::test_delete_bean -v`
Expected: FAIL — `AttributeError: 'StalkStore' object has no attribute 'delete_bean'`

- [ ] **Step 3: Implement delete_bean**

In `src/beans_stalk/data/store.py`, add method to `StalkStore`:

```python
def delete_bean(self, bean_id: str) -> Bean:
    return api.delete_bean(self.store, bean_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_store.py::TestStalkStore::test_delete_bean -v`
Expected: PASS

- [ ] **Step 5: Write failing test for ready_bean_ids**

In `tests/test_store.py`, add:

```python
def test_ready_bean_ids(self, tmp_beans_dir):
    ss = StalkStore(tmp_beans_dir / "beans.db")
    a = ss.create_bean("Ready A")
    b = ss.create_bean("Ready B")
    blocker = ss.create_bean("Blocker")
    ss.add_dep(blocker.id, b.id)  # blocker blocks b
    ready = ss.ready_bean_ids()
    assert a.id in ready
    assert b.id not in ready  # blocked
    assert blocker.id in ready
    ss.close()
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_store.py::TestStalkStore::test_ready_bean_ids -v`
Expected: FAIL — `AttributeError: 'StalkStore' object has no attribute 'ready_bean_ids'`

- [ ] **Step 7: Implement ready_bean_ids**

In `src/beans_stalk/data/store.py`, add method to `StalkStore`:

```python
def ready_bean_ids(self) -> set[str]:
    return {b.id for b in api.ready_beans(self.store)}
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_store.py::TestStalkStore::test_ready_bean_ids -v`
Expected: PASS

- [ ] **Step 9: Run full store tests and commit**

Run: `uv run pytest tests/test_store.py -v`
Expected: all pass

```bash
git add src/beans_stalk/data/store.py tests/test_store.py
git commit -m "feat: add delete_bean and ready_bean_ids to StalkStore"
```

---

### Task 2: BeanNode — ready property and blue border

**Files:**
- Modify: `src/beans_stalk/ui/bean_node.py`
- Test: `tests/test_bean_node.py`

- [ ] **Step 1: Write failing test for ready property**

In `tests/test_bean_node.py`, add:

```python
def test_ready_default_false(self, qapp):
    bean = Bean(id="b1", title="Test", status="open", type="task", priority=2, body="")
    node = BeanNode(bean, "#336699")
    assert node.ready is False

def test_ready_setter(self, qapp):
    bean = Bean(id="b1", title="Test", status="open", type="task", priority=2, body="")
    node = BeanNode(bean, "#336699")
    node.ready = True
    assert node.ready is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bean_node.py::TestBeanNode::test_ready_default_false tests/test_bean_node.py::TestBeanNode::test_ready_setter -v`
Expected: FAIL — `AttributeError: 'BeanNode' object has no attribute 'ready'`

- [ ] **Step 3: Implement ready property**

In `src/beans_stalk/ui/bean_node.py`, add to `__init__` after `self._highlighted = False`:

```python
self._ready = False
```

Add property after the `highlighted` property:

```python
@property
def ready(self) -> bool:
    return self._ready

@ready.setter
def ready(self, value: bool):
    self._ready = value
    self.update()
```

- [ ] **Step 4: Implement blue border in paint()**

In `bean_node.py`, add a constant at module level:

```python
READY_BORDER_COLOR = "#4A9EFF"
```

In `paint()`, replace the border drawing block (lines 204-214) with:

```python
border_width = 2.0
if self._pulsing:
    border_width = 2.0 + 2.0 * self._pulse_phase

if self._ghost:
    fill_color.setAlphaF(0.2)
    painter.setPen(QPen(fill_color.darker(130), border_width, Qt.PenStyle.DashLine))
elif self._ready and not self._muted:
    painter.setPen(QPen(QColor(READY_BORDER_COLOR), max(border_width, 2.5)))
else:
    painter.setPen(QPen(fill_color.darker(130), border_width))
painter.setBrush(fill_color)
painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), CORNER_RADIUS, CORNER_RADIUS)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_bean_node.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/beans_stalk/ui/bean_node.py tests/test_bean_node.py
git commit -m "feat: add ready property with blue border to BeanNode"
```

---

### Task 3: BeanNode — child_count property and badge

**Files:**
- Modify: `src/beans_stalk/ui/bean_node.py`
- Test: `tests/test_bean_node.py`

- [ ] **Step 1: Write failing test for child_count property**

In `tests/test_bean_node.py`, add:

```python
def test_child_count_default_zero(self, qapp):
    bean = Bean(id="b1", title="Test", status="open", type="task", priority=2, body="")
    node = BeanNode(bean, "#336699")
    assert node.child_count == 0

def test_child_count_setter(self, qapp):
    bean = Bean(id="b1", title="Test", status="open", type="task", priority=2, body="")
    node = BeanNode(bean, "#336699")
    node.child_count = 5
    assert node.child_count == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bean_node.py::TestBeanNode::test_child_count_default_zero tests/test_bean_node.py::TestBeanNode::test_child_count_setter -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: Implement child_count property**

In `src/beans_stalk/ui/bean_node.py`, add to `__init__` after `self._ready = False`:

```python
self._child_count = 0
```

Add property:

```python
@property
def child_count(self) -> int:
    return self._child_count

@child_count.setter
def child_count(self, value: int):
    self._child_count = value
    self.update()
```

- [ ] **Step 4: Implement badge in paint()**

In `paint()`, after the priority indicator block (after the `painter.drawEllipse` for priority), add:

```python
# Child count badge (top-right corner)
if self._child_count > 0 and not self._ghost and not self._muted:
    badge_font = QFont("system-ui", 8)
    badge_fm = QFontMetrics(badge_font)
    badge_text = str(self._child_count)
    text_width = badge_fm.horizontalAdvance(badge_text)
    badge_w = max(text_width + 8, badge_fm.height() + 4)
    badge_h = badge_fm.height() + 2
    badge_x = w - badge_w - 4
    badge_y = 4
    badge_color = QColor(255, 255, 255, 64)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(badge_color)
    painter.drawRoundedRect(QRectF(badge_x, badge_y, badge_w, badge_h), 3, 3)
    painter.setPen(QColor(255, 255, 255, 200))
    painter.setFont(badge_font)
    painter.drawText(
        QRectF(badge_x, badge_y, badge_w, badge_h),
        Qt.AlignmentFlag.AlignCenter,
        badge_text,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_bean_node.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/beans_stalk/ui/bean_node.py tests/test_bean_node.py
git commit -m "feat: add child count badge to BeanNode"
```

---

### Task 4: DagScene — wire ready state and child counts into update_snapshot

**Files:**
- Modify: `src/beans_stalk/ui/dag_scene.py`
- Test: `tests/test_dag_scene.py`

- [ ] **Step 1: Add store reference to DagScene**

`DagScene.update_snapshot` currently receives `(beans, deps)` but needs access to the store for `ready_bean_ids()`. Modify `DagScene.__init__` to accept an optional `store` parameter:

In `dag_scene.py`, update `__init__` signature:

```python
def __init__(self, config: StalkConfig, store=None, parent=None):
    super().__init__(parent)
    self._config = config
    self._store = store
```

In `main_window.py`, update `_setup_ui` where DagScene is created:

```python
self._scene = DagScene(self._config, store=self._store)
```

- [ ] **Step 2: Add ready and child_count computation to update_snapshot**

In `dag_scene.py`, inside `update_snapshot`, **before** the node update loop (`for bean_id, (bean, muted) in visible_beans.items():`), add:

```python
# Compute ready state
ready_ids: set[str] = set()
if self._store is not None:
    try:
        ready_ids = self._store.ready_bean_ids()
    except Exception:
        pass  # store may be closed during shutdown

# Compute child counts across all beans
child_counts: dict[str, int] = {}
for bean in beans:
    if bean.parent_id is not None:
        child_counts[bean.parent_id] = child_counts.get(bean.parent_id, 0) + 1
```

Then inside the existing node update loop, after `node.pulsing = (...)`, add:

```python
node.ready = (bean_id in ready_ids and not muted)
node.child_count = child_counts.get(bean_id, 0)
```

- [ ] **Step 3: Add delete_requested signal to DagScene**

In `dag_scene.py`, add to the signal declarations:

```python
delete_requested = Signal(str)
```

- [ ] **Step 4: Write unit test for ready/child_count wiring**

In `tests/test_dag_scene.py`, add:

```python
def test_ready_state_applied_to_nodes(self, qapp, tmp_beans_dir, store):
    from beans import api as beans_api
    a = beans_api.create_bean(store, "Ready")
    b = beans_api.create_bean(store, "Blocked")
    blocker = beans_api.create_bean(store, "Blocker")
    beans_api.add_dep(store, blocker.id, b.id)
    store.close()
    stalk_store = StalkStore(tmp_beans_dir / "beans.db")
    config = StalkConfig()
    scene = DagScene(config, store=stalk_store)
    beans, deps = stalk_store.load_snapshot()
    scene.update_snapshot(beans, deps)
    assert scene._nodes[a.id].ready is True
    assert scene._nodes[b.id].ready is False
    stalk_store.close()

def test_child_count_applied_to_nodes(self, qapp, tmp_beans_dir, store):
    from beans import api as beans_api
    parent = beans_api.create_bean(store, "Parent")
    beans_api.create_bean(store, "Child 1", parent_id=parent.id)
    beans_api.create_bean(store, "Child 2", parent_id=parent.id)
    store.close()
    stalk_store = StalkStore(tmp_beans_dir / "beans.db")
    config = StalkConfig()
    scene = DagScene(config, store=stalk_store)
    beans, deps = stalk_store.load_snapshot()
    scene.update_snapshot(beans, deps)
    assert scene._nodes[parent.id].child_count == 2
    stalk_store.close()
```

Add imports at top of `tests/test_dag_scene.py`:

```python
from beans_stalk.data.store import StalkStore
```

- [ ] **Step 5: Run all scene tests**

Run: `uv run pytest tests/test_dag_scene.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/beans_stalk/ui/dag_scene.py src/beans_stalk/ui/main_window.py tests/test_dag_scene.py
git commit -m "feat: wire ready state, child counts, and delete signal into DagScene"
```

---

### Task 5: DagView — Delete key and context menu

**Files:**
- Modify: `src/beans_stalk/ui/dag_view.py`
- Test: `tests/test_dag_view.py`

- [ ] **Step 1: Write failing test for Delete key**

In `tests/test_dag_view.py`, add:

```python
def test_delete_key_emits_delete_requested(self, qtbot):
    config = StalkConfig()
    scene = DagScene(config)
    view = DagView(scene)
    qtbot.addWidget(view)
    view.show()

    bean = Bean(id="bean-1", title="Delete Me", status="open", type="task",
                priority=2, body="")
    node = BeanNode(bean, "#336699")
    scene.addItem(node)
    scene._nodes["bean-1"] = node
    scene.selected_id = "bean-1"

    deleted_ids = []
    scene.delete_requested.connect(lambda bid: deleted_ids.append(bid))

    qtbot.keyPress(view, Qt.Key.Key_Delete)
    assert deleted_ids == ["bean-1"]

def test_delete_key_noop_on_ghost(self, qtbot):
    config = StalkConfig()
    scene = DagScene(config)
    view = DagView(scene)
    qtbot.addWidget(view)
    view.show()

    bean = Bean(id="bean-1", title="Ghost", status="open", type="task",
                priority=2, body="")
    node = BeanNode(bean, "#336699")
    node.ghost = True
    scene.addItem(node)
    scene._nodes["bean-1"] = node
    scene.selected_id = "bean-1"

    deleted_ids = []
    scene.delete_requested.connect(lambda bid: deleted_ids.append(bid))

    qtbot.keyPress(view, Qt.Key.Key_Delete)
    assert deleted_ids == []

def test_delete_key_noop_when_locked(self, qtbot):
    config = StalkConfig()
    scene = DagScene(config)
    view = DagView(scene)
    qtbot.addWidget(view)
    view.show()
    view.locked = True

    bean = Bean(id="bean-1", title="Locked", status="open", type="task",
                priority=2, body="")
    node = BeanNode(bean, "#336699")
    scene.addItem(node)
    scene._nodes["bean-1"] = node
    scene.selected_id = "bean-1"

    deleted_ids = []
    scene.delete_requested.connect(lambda bid: deleted_ids.append(bid))

    qtbot.keyPress(view, Qt.Key.Key_Delete)
    assert deleted_ids == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_dag_view.py::TestDagView::test_delete_key_emits_delete_requested -v`
Expected: FAIL

- [ ] **Step 3: Implement Delete key handling**

In `dag_view.py`, modify `keyPressEvent`:

```python
def keyPressEvent(self, event):
    if event.key() == Qt.Key.Key_Escape and not self.locked:
        self._dag_scene.selected_id = None
        event.accept()
        return
    if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and not self.locked:
        selected = self._dag_scene.selected_id
        if selected and selected in self._dag_scene._nodes:
            node = self._dag_scene._nodes[selected]
            if not node.ghost:
                self._dag_scene.delete_requested.emit(selected)
        event.accept()
        return
    super().keyPressEvent(event)
```

- [ ] **Step 4: Add "Delete bean" to context menu**

In `dag_view.py`, in `contextMenuEvent`, inside the `isinstance(item, BeanNode)` block, add after the existing actions:

```python
if not item.ghost:
    menu.addSeparator()
    menu.addAction("Delete bean", lambda: self._dag_scene.delete_requested.emit(bean_id))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_dag_view.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/beans_stalk/ui/dag_view.py tests/test_dag_view.py
git commit -m "feat: add Delete key and context menu for bean deletion"
```

---

### Task 6: MainWindow — delete confirmation dialog

**Files:**
- Modify: `src/beans_stalk/ui/main_window.py`
- Test: `tests/test_main_window.py`

- [ ] **Step 1: Write failing test for delete wiring**

In `tests/test_main_window.py`, add:

```python
def test_delete_bean_with_confirmation(self, tmp_beans_dir, store, qtbot, monkeypatch):
    """Delete key should trigger confirmation and delete the bean."""
    a = api.create_bean(store, "Task A")
    store.close()
    win = MainWindow(tmp_beans_dir)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitUntil(lambda: len(win._beans) > 0, timeout=2000)
    win._scene.selected_id = a.id

    # Monkeypatch dialog to return Yes
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    win._on_delete_bean(a.id)

    # Bean should be deleted
    beans, _ = win._store.load_snapshot()
    assert not any(b.id == a.id for b in beans)
    # Selection should be cleared
    assert win._scene.selected_id is None
    win.close()

def test_delete_bean_cancel(self, tmp_beans_dir, store, qtbot, monkeypatch):
    """Cancelling delete should keep the bean."""
    a = api.create_bean(store, "Task A")
    store.close()
    win = MainWindow(tmp_beans_dir)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitUntil(lambda: len(win._beans) > 0, timeout=2000)

    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )

    win._on_delete_bean(a.id)

    beans, _ = win._store.load_snapshot()
    assert any(b.id == a.id for b in beans)
    win.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main_window.py::TestMainWindow::test_delete_bean_with_confirmation -v`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_on_delete_bean'`

- [ ] **Step 3: Implement _on_delete_bean in MainWindow**

In `main_window.py`, connect the signal in `_setup_ui`:

```python
self._scene.delete_requested.connect(self._on_delete_bean)
```

Add the handler:

```python
@Slot(str)
def _on_delete_bean(self, bean_id: str):
    bean = next((b for b in self._beans if b.id == bean_id), None)
    if bean is None:
        return
    # Count children and deps
    n_children = sum(1 for b in self._beans if b.parent_id == bean_id)
    n_deps = sum(1 for d in self._deps if d.from_id == bean_id or d.to_id == bean_id)
    # Build message matching spec's four cases
    title = bean.title
    deps_s = "dependency" if n_deps == 1 else "dependencies"
    children_s = "child" if n_children == 1 else "children"
    if n_deps and n_children:
        msg = f"Delete '{title}' and its {n_deps} {deps_s}? Its {n_children} {children_s} will become orphaned. This cannot be undone."
    elif n_deps:
        msg = f"Delete '{title}' and its {n_deps} {deps_s}? This cannot be undone."
    elif n_children:
        msg = f"Delete '{title}'? Its {n_children} {children_s} will become orphaned. This cannot be undone."
    else:
        msg = f"Delete '{title}'? This cannot be undone."
    result = QMessageBox.warning(
        self, "Delete Bean", msg,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
    )
    if result == QMessageBox.StandardButton.Yes:
        try:
            self._store.delete_bean(bean_id)
        except Exception as e:
            self._sidebar.show_status(str(e))
            return
        self._scene.selected_id = None
        self._sidebar.clear_selection()
```

Add `QMessageBox` to the imports if not already imported (it's imported in sidebar but not main_window — add it):

```python
from PySide6.QtWidgets import QMainWindow, QSplitter, QFileDialog, QWidget, QVBoxLayout, QMessageBox
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_main_window.py -v`
Expected: all pass

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/beans_stalk/ui/main_window.py tests/test_main_window.py
git commit -m "feat: delete bean with confirmation dialog and enhanced warnings"
```

---

### Task 7: Final integration test

**Files:**
- Test: `tests/test_main_window.py`

- [ ] **Step 1: Write integration test for ready + child count**

In `tests/test_main_window.py`, add:

```python
def test_ready_beans_highlighted_after_snapshot(self, tmp_beans_dir, store, qtbot):
    """Ready beans should have node.ready=True after snapshot loads."""
    a = api.create_bean(store, "Ready Task")
    store.close()
    win = MainWindow(tmp_beans_dir)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitUntil(lambda: len(win._beans) > 0, timeout=2000)
    node = win._scene._nodes.get(a.id)
    assert node is not None
    assert node.ready is True
    win.close()

def test_child_count_on_parent_node(self, tmp_beans_dir, store, qtbot):
    """Parent nodes should show child count."""
    parent = api.create_bean(store, "Parent")
    api.create_bean(store, "Child 1", parent_id=parent.id)
    api.create_bean(store, "Child 2", parent_id=parent.id)
    store.close()
    win = MainWindow(tmp_beans_dir)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitUntil(lambda: len(win._beans) > 0, timeout=2000)
    node = win._scene._nodes.get(parent.id)
    assert node is not None
    assert node.child_count == 2
    win.close()
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_main_window.py -v`
Expected: all pass

- [ ] **Step 3: Run full suite**

Run: `uv run pytest`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_main_window.py
git commit -m "test: integration tests for ready highlighting and child count"
```
