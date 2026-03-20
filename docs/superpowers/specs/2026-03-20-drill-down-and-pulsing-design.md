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
- **Ghost nodes:** beans from other parents/root that have deps to/from visible regular nodes. Rendered with distinct ghost styling. Double-click navigates to that ghost's home view (its parent's view, or root if `parent_id is None`).
- **Edges:** all deps between visible nodes (including ghosts)

No parent ghost header — breadcrumbs handle upward navigation.

### Navigation Actions

| Action | Result |
|--------|--------|
| Double-click parent node (has children) | Drill down into its children |
| Double-click ghost node | Navigate to ghost's home view |
| Click breadcrumb segment | Navigate to that level |

### Breadcrumb Bar

- `QWidget` with horizontal `QHBoxLayout` of flat `QPushButton`s and `>` separator labels
- Always starts with `Root`
- Each drill-down appends a segment with the parent bean's title
- Clicking any segment navigates to that level
- Emits `navigate_to(parent_id: str | None)` signal

**Placement:** Inside the left pane of the splitter, stacked above the DAG view in a `QVBoxLayout`. The sidebar stays full window height on the right.

### Ghost Node Rendering

Ghost nodes use the same `BeanNode` class with a `ghost` property:
- Semi-transparent fill (alpha ~0.2) with dashed border
- Same assignee color tinting
- Title text at reduced opacity
- No priority dot
- Cursor changes to pointing hand on hover

### Determining "Has Children"

A node is a drillable parent if any bean in the full snapshot has `parent_id == node.id`. The scene checks this against the full bean list (not just visible beans) so closed children still make a parent drillable.

## Feature 2: Pulsing Claimed Nodes

### Which Nodes Pulse

A node pulses if:
- The bean has `status == "in_progress"` and `assignee is not None`, OR
- Any of its children (beans with `parent_id == this bean's id`) meet the above criteria (indicates active work happening inside a parent)

### Visual Treatment

- `QPropertyAnimation` on a `_pulse_phase` float property (0.0 → 1.0), duration ~1.5s, `InOutSine` easing, looping
- `paint()` modulates border width using `_pulse_phase` (pulses between 2px and 4px)
- Border uses the assignee color
- When `pulsing` is cleared, animation stops and border resets

### Implementation

Add to `BeanNode`:
- `pulsing` bool property — starts/stops the animation
- `_pulse_phase` float Qt Property — animated value used in `paint()`

The scene sets `pulsing=True` on applicable nodes during `update_snapshot()`.

## File Changes

### Modified Files

**`src/beans_stalk/ui/bean_node.py`:**
- Add `ghost` bool property with alternate rendering (dashed border, low alpha, no priority dot, pointing hand cursor)
- Add `pulsing` bool property + `_pulse_phase` float Property for border animation
- `paint()` checks `ghost` and `_pulse_phase`

**`src/beans_stalk/ui/dag_scene.py`:**
- Add `current_parent_id: str | None` property
- Add `navigate_requested(str)` signal (emitted with target parent_id or None for root)
- `update_snapshot()` filters beans by `current_parent_id`
- Identifies external dep ghosts — beans from other levels with deps to/from visible beans
- Marks ghost nodes with `ghost=True`
- Sets `pulsing=True` on nodes with active claims or claimed children

**`src/beans_stalk/ui/dag_view.py`:**
- Handle `mouseDoubleClickEvent`: if target is a parent node (has children) → navigate down; if ghost → navigate to ghost's home

**`src/beans_stalk/ui/main_window.py`:**
- Left pane becomes `QWidget` with `QVBoxLayout`: breadcrumb bar + DAG view
- Connect breadcrumb `navigate_to` and scene `navigate_requested` signals
- Maintain breadcrumb state (stack of parent IDs and titles)

### New File

**`src/beans_stalk/ui/breadcrumb.py`:**
- `BreadcrumbBar(QWidget)` with `navigate_to(str | None)` signal
- `set_path(segments: list[tuple[str | None, str]])` method to update displayed path
- Flat styled buttons with `>` separators
