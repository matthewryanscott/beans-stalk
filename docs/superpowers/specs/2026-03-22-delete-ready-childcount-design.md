# Delete Bean, Ready Highlighting, Child Count Badge

Three features that bring missing `beans` API functionality into the Stalk GUI.

## 1. Delete Bean

### Triggers

- **Delete or Backspace key** with a node selected in the DAG view
- **Right-click context menu** "Delete bean" option

No sidebar button — delete is a DAG-level action. Delete is disabled on ghost nodes (context menu item hidden, Delete key is a no-op when a ghost is selected).

### Cascade Behavior

Verified against the `beans` library: `api.delete_bean` removes the bean and its deps. Children are **orphaned** (their `parent_id` still references the deleted bean). The dialog wording reflects this:

- **Default:** "Delete 'Bean Title'? This cannot be undone."
- **With deps only:** "Delete 'Bean Title' and its M dependencies? This cannot be undone."
- **With children:** "Delete 'Bean Title'? Its N children will become orphaned. This cannot be undone."
- **With both:** "Delete 'Bean Title' and its M dependencies? Its N children will become orphaned. This cannot be undone."

Uses `QMessageBox.warning` with Yes/Cancel (Cancel is default).

Child and dep counts are computed from `self._beans` and `self._deps` in MainWindow.

### Post-Delete Behavior

After successful delete, clear `scene.selected_id` and call `sidebar.clear_selection()` before the watcher triggers the next snapshot refresh.

### Signal Routing

`DagScene` owns the `delete_requested = Signal(str)` signal. `DagView` emits it (consistent with how `DagView` already emits `dep_toggle_requested` and `dep_remove_requested` on the scene).

### Implementation

- **StalkStore**: Add `delete_bean(bean_id)` wrapping `beans.api.delete_bean`.
- **DagView**: Emit `scene.delete_requested` on Delete/Backspace key press; add "Delete bean" to context menu.
- **DagScene**: Add `delete_requested = Signal(str)` signal.
- **MainWindow**: Connect `delete_requested` to `_on_delete_bean` which shows the confirmation dialog, computes child/dep counts, calls `store.delete_bean`, and clears selection.

### Files Changed

- `src/beans_stalk/data/store.py` — add `delete_bean`
- `src/beans_stalk/ui/dag_view.py` — Delete key handling + context menu item
- `src/beans_stalk/ui/dag_scene.py` — add `delete_requested` signal
- `src/beans_stalk/ui/main_window.py` — `_on_delete_bean` handler with dialog
- `tests/test_store.py` — test delete_bean
- `tests/test_main_window.py` — test delete wiring and dialog behavior

## 2. Ready Beans Highlighting

### Data Flow

- **StalkStore**: Add `ready_bean_ids()` method that calls `beans.api.ready_beans()` and returns `{b.id for b in api.ready_beans(store)}`.
- **DagScene.update_snapshot()**: Calls `ready_bean_ids()` once per refresh, stores the set, and sets `node.ready` on each node during the node update loop.

Note: this adds one extra DB query per poll cycle. Acceptable for typical dataset sizes.

### Visual Treatment

Ready nodes get a **blue border** (`#4A9EFF`) at 2.5px width (vs default 2px).

### Visual State Priority (highest wins)

1. **Selected** — white dashed border
2. **Ready** — blue solid border
3. **Default** — dark border derived from fill color

Ready border is suppressed on muted/ghost nodes.

### Implementation

- **BeanNode**: Add `ready` boolean property. In `paint()`, apply blue border when ready and not selected/muted/ghost.
- **DagScene**: Pass ready set to node update loop.

### Files Changed

- `src/beans_stalk/data/store.py` — add `ready_bean_ids`
- `src/beans_stalk/ui/bean_node.py` — add `ready` property, paint logic
- `src/beans_stalk/ui/dag_scene.py` — compute and apply ready state
- `tests/test_bean_node.py` — test ready visual state
- `tests/test_store.py` — test ready_bean_ids

## 3. Child Count Badge

### Data Flow

- **DagScene.update_snapshot()**: Builds `child_counts: dict[str, int]` by counting beans per `parent_id` across all beans (the `beans` list passed to `update_snapshot` already contains all beans, so no extra DB query needed). Sets `node.child_count` on each node.

### Visual Treatment

- **Small rounded-rect badge** in the top-right corner of the node.
- Background: semi-transparent white (`rgba(255,255,255,0.25)`), text: white.
- Shows only the number (e.g., "3").
- Rendered only when `child_count > 0`.
- Hidden on ghost/muted nodes.

### Size

Badge sized relative to font metrics for DPI awareness, floats on the node boundary at a fixed offset from the top-right corner. Does not affect node width calculation.

### Implementation

- **BeanNode**: Add `child_count` int property. In `paint()`, draw badge when count > 0 and not ghost/muted.
- **DagScene**: Compute child counts and pass to nodes.

### Files Changed

- `src/beans_stalk/ui/bean_node.py` — add `child_count` property, paint badge
- `src/beans_stalk/ui/dag_scene.py` — compute child counts, set on nodes
- `tests/test_bean_node.py` — test badge rendering
