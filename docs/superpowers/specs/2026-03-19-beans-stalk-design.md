# Beans Stalk — Design Spec

**Date:** 2026-03-19
**Status:** Draft

## Overview

Beans Stalk is a Python + PySide6 companion app for the [Beans](https://github.com/versafeed/beans) task tracker CLI. It provides a live-updating visual DAG of bean dependencies with a sidebar editor for viewing and modifying beans.

**Target platform:** macOS (primary), with no intentional Linux/Windows incompatibilities.

## Architecture

Layered architecture with clear boundaries:

```
┌─────────────────────────────────────────────────┐
│                    main.py                       │
│         CLI entry point + single-instance IPC    │
├─────────────────────────────────────────────────┤
│                    app.py                        │
│       QApplication lifecycle, socket server      │
├──────────────┬──────────────┬───────────────────┤
│   ui/        │   graph/     │   data/            │
│  Qt widgets  │  networkx    │  beans API +       │
│  scenes      │  layout      │  watcher           │
│  interaction │  computation │  config             │
├──────────────┴──────────────┴───────────────────┤
│              beans (upstream dependency)          │
│         models, store, api, journal              │
└─────────────────────────────────────────────────┘
```

**Key boundaries:**
- `data/` — zero Qt imports, uses beans' own models and API
- `graph/` — zero Qt imports, pure networkx computation
- `ui/` — Qt widgets, depends on data and graph layers
- `main.py` / `app.py` — lifecycle orchestration, IPC

## Project Structure

```
beans-stalk/
├── pyproject.toml
├── src/
│   └── beans_stalk/
│       ├── __init__.py
│       ├── main.py              # Entry point, CLI (typer), single-instance IPC
│       ├── app.py               # QApplication lifecycle, signal handling
│       ├── config.py            # beans-stalk.toml read/write
│       ├── data/
│       │   ├── __init__.py
│       │   ├── store.py         # Wraps beans.store + beans.api for reads and writes
│       │   └── watcher.py       # Hybrid file-watch + poll, emits change signals
│       ├── graph/
│       │   ├── __init__.py
│       │   └── layout.py        # networkx DAG construction + layout computation
│       └── ui/
│           ├── __init__.py
│           ├── main_window.py   # Main window, menu bar, splitter, stay-on-top
│           ├── dag_view.py      # QGraphicsView subclass (zoom, pan, shift-drag)
│           ├── dag_scene.py     # QGraphicsScene with nodes and edges
│           ├── bean_node.py     # QGraphicsObject for a single bean
│           ├── dep_edge.py      # QGraphicsPathItem for a dependency edge
│           └── sidebar.py       # Bean property editor panel
```

## Data Layer

### Models

Uses `beans.models.Bean` and `beans.models.Dep` directly — no duplicate models.

### Store (`data/store.py`)

Thin wrapper around beans' own stores:
- Uses `beans.store.BeanStore` and `beans.store.DepStore` for reads
- Uses `beans.api` for all writes: create, update, close, claim, release, add/remove dep
- Beans API handles journal entries, validation, and business rules automatically

### Watcher (`data/watcher.py`)

Hybrid change detection:
- **Watchdog observer** on the DB file + WAL file triggers an immediate poll
- **Fallback QTimer** at configurable interval (default 2 seconds)
- **Debounce:** coalesce filesystem events within ~200ms before polling
- **Poll logic:** `SELECT MAX(id) FROM journal` — if changed since last check, reload data
- **Output:** emits a Qt signal (`snapshot_changed`) with fresh beans and deps from beans' stores

## Graph Layer (`graph/layout.py`)

Pure computation, no Qt dependency:

- `build_dag(beans, deps) → nx.DiGraph`: constructs directed graph, nodes carry bean data as attributes, edges carry dep_type
- `compute_layout(graph, visible_ids) → dict[str, tuple[float, float]]`: runs layered layout on subgraph of visible nodes
- **Layout algorithm:** `graphviz_layout(graph, prog="dot")` for clean top-to-bottom DAG layering; falls back to `nx.spring_layout` if graphviz unavailable
- **Visibility filtering:** accepts a set of visible bean IDs; completed beans excluded before layout unless within fade window or "show completed" is on

### Layout Stability

1. Compute new layout positions
2. If a node is selected, calculate delta between its old and new position
3. Translate all new positions by that delta (selected node stays at same viewport location)
4. If nothing selected, anchor on viewport center instead
5. Return both old and new positions so the UI can animate the transition

## UI Layer

### Main Window (`ui/main_window.py`)

One window per opened beans dir:
- `QMainWindow` with **user-adjustable** horizontal splitter: DAG view (left, stretches) + sidebar (right, initial default ~300px)
- **Menu bar:**
  - File: Open beans dir, Close window, Quit
  - View: Toggle completed beans, Toggle stay-on-top
  - Edit: New bean
- **Stay-on-top:** toggles `Qt.WindowType.WindowStaysOnTopHint` + `.show()`, per-window, not persisted
- **Title bar:** shows the beans dir path
- Owns a `DataWatcher` instance for its beans dir
- Connects watcher → layout → scene update pipeline

### DAG View (`ui/dag_view.py`)

`QGraphicsView` subclass:
- **Drag** to pan viewport
- **Scroll wheel / pinch** to zoom
- **Shift-drag** from node A to node B: creates A-blocks-B dependency if none exists, removes it if it does
- **Shift-click** on an edge: removes that dependency
- **Click** on a node: selects it, shows in sidebar
- Tracks selected node ID for layout anchoring

### DAG Scene (`ui/dag_scene.py`)

`QGraphicsScene`:
- Manages collection of `BeanNode` and `DepEdge` items
- `update_from_snapshot(beans, deps, positions, old_positions)`: diffs current items, adds/removes as needed, animates position changes via `QPropertyAnimation`
- Handles "recently closed" display: nodes for beans closed within the fade window rendered at muted opacity

### Bean Node (`ui/bean_node.py`)

`QGraphicsObject` (needs QObject for animation support):
- Rounded rectangle with title text inside
- Small priority indicator in corner
- **Fill color:** assignee color from config
- **Completed nodes:** same assignee color but at fixed muted opacity (e.g. 0.3)
- Hover: subtle highlight effect
- Emits signal on click for sidebar selection

### Dependency Edge (`ui/dep_edge.py`)

`QGraphicsPathItem`:
- Curved arrow (cubic bezier) from source to target node
- Follows node positions during animation
- Shift-clickable for removal

### Sidebar (`ui/sidebar.py`)

`QWidget` property editor panel:
- Shows all bean fields, editable via standard Qt widgets:
  - Title: `QLineEdit`
  - Body: `QTextEdit`
  - Type: `QComboBox` (task, bug, epic, project)
  - Status: `QComboBox` (open, in_progress, closed)
  - Priority: `QSpinBox` (0-4)
  - Assignee: `QLineEdit`
  - Parent: `QLineEdit` or picker
  - Ref ID: `QLineEdit`
- **Dependencies section:** lists blockers and blocked-by with add/remove buttons
- **Save button:** commits changes via `beans.api`
- **New Bean mode:** blank form, optional pre-filled parent/dependency from context menu
- **Close Bean button:** with optional reason field
- **Assignee color:** editable from sidebar when a bean with that assignee is selected

### New Bean Creation

Two entry points:
- **"New Bean" button/menu/shortcut:** opens blank editor in sidebar
- **Context menu on DAG nodes:** right-click a node to create a child or a bean that depends on / is blocked by that node. Pre-fills the relationship.

## Application Lifecycle & IPC

### CLI Entry Point (`main.py`)

```
stalk [path-to-beans-dir]
```

1. Parse args with typer. If path omitted, discover `.beans/` by walking up from cwd.
2. Attempt to connect to Unix domain socket at `~/.beans-stalk.sock`:
   - **Connection succeeds:** send beans dir path, exit. Running instance opens/focuses that window.
   - **Connection fails:** first instance. Launch the app.

### App Lifecycle (`app.py`)

- Creates `QApplication` with macOS high-DPI attributes
- Starts Unix socket server (listens for new `stalk` invocations)
- Opens initial window for requested beans dir
- `setQuitOnLastWindowClosed(True)`
- SIGINT/SIGTERM: clean shutdown (stop watchers, close DB connections, remove socket)
- Socket message handler: focus existing window for that dir, or open a new one

## Configuration (`config.py`)

Per-beans-dir config in `beans-stalk.toml`, stored alongside `beans.db`:

```toml
fade_minutes = 5
poll_interval_seconds = 2

[colors]
# auto-populated as new assignees appear
# alice = "#e06c75"
# claude = "#61afef"
```

### Color Assignment

- Predefined palette of ~12 visually distinct, accessible colors
- New assignees get the next unused palette color
- If palette exhausted, generate deterministic color from hash of assignee name
- Assignment written to `beans-stalk.toml` immediately for stability across restarts
- Editable via sidebar or by hand-editing the TOML

### Completed Bean Display

- **Within fade window:** immediately rendered at fixed muted opacity (e.g. 0.3), same assignee color. Shown even when "show completed" is off.
- **Past fade window:** removed from view entirely, unless "show completed" is toggled on (in which case shown at muted opacity indefinitely).

## Dependencies

```toml
[project]
requires-python = ">=3.14"

[project.scripts]
stalk = "beans_stalk.main:app"

dependencies = [
    "pyside6",
    "beans",           # upstream, local/editable install
    "networkx",
    "watchdog",
    "tomli-w",         # TOML writing (stdlib tomllib handles reading)
    "typer",
]

[project.optional-dependencies]
graphviz = ["pygraphviz"]  # for dot layout; falls back to spring_layout
```

**No qasync needed** — no async HTTP. Watchdog threading bridges to Qt main thread via signals. Poll timer is a plain `QTimer`.

## Interaction Summary

| Action | Behavior |
|--------|----------|
| Click node | Select, show in sidebar |
| Drag canvas | Pan viewport |
| Scroll / pinch | Zoom |
| Shift-drag node→node | Toggle dependency (add if absent, remove if present) |
| Shift-click edge | Remove dependency |
| Right-click node | Context menu: new child, new blocker, new blocked-by |
| Right-click canvas | Context menu: new bean |
| Cmd-T | Toggle stay-on-top |
