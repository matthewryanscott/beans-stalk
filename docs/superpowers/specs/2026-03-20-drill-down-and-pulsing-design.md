# Parent/Child Drill-Down Navigation & Pulsing Claimed Nodes

**Date:** 2026-03-20
**Status:** Draft

## Overview

Two enhancements to Beans Stalk:
1. **Drill-down navigation** — view beans by parent/child hierarchy with breadcrumbs and ghost nodes for cross-level dependencies
2. **Pulsing claimed nodes** — visual indicator for beans currently being worked on

## Feature 1: Drill-Down Navigation

### Navigation Model

The DAG scene tracks a `current_parent_id: str | None`:
- `None` = root view (beans with `parent_id is None`)
- A bean ID = viewing that parent's children (beans with `parent_id == current_parent_id`)

### What's Visible at Each Level

- **Regular nodes:** beans whose `parent_id` matches `current_parent_id`
- **Ghost nodes:** beans from other parents/root that have **direct** deps to/from visible regular nodes. Only direct deps produce ghosts — no transitive expansion. Rendered with distinct ghost styling. Double-click navigates to that ghost's home view (its parent's view, or root if `parent_id is None`).
- **Edges:** all deps between visible nodes (including ghosts). Ghost-to-ghost edges are rendered when both ghosts are visible (they both have deps to regular nodes, so their mutual edge provides useful context).

No parent ghost header — breadcrumbs handle upward navigation.

### Ghost Node Algorithm

During `update_snapshot()`:
1. Filter beans where `parent_id == current_parent_id` → these are **regular** nodes
2. Build a set of regular node IDs
3. Walk all deps: if one end is a regular node and the other is not, the other end is a ghost candidate
4. Look up ghost candidates from the full bean list, add them as ghost nodes
5. Include all deps where both ends are in the visible set (regular + ghost)

### Navigation Actions

| Action | Result |
|--------|--------|
| Double-click parent node (has children) | Drill down into its children |
| Double-click ghost node | Navigate to ghost's home view |
| Click breadcrumb segment | Navigate to that level |

On navigation, the current selection is cleared.

### Breadcrumb Bar

- `QWidget` with horizontal `QHBoxLayout` of flat `QPushButton`s and `>` separator labels
- Always starts with `Root`
- Each drill-down appends a segment with the parent bean's title
- Clicking any segment navigates to that level
- Owns its path stack internally: `push(parent_id, title)` and `pop_to(parent_id)` methods
- Emits `navigate_to(object)` signal — emits `str` (bean ID) or `None` (root). Uses `Signal(object)` to support `None`.

**Placement:** Inside the left pane of the splitter, stacked above the DAG view in a `QVBoxLayout`. The sidebar stays full window height on the right.

### Ghost Node Rendering

Ghost nodes use the same `BeanNode` class with a `ghost` property:
- Semi-transparent fill (alpha ~0.2) with dashed border
- Same assignee color tinting
- Title text at reduced opacity
- No priority dot
- `setCursor(Qt.CursorShape.PointingHandCursor)` when ghost is set, reset when cleared

### Determining "Has Children"

A node is a drillable parent if any bean in the full snapshot has `parent_id == node.id`. Precomputed as a `set` of parent IDs during `update_snapshot()` (single O(n) pass over all beans) for efficient lookup.

### Empty View After Drill-Down

If drilling into a parent results in no visible beans (e.g. all children closed with `show_completed` off), show placeholder text: "All children are closed" instead of the default "No beans yet" message.

## Feature 2: Pulsing Claimed Nodes

### Which Nodes Pulse

A node pulses if:
- The bean has `status == "in_progress"` and `assignee is not None`, OR
- Any of its descendants (recursive — children, grandchildren, etc.) meet the above criteria

Recursive check ensures that a root-level epic pulses when any deeply nested task inside it is being worked on.

### Visual Treatment

- `QPropertyAnimation` on a `_pulse_phase` float property (0.0 → 1.0), duration ~1.5s, `InOutSine` easing, looping
- `paint()` modulates border width using `_pulse_phase` (pulses between 2px and 4px)
- Border uses the assignee color
- When `pulsing` is cleared, animation stops and border resets
- Pulsing nodes should use `NoCache` cache mode (instead of `DeviceCoordinateCache`) since the animation invalidates the cache on every frame. Non-pulsing nodes keep `DeviceCoordinateCache`.

### Implementation

Add to `BeanNode`:
- `pulsing` bool property — starts/stops the animation, switches cache mode
- `_pulse_phase` float Qt Property — animated value used in `paint()`

The scene precomputes a set of "has active descendant" bean IDs during `update_snapshot()` (single pass building parent→children map, then walking up from claimed beans to mark all ancestors). Sets `pulsing=True` on applicable nodes.

## File Changes

### Modified Files

**`src/beans_stalk/ui/bean_node.py`:**
- Add `ghost` bool property with alternate rendering (dashed border, low alpha, no priority dot, pointing hand cursor)
- Add `pulsing` bool property + `_pulse_phase` float Property for border animation
- Switch cache mode to `NoCache` when pulsing, back to `DeviceCoordinateCache` when not
- `paint()` checks `ghost` and `_pulse_phase`

**`src/beans_stalk/ui/dag_scene.py`:**
- Add `current_parent_id: str | None` property
- Add `navigate_requested` signal — `Signal(object)` to support `None` for root
- `update_snapshot()` filters beans by `current_parent_id`, identifies ghost nodes via direct deps
- Precomputes `_parent_ids` set and `_has_active_descendant` set
- Marks ghost nodes with `ghost=True`
- Sets `pulsing=True` on nodes with active claims or active descendants
- Double-click on parent → emit `navigate_requested(bean_id)`, on ghost → emit `navigate_requested(ghost.parent_id)`

**`src/beans_stalk/ui/dag_view.py`:**
- Handle `mouseDoubleClickEvent`: inspect `itemAt`, determine if parent (has children) or ghost, emit scene's `navigate_requested` signal accordingly

**`src/beans_stalk/ui/main_window.py`:**
- Left pane becomes `QWidget` with `QVBoxLayout`: breadcrumb bar + DAG view
- Connect breadcrumb `navigate_to` and scene `navigate_requested` to a `_navigate(parent_id)` method
- `_navigate` updates `scene.current_parent_id`, updates breadcrumb, clears selection, triggers re-render

### New File

**`src/beans_stalk/ui/breadcrumb.py`:**
- `BreadcrumbBar(QWidget)` with `navigate_to = Signal(object)`
- `push(parent_id: str, title: str)` — append segment
- `pop_to(parent_id: str | None)` — truncate path to given ID
- `clear()` — reset to root only
- Internal path stack: `list[tuple[str | None, str]]`
- Rebuilds button layout on path change
- Flat styled buttons with `>` separator labels

### New Test Files

- `tests/test_breadcrumb.py` — breadcrumb path management and signal emission
- `tests/test_drill_down.py` — ghost node identification, navigation, parent detection, pulsing logic
