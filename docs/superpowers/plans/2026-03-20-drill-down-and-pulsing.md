# Drill-Down Navigation & Pulsing Claimed Nodes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add parent/child drill-down navigation with breadcrumbs and ghost nodes, plus pulsing border animation on claimed beans.

**Architecture:** Modify existing BeanNode to support ghost and pulsing rendering modes. Modify DagScene to filter by current parent level and identify ghost nodes from cross-level deps. Add BreadcrumbBar widget. Wire navigation through MainWindow.

**Tech Stack:** PySide6, existing beans_stalk codebase

**Spec:** `docs/superpowers/specs/2026-03-20-drill-down-and-pulsing-design.md`

**IMPORTANT:** Run `uv sync` first in any worktree before running tests. Use `uv run pytest` (NOT bare pytest).

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/beans_stalk/ui/bean_node.py` | Modify | Add `ghost` and `pulsing` properties with rendering |
| `src/beans_stalk/ui/breadcrumb.py` | Create | BreadcrumbBar widget with path stack and navigation signal |
| `src/beans_stalk/ui/dag_scene.py` | Modify | Filter by parent level, ghost node identification, pulsing logic |
| `src/beans_stalk/ui/dag_view.py` | Modify | Double-click handling for drill-down/ghost navigation |
| `src/beans_stalk/ui/main_window.py` | Modify | Breadcrumb integration, left pane layout, navigation wiring |
| `tests/test_bean_node.py` | Modify | Tests for ghost and pulsing properties |
| `tests/test_breadcrumb.py` | Create | Breadcrumb path management and signal tests |
| `tests/test_drill_down.py` | Create | Ghost identification, navigation, pulsing logic tests |

---

### Task 1: BeanNode Ghost & Pulsing Properties

**Files:**
- Modify: `src/beans_stalk/ui/bean_node.py`
- Modify: `tests/test_bean_node.py`

- [ ] **Step 1: Write failing tests for ghost and pulsing**

Add to `tests/test_bean_node.py`:
```python
class TestBeanNodeGhost:
    def test_ghost_default_false(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        assert not node.ghost

    def test_ghost_property(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.ghost = True
        assert node.ghost

    def test_ghost_sets_pointing_hand_cursor(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.ghost = True
        assert node.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_ghost_clears_cursor(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.ghost = True
        node.ghost = False
        assert node.cursor().shape() == Qt.CursorShape.ArrowCursor


class TestBeanNodePulsing:
    def test_pulsing_default_false(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        assert not node.pulsing

    def test_pulsing_property(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.pulsing = True
        assert node.pulsing

    def test_pulsing_changes_cache_mode(self, qapp):
        from PySide6.QtWidgets import QGraphicsItem
        node = BeanNode(_bean(), "#e06c75")
        assert node.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache
        node.pulsing = True
        assert node.cacheMode() == QGraphicsItem.CacheMode.NoCache
        node.pulsing = False
        assert node.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_pulse_phase_property(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.pulsePhase = 0.5
        assert node.pulsePhase == 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bean_node.py -v -k "Ghost or Pulsing"`
Expected: FAIL

- [ ] **Step 3: Implement ghost and pulsing on BeanNode**

Add these imports to `bean_node.py`:
```python
from PySide6.QtCore import QRectF, Qt, Signal, QPointF, Property, QPropertyAnimation, QEasingCurve
```

Add to `__init__`:
```python
        self._ghost = False
        self._pulsing = False
        self._pulse_phase = 0.0
        self._pulse_anim: QPropertyAnimation | None = None
```

Add properties after existing ones:
```python
    @property
    def ghost(self) -> bool:
        return self._ghost

    @ghost.setter
    def ghost(self, value: bool):
        self._ghost = value
        if value:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    @property
    def pulsing(self) -> bool:
        return self._pulsing

    @pulsing.setter
    def pulsing(self, value: bool):
        if self._pulsing == value:
            return
        self._pulsing = value
        if value:
            self.setCacheMode(self.CacheMode.NoCache)
            self._pulse_anim = QPropertyAnimation(self, b"pulsePhase")
            self._pulse_anim.setDuration(1500)
            self._pulse_anim.setStartValue(0.0)
            self._pulse_anim.setEndValue(1.0)
            self._pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
            self._pulse_anim.setLoopCount(-1)
            self._pulse_anim.start()
        else:
            if self._pulse_anim is not None:
                self._pulse_anim.stop()
                self._pulse_anim = None
            self._pulse_phase = 0.0
            self.setCacheMode(self.CacheMode.DeviceCoordinateCache)
        self.update()

    def _get_pulse_phase(self) -> float:
        return self._pulse_phase

    def _set_pulse_phase(self, value: float):
        self._pulse_phase = value
        self.update()

    pulsePhase = Property(float, _get_pulse_phase, _set_pulse_phase)
```

Modify `paint()` — at the border drawing section, replace the fixed border width with pulsing-aware width:
```python
        # Border
        border_width = 2.0
        if self._pulsing:
            border_width = 2.0 + 2.0 * self._pulse_phase  # pulses 2px to 4px

        if self._ghost:
            fill_color.setAlphaF(0.2)
            painter.setPen(QPen(fill_color.darker(130), border_width, Qt.PenStyle.DashLine))
        else:
            painter.setPen(QPen(fill_color.darker(130), border_width))
        painter.setBrush(fill_color)
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), CORNER_RADIUS, CORNER_RADIUS)
```

For ghost nodes, skip the priority indicator:
```python
        # Priority indicator (skip for ghost nodes)
        if not self._ghost:
            priority_colors = [...]
            ...
```

For ghost text, reduce opacity further:
```python
        if self._ghost:
            tc = QColor(text_color)
            tc.setAlphaF(0.4)
            text_color = tc
        elif self._muted:
            ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_bean_node.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/ui/bean_node.py tests/test_bean_node.py
git commit -m "feat: add ghost and pulsing rendering modes to BeanNode"
```

---

### Task 2: BreadcrumbBar Widget

**Files:**
- Create: `src/beans_stalk/ui/breadcrumb.py`
- Create: `tests/test_breadcrumb.py`

- [ ] **Step 1: Write failing tests**

`tests/test_breadcrumb.py`:
```python
from beans_stalk.ui.breadcrumb import BreadcrumbBar


class TestBreadcrumbBar:
    def test_initial_state_is_root(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        assert bar.current_parent_id is None
        assert len(bar._path) == 0

    def test_push_adds_segment(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "My Epic")
        assert bar.current_parent_id == "bean-001"
        assert len(bar._path) == 1

    def test_push_multiple(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "Epic")
        bar.push("bean-002", "Task")
        assert bar.current_parent_id == "bean-002"
        assert len(bar._path) == 2

    def test_pop_to_root(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "Epic")
        bar.push("bean-002", "Task")
        with qtbot.waitSignal(bar.navigate_to, timeout=1000) as blocker:
            bar.pop_to(None)
        assert blocker.args == [None]
        assert bar.current_parent_id is None
        assert len(bar._path) == 0

    def test_pop_to_mid_level(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "Epic")
        bar.push("bean-002", "Task")
        bar.push("bean-003", "Subtask")
        with qtbot.waitSignal(bar.navigate_to, timeout=1000) as blocker:
            bar.pop_to("bean-001")
        assert blocker.args == ["bean-001"]
        assert bar.current_parent_id == "bean-001"
        assert len(bar._path) == 1

    def test_clear_resets_to_root(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "Epic")
        bar.clear()
        assert bar.current_parent_id is None
        assert len(bar._path) == 0

    def test_button_click_emits_navigate(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "Epic")
        bar.push("bean-002", "Task")
        # Click the Root button (first button in layout)
        root_btn = bar._buttons[0]
        with qtbot.waitSignal(bar.navigate_to, timeout=1000) as blocker:
            root_btn.click()
        assert blocker.args == [None]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_breadcrumb.py -v`
Expected: FAIL — `cannot import name 'BreadcrumbBar'`

- [ ] **Step 3: Implement BreadcrumbBar**

`src/beans_stalk/ui/breadcrumb.py`:
```python
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton


class BreadcrumbBar(QWidget):
    """Navigation breadcrumb for parent/child drill-down."""

    navigate_to = Signal(object)  # str (bean ID) or None (root)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: list[tuple[str, str]] = []  # [(parent_id, title), ...]
        self._buttons: list[QPushButton] = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 2, 4, 2)
        self._layout.setSpacing(2)
        self._rebuild()

    @property
    def current_parent_id(self) -> str | None:
        if not self._path:
            return None
        return self._path[-1][0]

    def push(self, parent_id: str, title: str):
        """Drill into a parent — append to path."""
        self._path.append((parent_id, title))
        self._rebuild()

    def pop_to(self, parent_id: str | None):
        """Navigate to a specific level. None = root."""
        if parent_id is None:
            self._path.clear()
        else:
            for i, (pid, _) in enumerate(self._path):
                if pid == parent_id:
                    self._path = self._path[: i + 1]
                    break
        self._rebuild()
        self.navigate_to.emit(parent_id)

    def clear(self):
        """Reset to root without emitting signal."""
        self._path.clear()
        self._rebuild()

    def _rebuild(self):
        """Rebuild the button layout from current path."""
        # Clear existing widgets
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._buttons.clear()

        # Root button
        root_btn = self._make_button("Root", None)
        self._buttons.append(root_btn)
        self._layout.addWidget(root_btn)

        # Path segments
        for parent_id, title in self._path:
            sep = QLabel(">")
            sep.setStyleSheet("color: #888; font-size: 11px;")
            self._layout.addWidget(sep)
            btn = self._make_button(title, parent_id)
            self._buttons.append(btn)
            self._layout.addWidget(btn)

        self._layout.addStretch()

        # Style the last segment as active (not clickable appearance)
        if self._buttons:
            self._buttons[-1].setStyleSheet(
                "QPushButton { border: none; color: #fff; font-size: 11px; font-weight: bold; padding: 2px 4px; }"
            )

    def _make_button(self, text: str, parent_id: str | None) -> QPushButton:
        btn = QPushButton(text)
        btn.setFlat(True)
        btn.setStyleSheet(
            "QPushButton { border: none; color: #aaa; font-size: 11px; padding: 2px 4px; }"
            "QPushButton:hover { color: #fff; }"
        )
        btn.clicked.connect(lambda checked, pid=parent_id: self.pop_to(pid))
        return btn
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_breadcrumb.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/ui/breadcrumb.py tests/test_breadcrumb.py
git commit -m "feat: add BreadcrumbBar widget for parent/child navigation"
```

---

### Task 3: DagScene Drill-Down & Ghost Logic

**Files:**
- Modify: `src/beans_stalk/ui/dag_scene.py`
- Create: `tests/test_drill_down.py`

- [ ] **Step 1: Write failing tests**

`tests/test_drill_down.py`:
```python
from datetime import datetime, timezone
from beans.models import Bean, BeanId, Dep
from beans_stalk.config import StalkConfig
from beans_stalk.ui.dag_scene import DagScene


def _bean(id_, title="Test", status="open", assignee=None, parent_id=None, **kwargs):
    return Bean(id=BeanId(id_), title=title, status=status, assignee=assignee, parent_id=parent_id, **kwargs)


def _dep(from_id, to_id):
    return Dep(from_id=BeanId(from_id), to_id=BeanId(to_id))


class TestDrillDownFiltering:
    def test_root_shows_only_parentless_beans(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Root task"),
            _bean("bean-002", "Child task", parent_id="bean-001"),
        ]
        scene.update_snapshot(beans, [])
        assert "bean-001" in scene._nodes
        assert "bean-002" not in scene._nodes

    def test_drill_down_shows_children(self, qapp):
        scene = DagScene(StalkConfig())
        scene.current_parent_id = "bean-001"
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child A", parent_id="bean-001"),
            _bean("bean-003", "Child B", parent_id="bean-001"),
        ]
        scene.update_snapshot(beans, [])
        assert "bean-001" not in scene._nodes
        assert "bean-002" in scene._nodes
        assert "bean-003" in scene._nodes

    def test_root_view_after_drill_down(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child", parent_id="bean-001"),
        ]
        scene.current_parent_id = "bean-001"
        scene.update_snapshot(beans, [])
        assert "bean-002" in scene._nodes

        scene.current_parent_id = None
        scene.update_snapshot(beans, [])
        assert "bean-001" in scene._nodes
        assert "bean-002" not in scene._nodes


class TestGhostNodes:
    def test_cross_level_dep_creates_ghost(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Root A"),
            _bean("bean-002", "Root B"),
            _bean("bean-003", "Child of A", parent_id="bean-001"),
        ]
        deps = [_dep("bean-003", "bean-002")]  # child of A blocks root B
        scene.current_parent_id = "bean-001"
        scene.update_snapshot(beans, deps)
        # bean-003 is a regular node, bean-002 is a ghost
        assert "bean-003" in scene._nodes
        assert not scene._nodes["bean-003"].ghost
        assert "bean-002" in scene._nodes
        assert scene._nodes["bean-002"].ghost

    def test_no_transitive_ghosts(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child", parent_id="bean-001"),
            _bean("bean-003", "External A"),
            _bean("bean-004", "External B"),
        ]
        deps = [
            _dep("bean-002", "bean-003"),  # child -> ext A (ghost)
            _dep("bean-003", "bean-004"),  # ext A -> ext B (NOT ghost)
        ]
        scene.current_parent_id = "bean-001"
        scene.update_snapshot(beans, deps)
        assert "bean-003" in scene._nodes  # direct dep ghost
        assert "bean-004" not in scene._nodes  # transitive — not shown

    def test_ghost_to_ghost_edge_shown(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child", parent_id="bean-001"),
            _bean("bean-003", "External A"),
            _bean("bean-004", "External B"),
        ]
        deps = [
            _dep("bean-002", "bean-003"),  # child -> ext A
            _dep("bean-002", "bean-004"),  # child -> ext B
            _dep("bean-003", "bean-004"),  # ext A -> ext B (both ghosts)
        ]
        scene.current_parent_id = "bean-001"
        scene.update_snapshot(beans, deps)
        assert ("bean-003", "bean-004") in scene._edges


class TestPulsingLogic:
    def test_claimed_bean_pulses(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-001", "Claimed", status="in_progress", assignee="alice")]
        scene.update_snapshot(beans, [])
        assert scene._nodes["bean-001"].pulsing

    def test_unclaimed_bean_does_not_pulse(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-001", "Open")]
        scene.update_snapshot(beans, [])
        assert not scene._nodes["bean-001"].pulsing

    def test_parent_pulses_when_child_claimed(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child", status="in_progress", assignee="alice", parent_id="bean-001"),
        ]
        scene.update_snapshot(beans, [])
        # Root view shows parent, child is hidden
        assert "bean-001" in scene._nodes
        assert scene._nodes["bean-001"].pulsing

    def test_grandparent_pulses_when_grandchild_claimed(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Grandparent"),
            _bean("bean-002", "Parent", parent_id="bean-001"),
            _bean("bean-003", "Child", status="in_progress", assignee="bob", parent_id="bean-002"),
        ]
        scene.update_snapshot(beans, [])
        assert scene._nodes["bean-001"].pulsing


class TestHasChildren:
    def test_parent_detected(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child", parent_id="bean-001"),
        ]
        scene.update_snapshot(beans, [])
        assert "bean-001" in scene._parent_ids

    def test_childless_not_parent(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-001", "Leaf")]
        scene.update_snapshot(beans, [])
        assert "bean-001" not in scene._parent_ids


class TestEmptyDrillDown:
    def test_all_children_closed_shows_message(self, qapp):
        scene = DagScene(StalkConfig(fade_minutes=0))
        scene.current_parent_id = "bean-001"
        beans = [
            _bean("bean-001", "Parent"),
            _bean("bean-002", "Child", status="closed", parent_id="bean-001",
                  closed_at=datetime(2020, 1, 1, tzinfo=timezone.utc)),
        ]
        scene.update_snapshot(beans, [])
        assert scene._placeholder is not None
        assert "closed" in scene._placeholder.toPlainText().lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_drill_down.py -v`
Expected: FAIL

- [ ] **Step 3: Implement drill-down logic in DagScene**

Modify `dag_scene.py`:

Add to imports:
```python
from PySide6.QtCore import QPointF, QEasingCurve, QPropertyAnimation, Signal
```

Add to class signals:
```python
    navigate_requested = Signal(object)  # str (bean ID) or None (root)
```

Add to `__init__`:
```python
        self._current_parent_id: str | None = None
        self._parent_ids: set[str] = set()
        self._all_beans: list[Bean] = []
```

Add property:
```python
    @property
    def current_parent_id(self) -> str | None:
        return self._current_parent_id

    @current_parent_id.setter
    def current_parent_id(self, value: str | None):
        self._current_parent_id = value
```

Modify `update_snapshot()` — the key change is filtering beans by parent level and identifying ghosts. Replace the "Determine visible beans" section:

```python
    def update_snapshot(self, beans: list[Bean], deps: list[Dep]):
        now = datetime.now(timezone.utc)
        self._all_beans = beans

        # Precompute parent IDs and active-descendant set
        self._parent_ids = set()
        children_map: dict[str | None, list[str]] = {}  # parent_id -> [child_ids]
        bean_by_id: dict[str, Bean] = {}
        for bean in beans:
            bean_by_id[bean.id] = bean
            if bean.parent_id is not None:
                self._parent_ids.add(bean.parent_id)
                children_map.setdefault(bean.parent_id, []).append(bean.id)

        # Compute which beans have active descendants (recursive)
        active_ancestors: set[str] = set()
        for bean in beans:
            if bean.status == "in_progress" and bean.assignee is not None:
                # Walk up parent chain marking all ancestors
                current = bean.parent_id
                while current is not None:
                    if current in active_ancestors:
                        break
                    active_ancestors.add(current)
                    parent_bean = bean_by_id.get(current)
                    current = parent_bean.parent_id if parent_bean else None

        # Filter beans for current level
        level_beans: dict[str, tuple[Bean, bool]] = {}
        for bean in beans:
            if bean.parent_id != self._current_parent_id:
                continue
            if bean.status == "closed":
                if self._show_completed:
                    level_beans[bean.id] = (bean, True)
                elif bean.closed_at and self._is_recently_closed(bean.closed_at, now):
                    level_beans[bean.id] = (bean, True)
            else:
                level_beans[bean.id] = (bean, False)

        # Identify ghost nodes: direct deps to/from level beans that are outside this level
        regular_ids = set(level_beans.keys())
        ghost_ids: set[str] = set()
        for dep in deps:
            if dep.from_id in regular_ids and dep.to_id not in regular_ids:
                ghost_ids.add(dep.to_id)
            elif dep.to_id in regular_ids and dep.from_id not in regular_ids:
                ghost_ids.add(dep.from_id)

        # Build visible_beans combining regular + ghost
        visible_beans: dict[str, tuple[Bean, bool]] = dict(level_beans)
        for gid in ghost_ids:
            if gid in bean_by_id and gid not in visible_beans:
                ghost_bean = bean_by_id[gid]
                visible_beans[gid] = (ghost_bean, False)

        # ... rest of layout, node creation, edge creation as before ...
        # but when creating/updating nodes, set ghost and pulsing:
```

In the node add/update loop, after setting color/muted:
```python
            is_ghost = bean_id in ghost_ids
            is_pulsing = (
                (bean.status == "in_progress" and bean.assignee is not None)
                or bean_id in active_ancestors
            )
            # ... existing node creation/update ...
            node.ghost = is_ghost
            node.pulsing = is_pulsing
```

Update the placeholder message for drill-down context:
```python
        if not visible_beans:
            if self._current_parent_id is not None:
                self._show_placeholder("All children are closed")
            else:
                self._show_placeholder("No beans yet — create one with Cmd-N or right-click")
        else:
            self._hide_placeholder()
```

Update `_show_placeholder` to accept a message parameter:
```python
    def _show_placeholder(self, message: str = "No beans yet — create one with Cmd-N or right-click"):
        if self._placeholder is not None:
            self.removeItem(self._placeholder)
        self._placeholder = QGraphicsTextItem(message)
        self._placeholder.setDefaultTextColor(QColor("#888888"))
        self._placeholder.setFont(QFont("system-ui", 14))
        self.addItem(self._placeholder)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_drill_down.py tests/test_dag_scene.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/ui/dag_scene.py tests/test_drill_down.py
git commit -m "feat: add parent/child filtering, ghost nodes, and pulsing logic to DagScene"
```

---

### Task 4: DagView Double-Click Navigation

**Files:**
- Modify: `src/beans_stalk/ui/dag_view.py`

- [ ] **Step 1: Add double-click handler to DagView**

Add `mouseDoubleClickEvent` to `DagView`:
```python
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if isinstance(item, BeanNode):
                if item.ghost:
                    # Navigate to ghost's home view
                    self._dag_scene.navigate_requested.emit(item.bean.parent_id)
                elif item.bean.id in self._dag_scene._parent_ids:
                    # Drill into parent's children
                    self._dag_scene.navigate_requested.emit(item.bean.id)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/beans_stalk/ui/dag_view.py
git commit -m "feat: add double-click navigation for drill-down and ghost nodes"
```

---

### Task 5: MainWindow Breadcrumb Integration

**Files:**
- Modify: `src/beans_stalk/ui/main_window.py`

- [ ] **Step 1: Wire breadcrumb into main window**

Add import:
```python
from PySide6.QtWidgets import QMainWindow, QSplitter, QFileDialog, QWidget, QVBoxLayout
from beans_stalk.ui.breadcrumb import BreadcrumbBar
```

Modify `_setup_ui` — wrap the DAG view in a QVBoxLayout with breadcrumb above it:
```python
    def _setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left pane: breadcrumb + DAG view
        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self._breadcrumb = BreadcrumbBar()
        left_layout.addWidget(self._breadcrumb)

        self._scene = DagScene(self._config)
        self._view = DagView(self._scene)
        left_layout.addWidget(self._view)

        splitter.addWidget(left_pane)

        self._sidebar = Sidebar(self._config)
        splitter.addWidget(self._sidebar)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([900, 300])
        self.setCentralWidget(splitter)

        # Connect signals
        # ... existing signal connections ...
        self._breadcrumb.navigate_to.connect(self._on_breadcrumb_navigate)
        self._scene.navigate_requested.connect(self._on_scene_navigate)
```

Add two navigation methods — one for scene updates only, one for breadcrumb-triggered navigation:
```python
    def _apply_navigation(self, parent_id):
        """Update scene to show a parent level. Does NOT touch breadcrumb."""
        self._scene.selected_id = None
        self._scene.current_parent_id = parent_id
        self._scene.update_snapshot(self._beans, self._deps)

    def _on_scene_navigate(self, parent_id):
        """Handle navigation from double-click in DAG (scene signal).
        Updates both breadcrumb and scene."""
        if parent_id is None:
            self._breadcrumb.clear()
        else:
            # Check if popping back or drilling deeper
            found = False
            for pid, _ in self._breadcrumb._path:
                if pid == parent_id:
                    # Block signal to avoid re-entrancy, then pop
                    self._breadcrumb.blockSignals(True)
                    self._breadcrumb.pop_to(parent_id)
                    self._breadcrumb.blockSignals(False)
                    found = True
                    break
            if not found:
                bean = next((b for b in self._beans if b.id == parent_id), None)
                title = bean.title if bean else parent_id
                self._breadcrumb.push(parent_id, title)
        self._apply_navigation(parent_id)

    def _on_breadcrumb_navigate(self, parent_id):
        """Handle navigation from breadcrumb click.
        Breadcrumb already updated itself — just update scene."""
        self._apply_navigation(parent_id)
```

Wire the signals separately:
```python
        self._breadcrumb.navigate_to.connect(self._on_breadcrumb_navigate)
        self._scene.navigate_requested.connect(self._on_scene_navigate)
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/beans_stalk/ui/main_window.py
git commit -m "feat: integrate breadcrumb bar and navigation wiring in MainWindow"
```

---

### Task 6: Integration Testing & Smoke Test

**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Add drill-down integration test**

Add to `tests/test_integration.py`:
```python
class TestDrillDownIntegration:
    def test_drill_down_round_trip(self, tmp_beans_dir, store, qapp):
        """Create parent+children, verify drill-down shows correct beans."""
        from beans import api
        from beans_stalk.config import StalkConfig
        from beans_stalk.data.store import StalkStore
        from beans_stalk.ui.dag_scene import DagScene

        parent = api.create_bean(store, "Epic")
        child_a = api.create_bean(store, "Task A", parent_id=parent.id)
        child_b = api.create_bean(store, "Task B", parent_id=parent.id)
        api.add_dep(store, child_a.id, child_b.id)
        store.close()

        ss = StalkStore(tmp_beans_dir / "beans.db")
        beans, deps = ss.load_snapshot()
        ss.close()

        config = StalkConfig()
        scene = DagScene(config)

        # Root view — only parent visible
        scene.update_snapshot(beans, deps)
        assert parent.id in scene._nodes
        assert child_a.id not in scene._nodes

        # Drill down — children visible
        scene.current_parent_id = parent.id
        scene.update_snapshot(beans, deps)
        assert child_a.id in scene._nodes
        assert child_b.id in scene._nodes
        assert parent.id not in scene._nodes

        # Back to root
        scene.current_parent_id = None
        scene.update_snapshot(beans, deps)
        assert parent.id in scene._nodes
        assert child_a.id not in scene._nodes
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add drill-down integration test"
```

---

## Task Dependency Order

```
Task 1 (bean_node ghost+pulsing)
  └→ Task 2 (breadcrumb widget) — independent, can parallel with 1
  └→ Task 3 (dag_scene drill-down) — depends on 1
       └→ Task 4 (dag_view double-click) — depends on 3
            └→ Task 5 (main_window wiring) — depends on 2, 3, 4
                 └→ Task 6 (integration tests) — depends on 5
```

Tasks 1 and 2 can run in parallel.
