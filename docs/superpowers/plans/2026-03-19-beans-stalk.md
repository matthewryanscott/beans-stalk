# Beans Stalk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PySide6 companion app for the Beans task tracker that visualizes bean dependencies as an interactive DAG with a sidebar editor.

**Architecture:** Layered design — `data/` (beans API wrapper + file watcher, no Qt), `graph/` (networkx layout, no Qt), `ui/` (PySide6 widgets). Single-instance app via Unix domain socket IPC. Config in TOML beside the beans DB.

**Tech Stack:** Python 3.14+, PySide6, magic-beans, networkx, pygraphviz, watchdog, tomli-w, typer

**Spec:** `docs/superpowers/specs/2026-03-19-beans-stalk-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Package metadata, dependencies, entry point |
| `src/beans_stalk/__init__.py` | Package init |
| `src/beans_stalk/main.py` | CLI entry point (typer), single-instance IPC client |
| `src/beans_stalk/app.py` | QApplication lifecycle, socket server |
| `src/beans_stalk/config.py` | `beans-stalk.toml` read/write, color palette |
| `src/beans_stalk/data/__init__.py` | Package init |
| `src/beans_stalk/data/store.py` | Wraps `beans.store.Store` + `beans.api` |
| `src/beans_stalk/data/watcher.py` | Hybrid watchdog + poll change detection |
| `src/beans_stalk/graph/__init__.py` | Package init |
| `src/beans_stalk/graph/layout.py` | networkx DAG construction + graphviz layout |
| `src/beans_stalk/ui/__init__.py` | Package init |
| `src/beans_stalk/ui/main_window.py` | Main window, menu bar, splitter, stay-on-top |
| `src/beans_stalk/ui/dag_view.py` | QGraphicsView: zoom, pan, shift-drag interaction |
| `src/beans_stalk/ui/dag_scene.py` | QGraphicsScene: manages nodes + edges, animation |
| `src/beans_stalk/ui/bean_node.py` | QGraphicsObject: single bean node rendering |
| `src/beans_stalk/ui/dep_edge.py` | QGraphicsPathItem: dependency arrow rendering |
| `src/beans_stalk/ui/sidebar.py` | Bean property editor panel |
| `tests/conftest.py` | Shared fixtures (temp beans DB, Store instances) |
| `tests/test_config.py` | Config read/write/color tests |
| `tests/test_store.py` | Data store wrapper tests |
| `tests/test_watcher.py` | Watcher change detection tests |
| `tests/test_layout.py` | Graph layout tests |
| `tests/test_ipc.py` | Single-instance IPC tests |
| `tests/test_bean_node.py` | Bean node rendering/interaction tests |
| `tests/test_dep_edge.py` | Dependency edge rendering tests |
| `tests/test_dag_scene.py` | DAG scene state management tests |
| `tests/test_dag_view.py` | DAG view interaction tests |
| `tests/test_sidebar.py` | Sidebar editor tests |
| `tests/test_main_window.py` | Main window integration tests |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/beans_stalk/__init__.py`
- Create: `src/beans_stalk/data/__init__.py`
- Create: `src/beans_stalk/graph/__init__.py`
- Create: `src/beans_stalk/ui/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "beans-stalk"
version = "0.1.0"
description = "Visual DAG companion for the Beans task tracker"
requires-python = ">=3.14"
dependencies = [
    "pyside6",
    "magic-beans",
    "networkx",
    "pygraphviz",
    "watchdog",
    "tomli-w",
    "typer",
]

[project.scripts]
stalk = "beans_stalk.main:app"

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-qt",
]
```

- [ ] **Step 2: Create package init files**

`src/beans_stalk/__init__.py`:
```python
"""Beans Stalk — Visual DAG companion for the Beans task tracker."""
```

`src/beans_stalk/data/__init__.py`, `src/beans_stalk/graph/__init__.py`, `src/beans_stalk/ui/__init__.py`, `tests/__init__.py`: empty files.

- [ ] **Step 3: Create test conftest with shared fixtures**

`tests/conftest.py`:
```python
"""Pytest configuration for headless Qt testing."""

import os

import pytest
from beans.store import Store

# Set headless mode before any Qt imports
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def tmp_beans_dir(tmp_path):
    """Create a temporary .beans directory with initialized DB."""
    beans_dir = tmp_path / ".beans"
    beans_dir.mkdir()
    db_path = beans_dir / "beans.db"
    store = Store.from_path(str(db_path))
    store.close()
    return beans_dir


@pytest.fixture
def store(tmp_beans_dir):
    """Provide an open Store connected to a temporary beans DB."""
    db_path = tmp_beans_dir / "beans.db"
    s = Store.from_path(str(db_path))
    yield s
    s.close()
```

Note: pytest-qt provides `qapp` and `qtbot` fixtures automatically. We only set `QT_QPA_PLATFORM=offscreen` at module level to ensure headless mode. Do NOT define custom `qapp` or `qtbot` fixtures — use pytest-qt's built-in ones.

- [ ] **Step 4: Install in editable mode and verify**

Run: `pip install -e ".[dev]" && python -c "import beans_stalk; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Run pytest to verify fixtures work**

Run: `pytest tests/ -v --co`
Expected: No errors, conftest loads successfully

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "feat: scaffold beans-stalk project with dependencies and test fixtures"
```

---

### Task 2: Configuration Module

**Files:**
- Create: `src/beans_stalk/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for config**

`tests/test_config.py`:
```python
from pathlib import Path

from beans_stalk.config import StalkConfig, DEFAULT_PALETTE


class TestStalkConfig:
    def test_load_defaults_when_no_file(self, tmp_path):
        config = StalkConfig.load(tmp_path)
        assert config.fade_minutes == 5
        assert config.poll_interval_seconds == 2
        assert config.colors == {}

    def test_load_from_existing_file(self, tmp_path):
        toml_path = tmp_path / "beans-stalk.toml"
        toml_path.write_text(
            'fade_minutes = 10\npoll_interval_seconds = 3\n\n'
            '[colors]\nalice = "#ff0000"\n'
        )
        config = StalkConfig.load(tmp_path)
        assert config.fade_minutes == 10
        assert config.poll_interval_seconds == 3
        assert config.colors == {"alice": "#ff0000"}

    def test_save_creates_file(self, tmp_path):
        config = StalkConfig(fade_minutes=5, poll_interval_seconds=2, colors={"bob": "#00ff00"})
        config.save(tmp_path)
        toml_path = tmp_path / "beans-stalk.toml"
        assert toml_path.exists()
        reloaded = StalkConfig.load(tmp_path)
        assert reloaded.colors == {"bob": "#00ff00"}

    def test_get_color_returns_assigned(self, tmp_path):
        config = StalkConfig(colors={"alice": "#ff0000"})
        assert config.get_color("alice") == "#ff0000"

    def test_get_color_auto_assigns_from_palette(self, tmp_path):
        config = StalkConfig(colors={})
        color = config.get_color("alice")
        assert color == DEFAULT_PALETTE[0]
        assert config.colors["alice"] == DEFAULT_PALETTE[0]

    def test_get_color_skips_used_palette_colors(self, tmp_path):
        config = StalkConfig(colors={"alice": DEFAULT_PALETTE[0]})
        color = config.get_color("bob")
        assert color == DEFAULT_PALETTE[1]
        assert config.colors["bob"] == DEFAULT_PALETTE[1]

    def test_get_color_falls_back_to_hash_when_palette_exhausted(self, tmp_path):
        colors = {f"user{i}": c for i, c in enumerate(DEFAULT_PALETTE)}
        config = StalkConfig(colors=colors)
        color = config.get_color("newuser")
        assert color.startswith("#")
        assert len(color) == 7
        assert config.colors["newuser"] == color

    def test_get_color_for_none_assignee(self):
        config = StalkConfig(colors={})
        color = config.get_color(None)
        assert color.startswith("#")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `cannot import name 'StalkConfig'`

- [ ] **Step 3: Implement config module**

`src/beans_stalk/config.py`:
```python
import hashlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

CONFIG_FILENAME = "beans-stalk.toml"

DEFAULT_PALETTE = [
    "#e06c75",  # red
    "#61afef",  # blue
    "#98c379",  # green
    "#e5c07b",  # yellow
    "#c678dd",  # purple
    "#56b6c2",  # cyan
    "#d19a66",  # orange
    "#be5046",  # dark red
    "#528bff",  # bright blue
    "#7ec699",  # mint
    "#f0c674",  # gold
    "#a9a1e1",  # lavender
]

UNASSIGNED_COLOR = "#888888"


@dataclass
class StalkConfig:
    fade_minutes: int = 5
    poll_interval_seconds: int = 2
    colors: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, beans_dir: Path) -> "StalkConfig":
        toml_path = beans_dir / CONFIG_FILENAME
        if not toml_path.exists():
            return cls()
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        return cls(
            fade_minutes=data.get("fade_minutes", 5),
            poll_interval_seconds=data.get("poll_interval_seconds", 2),
            colors=dict(data.get("colors", {})),
        )

    def save(self, beans_dir: Path) -> None:
        toml_path = beans_dir / CONFIG_FILENAME
        data = {
            "fade_minutes": self.fade_minutes,
            "poll_interval_seconds": self.poll_interval_seconds,
            "colors": self.colors,
        }
        with open(toml_path, "wb") as f:
            tomli_w.dump(data, f)

    def get_color(self, assignee: str | None) -> str:
        if assignee is None:
            return UNASSIGNED_COLOR
        if assignee in self.colors:
            return self.colors[assignee]
        used = set(self.colors.values())
        for color in DEFAULT_PALETTE:
            if color not in used:
                self.colors[assignee] = color
                return color
        # Palette exhausted — deterministic hash
        h = hashlib.sha256(assignee.encode()).hexdigest()[:6]
        color = f"#{h}"
        self.colors[assignee] = color
        return color
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/config.py tests/test_config.py
git commit -m "feat: add config module with TOML persistence and color auto-assignment"
```

---

### Task 3: Data Store Wrapper

**Files:**
- Create: `src/beans_stalk/data/store.py`
- Create: `tests/test_store.py`

- [ ] **Step 1: Write failing tests for data store**

`tests/test_store.py`:
```python
from beans.models import Bean, Dep
from beans import api

from beans_stalk.data.store import StalkStore


class TestStalkStore:
    def test_open_and_close(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        assert ss.store is not None
        ss.close()

    def test_load_snapshot_empty(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        beans, deps = ss.load_snapshot()
        assert beans == []
        assert deps == []
        ss.close()

    def test_load_snapshot_with_beans(self, tmp_beans_dir, store):
        api.create_bean(store, "Task A")
        api.create_bean(store, "Task B")
        store.close()

        ss = StalkStore(tmp_beans_dir / "beans.db")
        beans, deps = ss.load_snapshot()
        assert len(beans) == 2
        titles = {b.title for b in beans}
        assert titles == {"Task A", "Task B"}
        ss.close()

    def test_load_snapshot_with_deps(self, tmp_beans_dir, store):
        a = api.create_bean(store, "Task A")
        b = api.create_bean(store, "Task B")
        api.add_dep(store, a.id, b.id)
        store.close()

        ss = StalkStore(tmp_beans_dir / "beans.db")
        beans, deps = ss.load_snapshot()
        assert len(deps) == 1
        assert deps[0].from_id == a.id
        assert deps[0].to_id == b.id
        ss.close()

    def test_create_bean(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        bean = ss.create_bean("New Task", type="bug", priority=1)
        assert bean.title == "New Task"
        assert bean.type == "bug"
        assert bean.priority == 1
        ss.close()

    def test_update_bean(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        bean = ss.create_bean("Original")
        updated = ss.update_bean(bean.id, title="Updated")
        assert updated.title == "Updated"
        ss.close()

    def test_close_bean(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        bean = ss.create_bean("To close")
        closed = ss.close_bean(bean.id, reason="Done")
        assert closed.status == "closed"
        assert closed.close_reason == "Done"
        ss.close()

    def test_add_and_remove_dep(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        a = ss.create_bean("A")
        b = ss.create_bean("B")
        dep = ss.add_dep(a.id, b.id)
        assert dep.from_id == a.id

        ss.remove_dep(a.id, b.id)
        _, deps = ss.load_snapshot()
        assert len(deps) == 0
        ss.close()

    def test_claim_and_release(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        bean = ss.create_bean("Claimable")
        claimed = ss.claim_bean(bean.id, "alice")
        assert claimed.assignee == "alice"
        assert claimed.status == "in_progress"

        released = ss.release_bean(bean.id, "alice")
        assert released.assignee is None
        assert released.status == "open"
        ss.close()

    def test_data_version(self, tmp_beans_dir):
        ss = StalkStore(tmp_beans_dir / "beans.db")
        v1 = ss.data_version()
        ss.create_bean("Trigger change")
        v2 = ss.data_version()
        assert v2 != v1
        ss.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_store.py -v`
Expected: FAIL — `cannot import name 'StalkStore'`

- [ ] **Step 3: Implement data store**

`src/beans_stalk/data/store.py`:
```python
from pathlib import Path

from beans import api
from beans.models import Bean, Dep
from beans.store import Store


class StalkStore:
    """Wraps beans Store for Beans Stalk read/write operations."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.store = Store.from_path(str(self.db_path))
        self.store.conn.execute("PRAGMA busy_timeout=5000")

    def close(self):
        self.store.close()

    def load_snapshot(self) -> tuple[list[Bean], list[Dep]]:
        beans = self.store.list()
        deps = self.store.list_all_deps()
        return beans, deps

    def data_version(self) -> int:
        row = self.store.conn.execute("PRAGMA data_version").fetchone()
        return row[0]

    # Write operations — delegate to beans.api

    def create_bean(self, title: str, **fields) -> Bean:
        return api.create_bean(self.store, title, **fields)

    def update_bean(self, bean_id: str, **fields) -> Bean:
        return api.update_bean(self.store, bean_id, **fields)

    def close_bean(self, bean_id: str, reason: str | None = None) -> Bean:
        return api.close_bean(self.store, bean_id, reason=reason)

    def claim_bean(self, bean_id: str, actor: str) -> Bean:
        return api.claim_bean(self.store, bean_id, actor)

    def release_bean(self, bean_id: str, actor: str) -> Bean:
        return api.release_bean(self.store, bean_id, actor)

    def add_dep(self, from_id: str, to_id: str, dep_type: str = "blocks") -> Dep:
        return api.add_dep(self.store, from_id, to_id, dep_type=dep_type)

    def remove_dep(self, from_id: str, to_id: str) -> int:
        return api.remove_dep(self.store, from_id, to_id)

    def show_bean(self, bean_id: str) -> Bean:
        return api.show_bean(self.store, bean_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_store.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/data/store.py tests/test_store.py
git commit -m "feat: add data store wrapper around beans API"
```

---

### Task 4: Data Watcher

**Files:**
- Create: `src/beans_stalk/data/watcher.py`
- Create: `tests/test_watcher.py`

- [ ] **Step 1: Write failing tests for watcher**

`tests/test_watcher.py`:
```python
from beans import api

from beans_stalk.data.watcher import DataWatcher


class TestDataWatcher:
    def test_emits_initial_snapshot(self, tmp_beans_dir, store, qtbot):
        api.create_bean(store, "Existing bean")

        watcher = DataWatcher(
            db_path=tmp_beans_dir / "beans.db",
            poll_interval_seconds=10,  # won't fire in this test
        )
        with qtbot.waitSignal(watcher.snapshot_changed, timeout=1000) as blocker:
            watcher.start()
        watcher.stop()

        beans, deps = blocker.args
        assert any(b.title == "Existing bean" for b in beans)

    def test_detects_change_on_poll(self, tmp_beans_dir, store, qtbot):
        watcher = DataWatcher(
            db_path=tmp_beans_dir / "beans.db",
            poll_interval_seconds=0.1,
        )
        watcher.start()
        # Consume initial snapshot
        qtbot.waitSignal(watcher.snapshot_changed, timeout=1000)

        # Make a change via the external store
        api.create_bean(store, "New bean")

        # Wait for poll to detect it
        with qtbot.waitSignal(watcher.snapshot_changed, timeout=2000) as blocker:
            pass
        watcher.stop()

        beans, deps = blocker.args
        assert any(b.title == "New bean" for b in beans)

    def test_no_spurious_signals_without_changes(self, tmp_beans_dir, qtbot):
        watcher = DataWatcher(
            db_path=tmp_beans_dir / "beans.db",
            poll_interval_seconds=0.1,
        )
        signals = []
        watcher.snapshot_changed.connect(lambda b, d: signals.append((b, d)))
        watcher.start()

        qtbot.wait(500)
        watcher.stop()

        # Should get initial snapshot but no spurious updates
        assert len(signals) == 1

    def test_stop_is_idempotent(self, tmp_beans_dir):
        watcher = DataWatcher(
            db_path=tmp_beans_dir / "beans.db",
            poll_interval_seconds=1,
        )
        watcher.start()
        watcher.stop()
        watcher.stop()  # Should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_watcher.py -v`
Expected: FAIL — `cannot import name 'DataWatcher'`

- [ ] **Step 3: Implement data watcher**

`src/beans_stalk/data/watcher.py`:
```python
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from beans.models import Bean, Dep
from beans_stalk.data.store import StalkStore


class _DbFileHandler(FileSystemEventHandler):
    """Watches for filesystem changes to the DB and WAL files."""

    def __init__(self, db_path: Path, trigger_poll: callable):
        self._db_name = db_path.name
        self._wal_name = f"{db_path.name}-wal"
        self._trigger_poll = trigger_poll

    def on_modified(self, event):
        if event.is_directory:
            return
        name = Path(event.src_path).name
        if name in (self._db_name, self._wal_name):
            self._trigger_poll()

    def on_created(self, event):
        self.on_modified(event)


class DataWatcher(QObject):
    """Hybrid watchdog + poll change detector for a beans database.

    Thread safety: watchdog callbacks schedule a check on the main thread
    via QTimer.singleShot. All Store access happens on the main thread only.
    """

    snapshot_changed = Signal(list, list)  # list[Bean], list[Dep]

    def __init__(
        self,
        db_path: Path | str,
        poll_interval_seconds: float,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._db_path = Path(db_path)
        self._poll_interval_ms = int(poll_interval_seconds * 1000)
        self._store: StalkStore | None = None
        self._observer: Observer | None = None
        self._poll_timer: QTimer | None = None
        self._last_data_version: int | None = None
        self._debounce_timer: QTimer | None = None

    def start(self):
        # Store access only on main thread
        self._store = StalkStore(self._db_path)
        self._last_data_version = self._store.data_version()

        # Send initial snapshot
        beans, deps = self._store.load_snapshot()
        self.snapshot_changed.emit(beans, deps)

        # Debounce timer (single-shot, reset on each watchdog event)
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._debounce_timer.timeout.connect(self._check_for_changes)

        # Start watchdog observer
        handler = _DbFileHandler(self._db_path, self._trigger_debounced_poll)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._db_path.parent), recursive=False)
        self._observer.start()

        # Start fallback poll timer (runs on main thread via Qt event loop)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._poll_interval_ms)
        self._poll_timer.timeout.connect(self._check_for_changes)
        self._poll_timer.start()

    def stop(self):
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
            self._debounce_timer = None
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        if self._store is not None:
            self._store.close()
            self._store = None

    def _trigger_debounced_poll(self):
        """Called from watchdog thread — marshals to main thread via QTimer."""
        QTimer.singleShot(0, self._debounce_timer.start)

    def _check_for_changes(self):
        """Runs on main thread only. Checks data_version and emits if changed."""
        if self._store is None:
            return
        current_version = self._store.data_version()
        if current_version != self._last_data_version:
            self._last_data_version = current_version
            beans, deps = self._store.load_snapshot()
            self.snapshot_changed.emit(beans, deps)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_watcher.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/data/watcher.py tests/test_watcher.py
git commit -m "feat: add hybrid watchdog+poll data watcher for beans DB"
```

---

### Task 5: Graph Layout Module

**Files:**
- Create: `src/beans_stalk/graph/layout.py`
- Create: `tests/test_layout.py`

- [ ] **Step 1: Write failing tests for layout**

`tests/test_layout.py`:
```python
from beans.models import Bean, BeanId, Dep

from beans_stalk.graph.layout import build_dag, compute_layout


def _bean(id_: str, title: str, status: str = "open", assignee: str | None = None) -> Bean:
    return Bean(id=BeanId(id_), title=title, status=status, assignee=assignee)


def _dep(from_id: str, to_id: str) -> Dep:
    return Dep(from_id=BeanId(from_id), to_id=BeanId(to_id))


class TestBuildDag:
    def test_empty(self):
        g = build_dag([], [])
        assert len(g.nodes) == 0
        assert len(g.edges) == 0

    def test_single_bean(self):
        beans = [_bean("bean-00000001", "Task A")]
        g = build_dag(beans, [])
        assert list(g.nodes) == ["bean-00000001"]
        assert g.nodes["bean-00000001"]["bean"].title == "Task A"

    def test_with_dependency(self):
        beans = [
            _bean("bean-00000001", "A"),
            _bean("bean-00000002", "B"),
        ]
        deps = [_dep("bean-00000001", "bean-00000002")]
        g = build_dag(beans, deps)
        assert ("bean-00000001", "bean-00000002") in g.edges

    def test_ignores_deps_for_missing_beans(self):
        beans = [_bean("bean-00000001", "A")]
        deps = [_dep("bean-00000001", "bean-99999999")]
        g = build_dag(beans, deps)
        assert len(g.edges) == 0


class TestComputeLayout:
    def test_empty(self):
        g = build_dag([], [])
        positions = compute_layout(g, set())
        assert positions == {}

    def test_single_node(self):
        beans = [_bean("bean-00000001", "A")]
        g = build_dag(beans, [])
        positions = compute_layout(g, {"bean-00000001"})
        assert "bean-00000001" in positions
        x, y = positions["bean-00000001"]
        assert isinstance(x, float)
        assert isinstance(y, float)

    def test_filters_to_visible_ids(self):
        beans = [
            _bean("bean-00000001", "A"),
            _bean("bean-00000002", "B"),
        ]
        g = build_dag(beans, [])
        positions = compute_layout(g, {"bean-00000001"})
        assert "bean-00000001" in positions
        assert "bean-00000002" not in positions

    def test_chain_layout_is_vertical(self):
        beans = [
            _bean("bean-00000001", "A"),
            _bean("bean-00000002", "B"),
            _bean("bean-00000003", "C"),
        ]
        deps = [
            _dep("bean-00000001", "bean-00000002"),
            _dep("bean-00000002", "bean-00000003"),
        ]
        g = build_dag(beans, deps)
        visible = {"bean-00000001", "bean-00000002", "bean-00000003"}
        positions = compute_layout(g, visible)
        # dot layout: nodes in a chain should have distinct y positions
        ys = [positions[nid][1] for nid in sorted(visible)]
        assert len(set(ys)) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_layout.py -v`
Expected: FAIL — `cannot import name 'build_dag'`

- [ ] **Step 3: Implement layout module**

`src/beans_stalk/graph/layout.py`:
```python
import networkx as nx
from beans.models import Bean, Dep


def build_dag(beans: list[Bean], deps: list[Dep]) -> nx.DiGraph:
    """Build a networkx DiGraph from beans and dependencies."""
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
    graph: nx.DiGraph,
    visible_ids: set[str],
) -> dict[str, tuple[float, float]]:
    """Compute node positions for visible nodes using graphviz dot layout."""
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
    """Translate new positions so the anchor node stays at its old location.

    If anchor_id is None or not in both position sets, returns new_positions unchanged.
    """
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_layout.py -v`
Expected: All PASS

- [ ] **Step 5: Add test for stabilize_layout**

Add to `tests/test_layout.py`:
```python
from beans_stalk.graph.layout import stabilize_layout


class TestStabilizeLayout:
    def test_anchors_selected_node(self):
        old = {"a": (100.0, 200.0), "b": (150.0, 250.0)}
        new = {"a": (50.0, 100.0), "b": (100.0, 150.0)}
        result = stabilize_layout(new, old, anchor_id="a")
        assert result["a"] == (100.0, 200.0)
        assert result["b"] == (150.0, 250.0)

    def test_no_anchor_returns_unchanged(self):
        new = {"a": (50.0, 100.0)}
        result = stabilize_layout(new, {}, anchor_id=None)
        assert result == new

    def test_missing_anchor_returns_unchanged(self):
        new = {"a": (50.0, 100.0)}
        old = {"b": (100.0, 200.0)}
        result = stabilize_layout(new, old, anchor_id="x")
        assert result == new
```

- [ ] **Step 6: Run all layout tests**

Run: `pytest tests/test_layout.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/beans_stalk/graph/layout.py tests/test_layout.py
git commit -m "feat: add graph layout module with DAG construction and position stabilization"
```

---

### Task 6: Single-Instance IPC

**Files:**
- Create: `src/beans_stalk/main.py`
- Create: `tests/test_ipc.py`

- [ ] **Step 1: Write failing tests for IPC**

`tests/test_ipc.py`:
```python
import socket
import threading
import time
from pathlib import Path

from beans_stalk.main import IpcServer, try_send_to_running_instance, SOCKET_PATH


class TestIpc:
    def test_try_send_fails_when_no_server(self, tmp_path, monkeypatch):
        sock_path = tmp_path / "test.sock"
        monkeypatch.setattr("beans_stalk.main.SOCKET_PATH", sock_path)
        result = try_send_to_running_instance("/some/path")
        assert result is False

    def test_server_receives_path(self, tmp_path, monkeypatch):
        sock_path = tmp_path / "test.sock"
        monkeypatch.setattr("beans_stalk.main.SOCKET_PATH", sock_path)

        received = []
        server = IpcServer(on_path=lambda p: received.append(p))
        server.start()
        time.sleep(0.1)

        result = try_send_to_running_instance("/some/beans/dir")
        assert result is True
        time.sleep(0.1)

        server.stop()
        assert received == ["/some/beans/dir"]

    def test_stale_socket_cleanup(self, tmp_path, monkeypatch):
        sock_path = tmp_path / "test.sock"
        monkeypatch.setattr("beans_stalk.main.SOCKET_PATH", sock_path)

        # Create a stale socket file
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(sock_path))
        sock.close()
        assert sock_path.exists()

        # try_send should fail (stale), then server should be able to bind
        result = try_send_to_running_instance("/path")
        assert result is False
        # Stale socket should be cleaned up
        assert not sock_path.exists()

    def test_server_stop_removes_socket(self, tmp_path, monkeypatch):
        sock_path = tmp_path / "test.sock"
        monkeypatch.setattr("beans_stalk.main.SOCKET_PATH", sock_path)

        server = IpcServer(on_path=lambda p: None)
        server.start()
        time.sleep(0.1)
        assert sock_path.exists()

        server.stop()
        assert not sock_path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ipc.py -v`
Expected: FAIL — `cannot import name 'IpcServer'`

- [ ] **Step 3: Implement IPC in main.py**

`src/beans_stalk/main.py`:
```python
import os
import socket
import threading
from pathlib import Path
from typing import Callable

import typer

SOCKET_PATH = Path.home() / ".beans-stalk.sock"

app = typer.Typer(add_completion=False)


def try_send_to_running_instance(beans_dir_path: str) -> bool:
    """Try to send a path to a running Beans Stalk instance.

    Returns True if message was sent, False if no instance is running.
    Cleans up stale socket files.
    """
    if not SOCKET_PATH.exists():
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(SOCKET_PATH))
        sock.sendall(beans_dir_path.encode("utf-8"))
        sock.close()
        return True
    except (ConnectionRefusedError, FileNotFoundError):
        # Stale socket — clean up
        try:
            SOCKET_PATH.unlink()
        except FileNotFoundError:
            pass
        return False
    finally:
        sock.close()


class IpcServer:
    """Unix domain socket server for receiving paths from new stalk invocations."""

    def __init__(self, on_path: Callable[[str], None]):
        self._on_path = on_path
        self._server_socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self):
        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            SOCKET_PATH.unlink()
        except FileNotFoundError:
            pass
        self._server_socket.bind(str(SOCKET_PATH))
        self._server_socket.listen(5)
        self._server_socket.settimeout(0.5)
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._server_socket is not None:
            self._server_socket.close()
            self._server_socket = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        try:
            SOCKET_PATH.unlink()
        except FileNotFoundError:
            pass

    def _accept_loop(self):
        while not self._stop_event.is_set():
            try:
                conn, _ = self._server_socket.accept()
                data = conn.recv(4096).decode("utf-8")
                conn.close()
                if data:
                    self._on_path(data)
            except socket.timeout:
                continue
            except OSError:
                break


@app.command()
def main(beans_dir: str = typer.Argument(None, help="Path to .beans directory or parent")):
    """Launch Beans Stalk DAG viewer."""
    from beans.workspace import find_beans_dir

    if beans_dir is None:
        resolved = str(find_beans_dir())
    else:
        p = Path(beans_dir)
        if p.is_dir() and (p / "beans.db").exists():
            resolved = str(p)
        elif p.name == "beans.db" and p.exists():
            resolved = str(p.parent)
        else:
            resolved = str(find_beans_dir(start=beans_dir))

    if try_send_to_running_instance(resolved):
        raise SystemExit(0)

    # Import Qt only when we need to launch
    from beans_stalk.app import run_app

    run_app(resolved)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ipc.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/main.py tests/test_ipc.py
git commit -m "feat: add CLI entry point with single-instance IPC via Unix domain socket"
```

---

### Task 7: Bean Node Widget

**Files:**
- Create: `src/beans_stalk/ui/bean_node.py`
- Create: `tests/test_bean_node.py`

- [ ] **Step 1: Write failing tests for bean node**

`tests/test_bean_node.py`:
```python
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

from beans.models import Bean, BeanId

from beans_stalk.ui.bean_node import BeanNode, NODE_WIDTH, NODE_HEIGHT


def _bean(title="Test", status="open", assignee=None, priority=2):
    return Bean(id=BeanId.generate(), title=title, status=status, assignee=assignee, priority=priority)


class TestBeanNode:
    def test_bounding_rect(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        rect = node.boundingRect()
        assert rect.width() == NODE_WIDTH
        assert rect.height() == NODE_HEIGHT

    def test_click_emits_signal(self, qtbot):
        bean = _bean()
        node = BeanNode(bean, "#e06c75")
        with qtbot.waitSignal(node.clicked, timeout=1000) as blocker:
            node.clicked.emit(bean.id)
        assert blocker.args == [bean.id]

    def test_muted_property(self, qapp):
        node = BeanNode(_bean(), "#e06c75", muted=False)
        assert not node.muted
        node.muted = True
        assert node.muted

    def test_set_color(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.set_color("#61afef")
        assert node._color == QColor("#61afef")

    def test_bean_property_update(self, qapp):
        bean = _bean(title="Original")
        node = BeanNode(bean, "#e06c75")
        assert node.bean.title == "Original"
        node.bean = _bean(title="Updated")
        assert node.bean.title == "Updated"

    def test_anim_pos_property(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.animPos = QPointF(100, 200)
        assert node.pos() == QPointF(100, 200)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bean_node.py -v`
Expected: FAIL — `cannot import name 'BeanNode'`

- [ ] **Step 3: Implement bean node**

`src/beans_stalk/ui/bean_node.py`:
```python
from PySide6.QtCore import QRectF, Qt, Signal, QPointF, Property
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics
from PySide6.QtWidgets import QGraphicsObject, QStyleOptionGraphicsItem, QWidget

from beans.models import Bean

NODE_WIDTH = 160
NODE_HEIGHT = 40
CORNER_RADIUS = 8
PRIORITY_RADIUS = 6


class BeanNode(QGraphicsObject):
    """Visual representation of a single bean in the DAG."""

    clicked = Signal(str)  # bean_id

    def __init__(self, bean: Bean, color: str, muted: bool = False, parent=None):
        super().__init__(parent)
        self._bean = bean
        self._color = QColor(color)
        self._muted = muted
        self._hovered = False
        self._pos_value = QPointF(0, 0)

        self.setAcceptHoverEvents(True)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setCacheMode(self.CacheMode.DeviceCoordinateCache)

    @property
    def bean(self) -> Bean:
        return self._bean

    @bean.setter
    def bean(self, value: Bean):
        self._bean = value
        self.update()

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool):
        self._muted = value
        self.update()

    def set_color(self, color: str):
        self._color = QColor(color)
        self.update()

    # Animatable position property
    def _get_anim_pos(self) -> QPointF:
        return self.pos()

    def _set_anim_pos(self, pos: QPointF):
        self.setPos(pos)

    animPos = Property(QPointF, _get_anim_pos, _set_anim_pos)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, NODE_WIDTH, NODE_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        fill_color = QColor(self._color)
        if self._muted:
            fill_color.setAlphaF(0.3)

        # Highlight on hover
        if self._hovered and not self._muted:
            fill_color = fill_color.lighter(120)

        # Draw rounded rect
        painter.setPen(QPen(fill_color.darker(130), 2))
        painter.setBrush(fill_color)
        painter.drawRoundedRect(
            QRectF(1, 1, NODE_WIDTH - 2, NODE_HEIGHT - 2),
            CORNER_RADIUS, CORNER_RADIUS,
        )

        # Selection indicator
        if self.isSelected():
            painter.setPen(QPen(Qt.GlobalColor.white, 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                QRectF(1, 1, NODE_WIDTH - 2, NODE_HEIGHT - 2),
                CORNER_RADIUS, CORNER_RADIUS,
            )

        # Title text
        text_color = Qt.GlobalColor.white if fill_color.lightnessF() < 0.5 else Qt.GlobalColor.black
        if self._muted:
            tc = QColor(text_color)
            tc.setAlphaF(0.5)
            text_color = tc
        painter.setPen(text_color)
        font = QFont("system-ui", 10)
        painter.setFont(font)
        text_rect = QRectF(8, 2, NODE_WIDTH - 24, NODE_HEIGHT - 4)
        elided = QFontMetrics(font).elidedText(
            self._bean.title, Qt.TextElideMode.ElideRight, int(text_rect.width())
        )
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, elided)

        # Priority indicator
        priority_colors = ["#ff4444", "#ff8800", "#ffcc00", "#88cc00", "#44aa44"]
        pc = QColor(priority_colors[self._bean.priority])
        if self._muted:
            pc.setAlphaF(0.3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(pc)
        painter.drawEllipse(
            QPointF(NODE_WIDTH - PRIORITY_RADIUS - 6, PRIORITY_RADIUS + 6),
            PRIORITY_RADIUS, PRIORITY_RADIUS,
        )

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.clicked.emit(self._bean.id)
        super().mousePressEvent(event)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bean_node.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/ui/bean_node.py tests/test_bean_node.py
git commit -m "feat: add BeanNode QGraphicsObject with assignee coloring and priority indicator"
```

---

### Task 8: Dependency Edge Widget

**Files:**
- Create: `src/beans_stalk/ui/dep_edge.py`
- Create: `tests/test_dep_edge.py`

- [ ] **Step 1: Write failing tests for dependency edge**

`tests/test_dep_edge.py`:
```python
from PySide6.QtCore import QPointF

from beans_stalk.ui.dep_edge import DepEdge


class TestDepEdge:
    def test_stores_ids(self, qapp):
        edge = DepEdge("bean-00000001", "bean-00000002")
        assert edge.from_id == "bean-00000001"
        assert edge.to_id == "bean-00000002"

    def test_update_path_creates_valid_path(self, qapp):
        edge = DepEdge("a", "b")
        edge.update_path(QPointF(0, 0), QPointF(0, 200))
        assert not edge.path().isEmpty()

    def test_shape_is_wider_than_path(self, qapp):
        edge = DepEdge("a", "b")
        edge.update_path(QPointF(0, 0), QPointF(0, 200))
        # Shape should be wider for click targets
        assert edge.shape().boundingRect().width() > edge.path().boundingRect().width()

    def test_z_value_is_negative(self, qapp):
        edge = DepEdge("a", "b")
        assert edge.zValue() < 0  # Behind nodes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dep_edge.py -v`
Expected: FAIL — `cannot import name 'DepEdge'`

- [ ] **Step 3: Implement dependency edge**

`src/beans_stalk/ui/dep_edge.py`:
```python
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPainterPathStroker, QPen, QColor, QPolygonF
from PySide6.QtWidgets import QGraphicsPathItem

from beans_stalk.ui.bean_node import NODE_WIDTH, NODE_HEIGHT

ARROW_SIZE = 8
EDGE_COLOR = "#aaaaaa"
EDGE_HOVER_COLOR = "#ffffff"


class DepEdge(QGraphicsPathItem):
    """Visual representation of a dependency edge between two bean nodes."""

    def __init__(self, from_id: str, to_id: str, parent=None):
        super().__init__(parent)
        self.from_id = from_id
        self.to_id = to_id
        self._hovered = False

        self.setPen(QPen(QColor(EDGE_COLOR), 1.5))
        self.setAcceptHoverEvents(True)
        self.setZValue(-1)  # Draw behind nodes

    def update_path(self, from_pos: QPointF, to_pos: QPointF):
        """Recompute the bezier path between two node positions.

        Positions are the top-left corners of the nodes. Edge goes from
        bottom-center of source to top-center of target.
        """
        start = QPointF(
            from_pos.x() + NODE_WIDTH / 2,
            from_pos.y() + NODE_HEIGHT,
        )
        end = QPointF(
            to_pos.x() + NODE_WIDTH / 2,
            to_pos.y(),
        )

        # Control points for cubic bezier
        dy = abs(end.y() - start.y()) / 2
        ctrl1 = QPointF(start.x(), start.y() + dy)
        ctrl2 = QPointF(end.x(), end.y() - dy)

        path = QPainterPath(start)
        path.cubicTo(ctrl1, ctrl2, end)
        self.setPath(path)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(EDGE_HOVER_COLOR if self._hovered else EDGE_COLOR)
        width = 2.5 if self._hovered else 1.5
        painter.setPen(QPen(color, width))
        painter.drawPath(self.path())

        # Draw arrowhead at the end
        path = self.path()
        if path.elementCount() < 2:
            return
        end = QPointF(path.elementAt(path.elementCount() - 1).x,
                       path.elementAt(path.elementCount() - 1).y)
        # Get direction from second-to-last control point
        prev = QPointF(path.elementAt(path.elementCount() - 2).x,
                        path.elementAt(path.elementCount() - 2).y)
        dx = end.x() - prev.x()
        dy = end.y() - prev.y()
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return
        dx /= length
        dy /= length

        # Arrow points
        p1 = QPointF(
            end.x() - ARROW_SIZE * dx + ARROW_SIZE * 0.5 * dy,
            end.y() - ARROW_SIZE * dy - ARROW_SIZE * 0.5 * dx,
        )
        p2 = QPointF(
            end.x() - ARROW_SIZE * dx - ARROW_SIZE * 0.5 * dy,
            end.y() - ARROW_SIZE * dy + ARROW_SIZE * 0.5 * dx,
        )
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygonF([end, p1, p2]))

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()

    def shape(self):
        """Wider hit area for easier clicking."""
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self.path())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dep_edge.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/ui/dep_edge.py tests/test_dep_edge.py
git commit -m "feat: add DepEdge with bezier curves and arrowheads"
```

---

### Task 9: DAG Scene

**Files:**
- Create: `src/beans_stalk/ui/dag_scene.py`
- Create: `tests/test_dag_scene.py`

- [ ] **Step 1: Write failing tests for DAG scene**

`tests/test_dag_scene.py`:
```python
from datetime import datetime, timezone, timedelta

from beans.models import Bean, BeanId, Dep
from beans import api

from beans_stalk.config import StalkConfig
from beans_stalk.ui.dag_scene import DagScene


def _bean(id_="bean-00000001", title="Test", status="open", assignee=None, closed_at=None):
    return Bean(id=BeanId(id_), title=title, status=status, assignee=assignee, closed_at=closed_at)


def _dep(from_id, to_id):
    return Dep(from_id=BeanId(from_id), to_id=BeanId(to_id))


class TestDagScene:
    def test_empty_shows_placeholder(self, qapp):
        scene = DagScene(StalkConfig())
        scene.update_snapshot([], [])
        assert scene._placeholder is not None
        assert len(scene._nodes) == 0

    def test_beans_create_nodes(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B")]
        scene.update_snapshot(beans, [])
        assert len(scene._nodes) == 2
        assert scene._placeholder is None

    def test_deps_create_edges(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B")]
        deps = [_dep("bean-00000001", "bean-00000002")]
        scene.update_snapshot(beans, deps)
        assert len(scene._edges) == 1

    def test_closed_beans_hidden_by_default(self, qapp):
        scene = DagScene(StalkConfig(fade_minutes=0))
        beans = [
            _bean("bean-00000001", "Open"),
            _bean("bean-00000002", "Closed", status="closed",
                  closed_at=datetime.now(timezone.utc) - timedelta(hours=1)),
        ]
        scene.update_snapshot(beans, [])
        assert "bean-00000001" in scene._nodes
        assert "bean-00000002" not in scene._nodes

    def test_recently_closed_shown_muted(self, qapp):
        scene = DagScene(StalkConfig(fade_minutes=10))
        beans = [
            _bean("bean-00000001", "Just closed", status="closed",
                  closed_at=datetime.now(timezone.utc) - timedelta(minutes=1)),
        ]
        scene.update_snapshot(beans, [])
        assert "bean-00000001" in scene._nodes
        assert scene._nodes["bean-00000001"].muted is True

    def test_show_completed_reveals_all(self, qapp):
        scene = DagScene(StalkConfig(fade_minutes=0))
        scene.show_completed = True
        beans = [
            _bean("bean-00000001", "Closed", status="closed",
                  closed_at=datetime.now(timezone.utc) - timedelta(hours=1)),
        ]
        scene.update_snapshot(beans, [])
        assert "bean-00000001" in scene._nodes

    def test_removed_beans_cleaned_up(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-00000001", "A"), _bean("bean-00000002", "B")]
        scene.update_snapshot(beans, [])
        assert len(scene._nodes) == 2

        scene.update_snapshot([_bean("bean-00000001", "A")], [])
        assert len(scene._nodes) == 1
        assert "bean-00000002" not in scene._nodes

    def test_node_clicked_emits_signal(self, qtbot):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-00000001", "A")]
        scene.update_snapshot(beans, [])

        with qtbot.waitSignal(scene.node_clicked, timeout=1000):
            scene._on_node_clicked("bean-00000001")

    def test_selected_id_updates_selection(self, qapp):
        scene = DagScene(StalkConfig())
        beans = [_bean("bean-00000001", "A")]
        scene.update_snapshot(beans, [])

        scene.selected_id = "bean-00000001"
        assert scene._nodes["bean-00000001"].isSelected()

        scene.selected_id = None
        assert not scene._nodes["bean-00000001"].isSelected()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dag_scene.py -v`
Expected: FAIL — `cannot import name 'DagScene'`

- [ ] **Step 3: Implement DAG scene**

`src/beans_stalk/ui/dag_scene.py`:
```python
from datetime import datetime, timezone

from PySide6.QtCore import QPointF, QEasingCurve, QPropertyAnimation, Signal
from PySide6.QtWidgets import QGraphicsScene, QGraphicsTextItem
from PySide6.QtGui import QColor, QFont

from beans.models import Bean, Dep
from beans_stalk.ui.bean_node import BeanNode
from beans_stalk.ui.dep_edge import DepEdge
from beans_stalk.config import StalkConfig
from beans_stalk.graph.layout import build_dag, compute_layout, stabilize_layout

ANIMATION_DURATION_MS = 300


class DagScene(QGraphicsScene):
    """Manages bean nodes and dependency edges with animated layout updates."""

    node_clicked = Signal(str)  # bean_id
    dep_toggle_requested = Signal(str, str)  # from_id, to_id
    dep_remove_requested = Signal(str, str)  # from_id, to_id

    def __init__(self, config: StalkConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._nodes: dict[str, BeanNode] = {}
        self._edges: dict[tuple[str, str], DepEdge] = {}
        self._positions: dict[str, tuple[float, float]] = {}
        self._selected_id: str | None = None
        self._show_completed = False
        self._fade_minutes = config.fade_minutes
        self._placeholder: QGraphicsTextItem | None = None

    @property
    def selected_id(self) -> str | None:
        return self._selected_id

    @selected_id.setter
    def selected_id(self, value: str | None):
        # Deselect old
        if self._selected_id and self._selected_id in self._nodes:
            self._nodes[self._selected_id].setSelected(False)
        self._selected_id = value
        # Select new
        if value and value in self._nodes:
            self._nodes[value].setSelected(True)

    @property
    def show_completed(self) -> bool:
        return self._show_completed

    @show_completed.setter
    def show_completed(self, value: bool):
        self._show_completed = value

    def update_snapshot(self, beans: list[Bean], deps: list[Dep]):
        """Update the scene with new data. Recomputes layout and animates."""
        now = datetime.now(timezone.utc)

        # Determine which beans are visible
        visible_beans = {}
        for bean in beans:
            if bean.status == "closed":
                if self._show_completed:
                    visible_beans[bean.id] = (bean, True)
                elif bean.closed_at and self._is_recently_closed(bean.closed_at, now):
                    visible_beans[bean.id] = (bean, True)
                # else: hidden
            else:
                visible_beans[bean.id] = (bean, False)

        # Build DAG and compute layout
        graph = build_dag(beans, deps)
        visible_ids = set(visible_beans.keys())
        new_positions = compute_layout(graph, visible_ids)
        new_positions = stabilize_layout(new_positions, self._positions, self._selected_id)

        # Show/hide placeholder
        if not visible_beans:
            self._show_placeholder()
        else:
            self._hide_placeholder()

        # Remove nodes no longer visible
        for bean_id in list(self._nodes.keys()):
            if bean_id not in visible_beans:
                self.removeItem(self._nodes.pop(bean_id))

        # Add or update nodes
        for bean_id, (bean, muted) in visible_beans.items():
            color = self._config.get_color(bean.assignee)
            if bean_id in self._nodes:
                node = self._nodes[bean_id]
                node.bean = bean
                node.muted = muted
                node.set_color(color)
            else:
                node = BeanNode(bean, color, muted=muted)
                node.clicked.connect(self._on_node_clicked)
                self._nodes[bean_id] = node
                self.addItem(node)

            # Animate to new position
            if bean_id in new_positions:
                target = QPointF(*new_positions[bean_id])
                if bean_id in self._positions:
                    anim = QPropertyAnimation(node, b"animPos")
                    anim.setDuration(ANIMATION_DURATION_MS)
                    anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
                    anim.setStartValue(node.pos())
                    anim.setEndValue(target)
                    anim.start()
                    # Keep reference so animation isn't garbage collected
                    node._current_anim = anim
                else:
                    node.setPos(target)

        # Remove edges no longer present
        current_dep_keys = set()
        for dep in deps:
            if dep.from_id in visible_beans and dep.to_id in visible_beans:
                current_dep_keys.add((dep.from_id, dep.to_id))

        for key in list(self._edges.keys()):
            if key not in current_dep_keys:
                self.removeItem(self._edges.pop(key))

        # Add or update edges
        for dep in deps:
            key = (dep.from_id, dep.to_id)
            if key not in current_dep_keys:
                continue
            if key not in self._edges:
                edge = DepEdge(dep.from_id, dep.to_id)
                self._edges[key] = edge
                self.addItem(edge)

            edge = self._edges[key]
            if dep.from_id in new_positions and dep.to_id in new_positions:
                edge.update_path(
                    QPointF(*new_positions[dep.from_id]),
                    QPointF(*new_positions[dep.to_id]),
                )

        self._positions = new_positions

    def _is_recently_closed(self, closed_at: datetime, now: datetime) -> bool:
        elapsed = (now - closed_at).total_seconds() / 60
        return elapsed < self._fade_minutes

    def _on_node_clicked(self, bean_id: str):
        self.selected_id = bean_id
        self.node_clicked.emit(bean_id)

    def _show_placeholder(self):
        if self._placeholder is not None:
            return
        self._placeholder = QGraphicsTextItem("No beans yet — create one with Cmd-N or right-click")
        self._placeholder.setDefaultTextColor(QColor("#888888"))
        self._placeholder.setFont(QFont("system-ui", 14))
        self.addItem(self._placeholder)

    def _hide_placeholder(self):
        if self._placeholder is not None:
            self.removeItem(self._placeholder)
            self._placeholder = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dag_scene.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/ui/dag_scene.py tests/test_dag_scene.py
git commit -m "feat: add DagScene with animated layout updates and completed-bean fading"
```

---

### Task 10: DAG View (Interaction Handler)

**Files:**
- Create: `src/beans_stalk/ui/dag_view.py`
- Create: `tests/test_dag_view.py`

- [ ] **Step 1: Write failing tests for DAG view**

`tests/test_dag_view.py`:
```python
from PySide6.QtCore import Qt

from beans_stalk.config import StalkConfig
from beans_stalk.ui.dag_scene import DagScene
from beans_stalk.ui.dag_view import DagView


class TestDagView:
    def test_creates_with_scene(self, qapp):
        scene = DagScene(StalkConfig())
        view = DagView(scene)
        assert view.scene() is scene

    def test_scroll_bars_hidden(self, qapp):
        scene = DagScene(StalkConfig())
        view = DagView(scene)
        assert view.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert view.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    def test_escape_deselects(self, qtbot):
        scene = DagScene(StalkConfig())
        view = DagView(scene)
        qtbot.addWidget(view)
        scene.selected_id = "some-id"  # won't find node, but tests the path
        qtbot.keyPress(view, Qt.Key.Key_Escape)
        assert scene.selected_id is None

    def test_signals_exist(self, qapp):
        scene = DagScene(StalkConfig())
        view = DagView(scene)
        # Verify signals are defined (doesn't test emission)
        assert hasattr(view, "new_bean_requested")
        assert hasattr(view, "new_child_requested")
        assert hasattr(view, "new_blocker_requested")
        assert hasattr(view, "new_blocked_by_requested")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dag_view.py -v`
Expected: FAIL — `cannot import name 'DagView'`

- [ ] **Step 3: Implement DAG view**

`src/beans_stalk/ui/dag_view.py`:
```python
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsView, QMenu

from beans_stalk.ui.dag_scene import DagScene
from beans_stalk.ui.bean_node import BeanNode
from beans_stalk.ui.dep_edge import DepEdge

MIN_ZOOM = 0.1
MAX_ZOOM = 10.0
ZOOM_FACTOR = 1.15


class DagView(QGraphicsView):
    """Interactive DAG viewer with pan, zoom, and shift-drag dependency editing."""

    new_bean_requested = Signal()  # no args = standalone
    new_child_requested = Signal(str)  # parent bean_id
    new_blocker_requested = Signal(str)  # blocked bean_id
    new_blocked_by_requested = Signal(str)  # blocker bean_id

    def __init__(self, scene: DagScene, parent=None):
        super().__init__(scene, parent)
        self._dag_scene = scene
        self._panning = False
        self._pan_start = QPointF()
        self._shift_dragging = False
        self._shift_drag_source: BeanNode | None = None

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grabGesture(Qt.GestureType.PinchGesture)

    def wheelEvent(self, event):
        factor = ZOOM_FACTOR if event.angleDelta().y() > 0 else 1 / ZOOM_FACTOR
        current = self.transform().m11()
        if MIN_ZOOM < current * factor < MAX_ZOOM:
            self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Start shift-drag for dependency editing
                item = self.itemAt(event.pos())
                if isinstance(item, BeanNode):
                    self._shift_dragging = True
                    self._shift_drag_source = item
                    event.accept()
                    return
                elif isinstance(item, DepEdge):
                    # Shift-click on edge = remove dependency
                    self._dag_scene.dep_remove_requested.emit(item.from_id, item.to_id)
                    event.accept()
                    return
            else:
                # Check if clicking on empty space (deselect)
                item = self.itemAt(event.pos())
                if item is None:
                    self._dag_scene.selected_id = None
                    # Start panning
                    self._panning = True
                    self._pan_start = event.position()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._panning:
                self._panning = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
                event.accept()
                return
            if self._shift_dragging and self._shift_drag_source is not None:
                self._shift_dragging = False
                # Find target node under cursor
                item = self.itemAt(event.pos())
                if isinstance(item, BeanNode) and item is not self._shift_drag_source:
                    self._dag_scene.dep_toggle_requested.emit(
                        self._shift_drag_source.bean.id, item.bean.id
                    )
                self._shift_drag_source = None
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._dag_scene.selected_id = None
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        menu = QMenu(self)
        if isinstance(item, BeanNode):
            bean_id = item.bean.id
            menu.addAction("New child bean", lambda: self.new_child_requested.emit(bean_id))
            menu.addAction("New bean blocked by this", lambda: self.new_blocker_requested.emit(bean_id))
            menu.addAction("New bean that blocks this", lambda: self.new_blocked_by_requested.emit(bean_id))
        else:
            menu.addAction("New bean", lambda: self.new_bean_requested.emit())
        menu.exec(event.globalPos())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dag_view.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/ui/dag_view.py tests/test_dag_view.py
git commit -m "feat: add DagView with pan, zoom, shift-drag deps, and context menus"
```

---

### Task 11: Sidebar Bean Editor

**Files:**
- Create: `src/beans_stalk/ui/sidebar.py`
- Create: `tests/test_sidebar.py`

- [ ] **Step 1: Write failing tests for sidebar**

`tests/test_sidebar.py`:
```python
from PySide6.QtCore import Qt

from beans.models import Bean, BeanId, Dep

from beans_stalk.config import StalkConfig
from beans_stalk.ui.sidebar import Sidebar


def _bean(title="Test", status="open", assignee=None, priority=2, body=""):
    return Bean(id=BeanId.generate(), title=title, status=status,
                assignee=assignee, priority=priority, body=body)


class TestSidebar:
    def test_show_bean_populates_fields(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        bean = _bean(title="My Task", priority=1, assignee="alice", body="Description")
        sidebar.show_bean(bean, [])

        assert sidebar._title_edit.text() == "My Task"
        assert sidebar._priority_spin.value() == 1
        assert sidebar._assignee_edit.text() == "alice"
        assert sidebar._body_edit.toPlainText() == "Description"

    def test_new_bean_mode_clears_fields(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        sidebar.show_bean(_bean(title="Existing"), [])
        sidebar.start_new_bean()

        assert sidebar._title_edit.text() == ""
        assert sidebar._priority_spin.value() == 2
        assert sidebar._save_btn.text() == "Create"
        assert sidebar._creating is True

    def test_new_bean_with_prefill(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        sidebar.start_new_bean({"parent_id": "bean-00000001"})
        assert sidebar._parent_edit.text() == "bean-00000001"

    def test_save_emits_signal_for_existing(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        bean = _bean(title="Original")
        sidebar.show_bean(bean, [])
        sidebar._title_edit.setText("Updated")

        with qtbot.waitSignal(sidebar.save_requested, timeout=1000) as blocker:
            sidebar._save_btn.click()
        assert blocker.args[0] == bean.id
        assert blocker.args[1]["title"] == "Updated"

    def test_create_emits_signal_for_new(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        sidebar.start_new_bean()
        sidebar._title_edit.setText("New Task")

        with qtbot.waitSignal(sidebar.create_bean_requested, timeout=1000) as blocker:
            sidebar._save_btn.click()
        assert blocker.args[0]["title"] == "New Task"

    def test_deps_displayed(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        bean = _bean()
        deps = [
            Dep(from_id=bean.id, to_id=BeanId("bean-00000002")),
            Dep(from_id=BeanId("bean-00000003"), to_id=bean.id),
        ]
        sidebar.show_bean(bean, deps)
        assert sidebar._blocks_list.count() == 1
        assert sidebar._blocked_by_list.count() == 1

    def test_status_message(self, qtbot):
        sidebar = Sidebar(StalkConfig())
        qtbot.addWidget(sidebar)
        sidebar.show_status("Something went wrong")
        assert sidebar._status_label.isVisible()
        assert sidebar._status_label.text() == "Something went wrong"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sidebar.py -v`
Expected: FAIL — `cannot import name 'Sidebar'`

- [ ] **Step 3: Implement sidebar**

`src/beans_stalk/ui/sidebar.py`:
```python
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QComboBox, QSpinBox, QPushButton, QColorDialog,
    QListWidget, QListWidgetItem, QMessageBox, QGroupBox, QScrollArea,
)

from beans.models import Bean, Dep
from beans_stalk.config import StalkConfig


class Sidebar(QWidget):
    """Bean property editor panel."""

    save_requested = Signal(str, dict)  # bean_id, fields
    close_bean_requested = Signal(str, str)  # bean_id, reason
    create_bean_requested = Signal(dict)  # fields
    add_dep_requested = Signal(str, str)  # from_id, to_id
    remove_dep_requested = Signal(str, str)  # from_id, to_id
    color_changed = Signal(str, str)  # assignee, new_color

    def __init__(self, config: StalkConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._current_bean: Bean | None = None
        self._current_deps: list[Dep] = []
        self._creating = False
        self._pre_filled: dict = {}
        self._setup_ui()

    def _setup_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)

        # Status message
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #e06c75; font-size: 11px;")
        self._status_label.setWordWrap(True)
        self._status_label.hide()
        layout.addWidget(self._status_label)

        # Title
        layout.addWidget(QLabel("Title"))
        self._title_edit = QLineEdit()
        layout.addWidget(self._title_edit)

        # Type
        layout.addWidget(QLabel("Type"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["task", "bug", "epic", "project"])
        layout.addWidget(self._type_combo)

        # Status
        layout.addWidget(QLabel("Status"))
        self._status_combo = QComboBox()
        self._status_combo.addItems(["open", "in_progress", "closed"])
        layout.addWidget(self._status_combo)

        # Priority
        layout.addWidget(QLabel("Priority"))
        self._priority_spin = QSpinBox()
        self._priority_spin.setRange(0, 4)
        layout.addWidget(self._priority_spin)

        # Assignee
        layout.addWidget(QLabel("Assignee"))
        assignee_row = QHBoxLayout()
        self._assignee_edit = QLineEdit()
        assignee_row.addWidget(self._assignee_edit)
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(24, 24)
        self._color_btn.clicked.connect(self._pick_color)
        assignee_row.addWidget(self._color_btn)
        layout.addLayout(assignee_row)

        # Parent
        layout.addWidget(QLabel("Parent ID"))
        self._parent_edit = QLineEdit()
        self._parent_edit.setPlaceholderText("bean-XXXXXXXX")
        layout.addWidget(self._parent_edit)

        # Ref ID
        layout.addWidget(QLabel("Ref ID"))
        self._ref_edit = QLineEdit()
        self._ref_edit.setPlaceholderText("e.g. GH-42")
        layout.addWidget(self._ref_edit)

        # Body
        layout.addWidget(QLabel("Body"))
        self._body_edit = QTextEdit()
        self._body_edit.setMaximumHeight(120)
        layout.addWidget(self._body_edit)

        # Dependencies
        deps_group = QGroupBox("Dependencies")
        deps_layout = QVBoxLayout()

        deps_layout.addWidget(QLabel("Blocks:"))
        self._blocks_list = QListWidget()
        self._blocks_list.setMaximumHeight(80)
        deps_layout.addWidget(self._blocks_list)

        deps_layout.addWidget(QLabel("Blocked by:"))
        self._blocked_by_list = QListWidget()
        self._blocked_by_list.setMaximumHeight(80)
        deps_layout.addWidget(self._blocked_by_list)

        dep_btn_row = QHBoxLayout()
        self._add_dep_btn = QPushButton("Add dep...")
        self._add_dep_btn.clicked.connect(self._add_dep_dialog)
        dep_btn_row.addWidget(self._add_dep_btn)
        self._rm_dep_btn = QPushButton("Remove selected")
        self._rm_dep_btn.clicked.connect(self._remove_selected_dep)
        dep_btn_row.addWidget(self._rm_dep_btn)
        deps_layout.addLayout(dep_btn_row)

        deps_group.setLayout(deps_layout)
        layout.addWidget(deps_group)

        # Action buttons
        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        self._close_btn = QPushButton("Close Bean")
        self._close_btn.clicked.connect(self._on_close_bean)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

        # Close reason
        self._close_reason_edit = QLineEdit()
        self._close_reason_edit.setPlaceholderText("Close reason (optional)")
        self._close_reason_edit.hide()
        layout.addWidget(self._close_reason_edit)

        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def show_bean(self, bean: Bean, deps: list[Dep]):
        """Populate the editor with a bean's data."""
        self._creating = False
        self._current_bean = bean
        self._current_deps = deps
        self._status_label.hide()
        self._close_reason_edit.hide()

        self._title_edit.setText(bean.title)
        self._type_combo.setCurrentText(bean.type)
        self._status_combo.setCurrentText(bean.status)
        self._priority_spin.setValue(bean.priority)
        self._assignee_edit.setText(bean.assignee or "")
        self._parent_edit.setText(bean.parent_id or "")
        self._ref_edit.setText(bean.ref_id or "")
        self._body_edit.setPlainText(bean.body)

        # Update color button
        color = self._config.get_color(bean.assignee)
        self._color_btn.setStyleSheet(f"background-color: {color}; border: 1px solid #555;")

        # Deps
        self._blocks_list.clear()
        self._blocked_by_list.clear()
        for dep in deps:
            if dep.from_id == bean.id:
                self._blocks_list.addItem(QListWidgetItem(dep.to_id))
            elif dep.to_id == bean.id:
                self._blocked_by_list.addItem(QListWidgetItem(dep.from_id))

        self._save_btn.setText("Save")
        self._close_btn.show()

    def start_new_bean(self, pre_filled: dict | None = None):
        """Switch to new-bean creation mode."""
        self._creating = True
        self._current_bean = None
        self._pre_filled = pre_filled or {}
        self._status_label.hide()
        self._close_reason_edit.hide()

        self._title_edit.setText("")
        self._type_combo.setCurrentText("task")
        self._status_combo.setCurrentText("open")
        self._priority_spin.setValue(2)
        self._assignee_edit.setText("")
        self._parent_edit.setText(self._pre_filled.get("parent_id", ""))
        self._ref_edit.setText("")
        self._body_edit.setPlainText("")
        self._blocks_list.clear()
        self._blocked_by_list.clear()

        self._save_btn.setText("Create")
        self._close_btn.hide()
        self._title_edit.setFocus()

    def show_status(self, message: str):
        self._status_label.setText(message)
        self._status_label.show()

    def _on_save(self):
        fields = {
            "title": self._title_edit.text(),
            "type": self._type_combo.currentText(),
            "status": self._status_combo.currentText(),
            "priority": self._priority_spin.value(),
            "body": self._body_edit.toPlainText(),
        }
        assignee = self._assignee_edit.text().strip()
        if assignee:
            fields["assignee"] = assignee
        parent = self._parent_edit.text().strip()
        if parent:
            fields["parent_id"] = parent
        ref = self._ref_edit.text().strip()
        if ref:
            fields["ref_id"] = ref

        if self._creating:
            fields.update(self._pre_filled)
            self.create_bean_requested.emit(fields)
        else:
            self.save_requested.emit(self._current_bean.id, fields)

    def _on_close_bean(self):
        if self._close_reason_edit.isHidden():
            self._close_reason_edit.show()
            self._close_reason_edit.setFocus()
            return
        reason = self._close_reason_edit.text().strip()
        self.close_bean_requested.emit(self._current_bean.id, reason)

    def _pick_color(self):
        assignee = self._assignee_edit.text().strip()
        if not assignee:
            return
        current = QColor(self._config.get_color(assignee))
        color = QColorDialog.getColor(current, self, "Pick assignee color")
        if color.isValid():
            hex_color = color.name()
            self._color_btn.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #555;")
            self.color_changed.emit(assignee, hex_color)

    def _add_dep_dialog(self):
        if self._current_bean is None and not self._creating:
            return
        from PySide6.QtWidgets import QInputDialog
        bean_id = self._current_bean.id if self._current_bean else None
        target_id, ok = QInputDialog.getText(self, "Add dependency", "Bean ID that blocks this bean:")
        if ok and target_id.strip():
            target_id = target_id.strip()
            if bean_id:
                self.add_dep_requested.emit(target_id, bean_id)

    def _remove_selected_dep(self):
        if self._current_bean is None:
            return
        bean_id = self._current_bean.id
        # Check blocks list
        item = self._blocks_list.currentItem()
        if item:
            self.remove_dep_requested.emit(bean_id, item.text())
            return
        # Check blocked_by list
        item = self._blocked_by_list.currentItem()
        if item:
            self.remove_dep_requested.emit(item.text(), bean_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sidebar.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/ui/sidebar.py tests/test_sidebar.py
git commit -m "feat: add sidebar bean editor with dependency management and color picker"
```

---

### Task 12: Main Window

**Files:**
- Create: `src/beans_stalk/ui/main_window.py`
- Create: `tests/test_main_window.py`

- [ ] **Step 1: Write failing tests for main window**

`tests/test_main_window.py`:
```python
from PySide6.QtCore import Qt

from beans import api

from beans_stalk.ui.main_window import MainWindow


class TestMainWindow:
    def test_creates_with_beans_dir(self, tmp_beans_dir, qtbot):
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        assert "Beans Stalk" in win.windowTitle()
        win.close()

    def test_splitter_has_two_widgets(self, tmp_beans_dir, qtbot):
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        splitter = win.centralWidget()
        assert splitter.count() == 2
        win.close()

    def test_menu_bar_has_expected_menus(self, tmp_beans_dir, qtbot):
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        menu_titles = [a.text() for a in win.menuBar().actions()]
        assert "File" in menu_titles
        assert "Edit" in menu_titles
        assert "View" in menu_titles
        win.close()

    def test_stay_on_top_toggle(self, tmp_beans_dir, qtbot):
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        win.show()
        assert not (win.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        win._toggle_on_top_action.trigger()
        assert win.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        win._toggle_on_top_action.trigger()
        assert not (win.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        win.close()

    def test_node_selection_updates_sidebar(self, tmp_beans_dir, store, qtbot):
        a = api.create_bean(store, "Task A")
        store.close()

        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        win.show()

        # Wait for watcher to deliver initial snapshot
        qtbot.waitUntil(lambda: len(win._beans) > 0, timeout=2000)

        win._on_node_selected(a.id)
        assert win._sidebar._title_edit.text() == "Task A"
        win.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main_window.py -v`
Expected: FAIL — `cannot import name 'MainWindow'`

- [ ] **Step 3: Implement main window**

`src/beans_stalk/ui/main_window.py`:
```python
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox,
)

from beans.models import Bean, Dep
from beans_stalk.config import StalkConfig
from beans_stalk.data.store import StalkStore
from beans_stalk.data.watcher import DataWatcher
from beans_stalk.ui.dag_scene import DagScene
from beans_stalk.ui.dag_view import DagView
from beans_stalk.ui.sidebar import Sidebar


class MainWindow(QMainWindow):
    """Main application window for a single beans directory."""

    def __init__(self, beans_dir: Path, on_open_dir=None, parent=None):
        super().__init__(parent)
        self._beans_dir = beans_dir
        self._on_open_dir = on_open_dir
        self._db_path = beans_dir / "beans.db"

        # Load config
        self._config = StalkConfig.load(beans_dir)

        # Data layer
        self._store = StalkStore(self._db_path)
        self._watcher = DataWatcher(
            db_path=self._db_path,
            poll_interval_seconds=self._config.poll_interval_seconds,
            parent=self,
        )
        self._watcher.snapshot_changed.connect(self._on_snapshot_changed)

        # Current state
        self._beans: list[Bean] = []
        self._deps: list[Dep] = []

        self._setup_ui()
        self._setup_menus()
        self._watcher.start()

        self.setWindowTitle(f"Beans Stalk — {beans_dir}")
        self.resize(1200, 700)

    def _setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._scene = DagScene(self._config)
        self._view = DagView(self._scene)
        splitter.addWidget(self._view)

        self._sidebar = Sidebar(self._config)
        splitter.addWidget(self._sidebar)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([900, 300])

        self.setCentralWidget(splitter)

        # Connect signals
        self._scene.node_clicked.connect(self._on_node_selected)
        self._scene.dep_toggle_requested.connect(self._on_dep_toggle)
        self._scene.dep_remove_requested.connect(self._on_dep_remove)
        self._sidebar.save_requested.connect(self._on_save_bean)
        self._sidebar.close_bean_requested.connect(self._on_close_bean)
        self._sidebar.create_bean_requested.connect(self._on_create_bean)
        self._sidebar.add_dep_requested.connect(self._on_add_dep)
        self._sidebar.remove_dep_requested.connect(self._on_dep_remove)
        self._sidebar.color_changed.connect(self._on_color_changed)
        self._view.new_bean_requested.connect(lambda: self._sidebar.start_new_bean())
        self._view.new_child_requested.connect(
            lambda pid: self._sidebar.start_new_bean({"parent_id": pid})
        )
        self._view.new_blocker_requested.connect(
            lambda bid: self._sidebar.start_new_bean({"_add_blocks": bid})
        )
        self._view.new_blocked_by_requested.connect(
            lambda bid: self._sidebar.start_new_bean({"_add_blocked_by": bid})
        )

    def _setup_menus(self):
        # File menu
        file_menu = self.menuBar().addMenu("File")
        open_action = QAction("Open beans dir...", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        close_action = QAction("Close window", self)
        close_action.setShortcut(QKeySequence("Ctrl+W"))
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        # Edit menu
        edit_menu = self.menuBar().addMenu("Edit")
        new_bean_action = QAction("New bean", self)
        new_bean_action.setShortcut(QKeySequence("Ctrl+N"))
        new_bean_action.triggered.connect(lambda: self._sidebar.start_new_bean())
        edit_menu.addAction(new_bean_action)

        # View menu
        view_menu = self.menuBar().addMenu("View")
        self._toggle_completed_action = QAction("Show completed beans", self)
        self._toggle_completed_action.setCheckable(True)
        self._toggle_completed_action.triggered.connect(self._on_toggle_completed)
        view_menu.addAction(self._toggle_completed_action)

        self._toggle_on_top_action = QAction("Always on top", self)
        self._toggle_on_top_action.setCheckable(True)
        self._toggle_on_top_action.setShortcut(QKeySequence("Ctrl+T"))
        self._toggle_on_top_action.triggered.connect(self._on_toggle_on_top)
        view_menu.addAction(self._toggle_on_top_action)

    @Slot(list, list)
    def _on_snapshot_changed(self, beans: list[Bean], deps: list[Dep]):
        self._beans = beans
        self._deps = deps
        self._scene.update_snapshot(beans, deps)

        # Refresh sidebar if selected bean is still present
        if self._scene.selected_id:
            bean = next((b for b in beans if b.id == self._scene.selected_id), None)
            if bean:
                self._sidebar.show_bean(bean, deps)

    @Slot(str)
    def _on_node_selected(self, bean_id: str):
        bean = next((b for b in self._beans if b.id == bean_id), None)
        if bean:
            self._sidebar.show_bean(bean, self._deps)

    @Slot(str, str)
    def _on_dep_toggle(self, from_id: str, to_id: str):
        # Check if dep exists
        existing = any(
            d.from_id == from_id and d.to_id == to_id and d.dep_type == "blocks"
            for d in self._deps
        )
        try:
            if existing:
                self._store.remove_dep(from_id, to_id)
            else:
                self._store.add_dep(from_id, to_id)
        except Exception as e:
            self._sidebar.show_status(str(e))

    @Slot(str, str)
    def _on_dep_remove(self, from_id: str, to_id: str):
        try:
            self._store.remove_dep(from_id, to_id)
        except Exception as e:
            self._sidebar.show_status(str(e))

    @Slot(str, dict)
    def _on_save_bean(self, bean_id: str, fields: dict):
        try:
            self._store.update_bean(bean_id, **fields)
        except Exception as e:
            self._sidebar.show_status(str(e))

    @Slot(str, str)
    def _on_close_bean(self, bean_id: str, reason: str):
        try:
            self._store.close_bean(bean_id, reason=reason or None)
        except Exception as e:
            self._sidebar.show_status(str(e))

    @Slot(dict)
    def _on_create_bean(self, fields: dict):
        add_blocks = fields.pop("_add_blocks", None)
        add_blocked_by = fields.pop("_add_blocked_by", None)
        try:
            bean = self._store.create_bean(**fields)
            if add_blocks:
                self._store.add_dep(bean.id, add_blocks)
            if add_blocked_by:
                self._store.add_dep(add_blocked_by, bean.id)
        except Exception as e:
            self._sidebar.show_status(str(e))

    @Slot(str, str)
    def _on_add_dep(self, from_id: str, to_id: str):
        try:
            self._store.add_dep(from_id, to_id)
        except Exception as e:
            self._sidebar.show_status(str(e))

    @Slot(str, str)
    def _on_color_changed(self, assignee: str, color: str):
        self._config.colors[assignee] = color
        self._config.save(self._beans_dir)
        # Refresh scene with new colors
        self._scene.update_snapshot(self._beans, self._deps)

    @Slot()
    def _on_toggle_completed(self):
        self._scene.show_completed = self._toggle_completed_action.isChecked()
        self._scene.update_snapshot(self._beans, self._deps)

    @Slot()
    def _on_toggle_on_top(self):
        if self._toggle_on_top_action.isChecked():
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
        self.show()

    @Slot()
    def _on_open(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select beans directory")
        if dir_path and self._on_open_dir:
            self._on_open_dir(dir_path)

    def closeEvent(self, event):
        self._watcher.stop()
        self._store.close()
        super().closeEvent(event)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main_window.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/beans_stalk/ui/main_window.py tests/test_main_window.py
git commit -m "feat: add MainWindow with splitter, menus, and signal wiring"
```

---

### Task 13: Application Lifecycle

**Files:**
- Create: `src/beans_stalk/app.py`

- [ ] **Step 1: Implement app lifecycle**

`src/beans_stalk/app.py`:
```python
import signal
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from beans_stalk.main import IpcServer
from beans_stalk.ui.main_window import MainWindow


class StalkApp:
    """Application lifecycle manager."""

    def __init__(self):
        self._qt_app: QApplication | None = None
        self._ipc_server: IpcServer | None = None
        self._windows: dict[str, MainWindow] = {}  # beans_dir -> window

    def open_beans_dir(self, beans_dir_path: str):
        """Open a window for a beans directory, or focus existing."""
        resolved = str(Path(beans_dir_path).resolve())
        if resolved in self._windows:
            win = self._windows[resolved]
            win.raise_()
            win.activateWindow()
            return

        beans_dir = Path(resolved)
        db_path = beans_dir / "beans.db"
        if not db_path.exists():
            return

        win = MainWindow(beans_dir, on_open_dir=self.open_beans_dir)
        win.destroyed.connect(lambda: self._windows.pop(resolved, None))
        self._windows[resolved] = win
        win.show()

    def run(self, initial_beans_dir: str):
        self._qt_app = QApplication(sys.argv)
        self._qt_app.setApplicationName("Beans Stalk")
        self._qt_app.setQuitOnLastWindowClosed(True)

        # IPC server for single-instance
        self._ipc_server = IpcServer(on_path=self._on_ipc_path)
        self._ipc_server.start()

        # Signal handling
        def signal_handler(signum, frame):
            self._shutdown()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Timer to allow Python signals through Qt event loop
        signal_timer = QTimer()
        signal_timer.timeout.connect(lambda: None)
        signal_timer.start(250)

        # Open initial window
        self.open_beans_dir(initial_beans_dir)

        sys.exit(self._qt_app.exec())

    def _on_ipc_path(self, path: str):
        """Handle path received from another stalk invocation."""
        # Must run on main thread via QTimer
        QTimer.singleShot(0, lambda: self.open_beans_dir(path))

    def _shutdown(self):
        if self._ipc_server:
            self._ipc_server.stop()
        for win in list(self._windows.values()):
            win.close()
        if self._qt_app:
            self._qt_app.quit()


def run_app(beans_dir: str):
    """Entry point called from main.py after IPC check."""
    app = StalkApp()
    app.run(beans_dir)
```

- [ ] **Step 2: Commit**

```bash
git add src/beans_stalk/app.py
git commit -m "feat: add StalkApp lifecycle with IPC server and multi-window management"
```

---

### Task 14: Integration Testing

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration tests for the full data→layout→scene pipeline**

`tests/test_integration.py`:
```python
"""End-to-end integration tests for the full stack."""

from beans import api

from beans_stalk.config import StalkConfig
from beans_stalk.data.store import StalkStore
from beans_stalk.graph.layout import build_dag, compute_layout
from beans_stalk.ui.dag_scene import DagScene


class TestDataToLayoutPipeline:
    def test_full_pipeline(self, tmp_beans_dir, store):
        """Data layer -> graph layer pipeline works end to end."""
        a = api.create_bean(store, "Task A")
        b = api.create_bean(store, "Task B")
        c = api.create_bean(store, "Task C")
        api.add_dep(store, a.id, b.id)
        api.add_dep(store, b.id, c.id)
        store.close()

        ss = StalkStore(tmp_beans_dir / "beans.db")
        beans, deps = ss.load_snapshot()
        ss.close()

        graph = build_dag(beans, deps)
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2

        positions = compute_layout(graph, {a.id, b.id, c.id})
        assert len(positions) == 3


class TestDataToScenePipeline:
    def test_full_pipeline_with_scene(self, tmp_beans_dir, store, qapp):
        """Data layer -> scene layer works end to end."""
        a = api.create_bean(store, "Task A")
        b = api.create_bean(store, "Task B")
        api.add_dep(store, a.id, b.id)
        store.close()

        ss = StalkStore(tmp_beans_dir / "beans.db")
        beans, deps = ss.load_snapshot()
        ss.close()

        config = StalkConfig()
        scene = DagScene(config)
        scene.update_snapshot(beans, deps)

        assert len(scene._nodes) == 2
        assert len(scene._edges) == 1
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration tests for data→layout pipeline and Qt scene"
```

---

### Task 15: Manual Smoke Test & Polish

- [ ] **Step 1: Create a test beans directory and run the app**

```bash
cd /tmp && mkdir -p test-project && cd test-project
beans init
beans create "Design the API" --type epic
beans create "Write endpoints" --parent $(beans --json list | python -c "import sys,json; print(json.loads(sys.stdin.read())[0]['id'])")
beans create "Write tests"
beans dep add $(beans --json list | python -c "import sys,json; d=json.loads(sys.stdin.read()); print(d[1]['id'])") $(beans --json list | python -c "import sys,json; d=json.loads(sys.stdin.read()); print(d[2]['id'])")
stalk .beans
```

- [ ] **Step 2: Verify core functionality**

Manually verify:
- DAG renders with 3 nodes and dependency edges
- Clicking a node shows it in sidebar
- Editing a bean title and clicking Save persists
- Right-click context menu works for new beans
- Cmd-T toggles stay-on-top
- Cmd-N opens new bean form
- View > Show completed toggles display

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: final polish and integration verification"
```

---

## Task Dependency Order

```
Task 1 (scaffold)
  └→ Task 2 (config)
  └→ Task 3 (data store)
       └→ Task 4 (watcher)
  └→ Task 5 (graph layout)
  └→ Task 6 (IPC / main.py)
  └→ Task 7 (bean node)
  └→ Task 8 (dep edge)
       └→ Task 9 (dag scene) — depends on 5, 7, 8
            └→ Task 10 (dag view) — depends on 9
                 └→ Task 11 (sidebar)
                      └→ Task 12 (main window) — depends on 2, 3, 4, 9, 10, 11
                           └→ Task 13 (app.py) — depends on 6, 12
                                └→ Task 14 (integration tests)
                                     └→ Task 15 (smoke test)
```

Tasks 2, 3, 5, 6, 7, 8 can run in parallel after Task 1.
