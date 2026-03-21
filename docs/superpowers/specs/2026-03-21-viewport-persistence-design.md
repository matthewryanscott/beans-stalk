# Viewport Persistence

**Date:** 2026-03-21
**Status:** Draft

## Overview

Persist the viewport center position and zoom scale per parent-level view in `beans-stalk.toml`. When navigating between views or reopening the app, the viewport restores to where the user left off.

## Config Structure

New `viewports` dict in `StalkConfig`, persisted as TOML:

```toml
[viewports.root]
center_x = 150.5
center_y = -200.0
scale = 1.2

[viewports."bean-abc123"]
center_x = 0.0
center_y = 50.0
scale = 0.8
```

Key is `"root"` for the root view or the parent bean ID for drill-down views. Values are the scene-coordinate center of the viewport and the view's scale factor.

`StalkConfig` field: `viewports: dict[str, dict[str, float]] = field(default_factory=dict)`. Both `load()` and `save()` updated.

## Save Triggers

- **Navigate away:** when the user navigates to a different level (breadcrumb click or double-click drill-down), save the current view's state before switching
- **Close window:** save the current view's state in `closeEvent`

## Restore Triggers

- **Navigate to a level:** after the scene updates, restore the saved viewport state if an entry exists for that level
- **Open window:** after initial data load, restore the root view's saved state

## DagView Methods

Two new methods on `DagView`:

```python
def get_viewport_state(self) -> dict[str, float]:
    """Return current center (scene coords) and scale."""
    center = self.mapToScene(self.viewport().rect().center())
    scale = self.transform().m11()
    return {"center_x": center.x(), "center_y": center.y(), "scale": scale}

def restore_viewport_state(self, state: dict[str, float]) -> None:
    """Restore center and scale from saved state."""
    scale = state.get("scale", 1.0)
    current_scale = self.transform().m11()
    factor = scale / current_scale
    self.scale(factor, factor)
    self.centerOn(state.get("center_x", 0.0), state.get("center_y", 0.0))
```

## MainWindow Coordination

The viewport key for the current view:

```python
def _viewport_key(self) -> str:
    pid = self._scene.current_parent_id
    return pid if pid is not None else "root"
```

**On navigate (before switching):** save current viewport state to config.

**On navigate (after scene update):** restore saved viewport for the new level, if it exists.

**On close:** save current viewport state, then save config.

## File Changes

### Modified Files

- `src/beans_stalk/config.py` — add `viewports` field, update `load()`/`save()`
- `src/beans_stalk/ui/dag_view.py` — add `get_viewport_state()`, `restore_viewport_state()`
- `src/beans_stalk/ui/main_window.py` — save/restore viewport on navigate and close
- `tests/test_config.py` — test viewports load/save
- `tests/test_dag_view.py` — test get/restore viewport state
- `tests/test_main_window.py` — test viewport persistence on navigate
