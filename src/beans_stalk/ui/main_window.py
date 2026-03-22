from pathlib import Path

import sys

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QSplitter, QFileDialog, QWidget, QVBoxLayout

from beans.models import Bean, Dep
from beans_stalk.config import StalkConfig
from beans_stalk.data.store import StalkStore
from beans_stalk.data.watcher import DataWatcher
from beans_stalk.ui.breadcrumb import BreadcrumbBar
from beans_stalk.ui.dag_scene import DagScene
from beans_stalk.ui.dag_view import DagView
from beans_stalk.ui.sidebar import Sidebar


class MainWindow(QMainWindow):
    def __init__(self, beans_dir: Path, on_open_dir=None, on_new_window=None,
                 navigate_to: str | None = None, config: StalkConfig | None = None,
                 parent=None):
        super().__init__(parent)
        self._beans_dir = beans_dir
        self._on_open_dir = on_open_dir
        self._on_new_window = on_new_window
        self._initial_navigate_to = navigate_to
        self._db_path = beans_dir / "beans.db"
        self._config = config if config is not None else StalkConfig.load(beans_dir)
        self._store = StalkStore(self._db_path)
        self._watcher = DataWatcher(
            db_path=self._db_path,
            poll_interval_seconds=self._config.poll_interval_seconds,
            parent=self,
        )
        self._watcher.snapshot_changed.connect(self._on_snapshot_changed)
        self._beans: list[Bean] = []
        self._deps: list[Dep] = []
        self._setup_ui()
        self._setup_menus()
        self._watcher.start()
        self.setWindowTitle(f"Beans Stalk — {beans_dir}")
        geo = self._config.window_geometry
        if geo and "width" in geo:
            self.setGeometry(geo.get("x", 100), geo.get("y", 100),
                             geo["width"], geo["height"])
        else:
            self.resize(1200, 700)

    def _setup_ui(self):
        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left pane: breadcrumb + DAG view
        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self._breadcrumb = BreadcrumbBar()
        self._breadcrumb.set_layout_algorithm(self._config.layout_algorithm)
        self._breadcrumb.layout_changed.connect(self._on_layout_changed)
        left_layout.addWidget(self._breadcrumb)

        self._scene = DagScene(self._config, store=self._store)
        self._scene.layout_algorithm = self._config.layout_algorithm
        self._view = DagView(self._scene)
        left_layout.addWidget(self._view)

        self._splitter.addWidget(left_pane)

        self._sidebar = Sidebar(self._config)
        self._splitter.addWidget(self._sidebar)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        saved_sizes = self._config.window_geometry.get("splitter_sizes")
        if saved_sizes:
            self._splitter.setSizes(saved_sizes)
        else:
            self._splitter.setSizes([900, 300])
        self.setCentralWidget(self._splitter)

        # Connect signals
        self._breadcrumb.navigate_to.connect(self._on_breadcrumb_navigate)
        self._scene.navigate_requested.connect(self._on_scene_navigate)
        self._scene.node_clicked.connect(self._on_node_selected)
        self._scene.selection_cleared.connect(self._sidebar.clear_selection)
        self._scene.dep_toggle_requested.connect(self._on_dep_toggle)
        self._scene.dep_remove_requested.connect(self._on_dep_remove)
        self._sidebar.save_requested.connect(self._on_save_bean)
        self._sidebar.close_bean_requested.connect(self._on_close_bean)
        self._sidebar.claim_requested.connect(self._on_claim_bean)
        self._sidebar.release_requested.connect(self._on_release_bean)
        self._sidebar.create_bean_requested.connect(self._on_create_bean)
        self._sidebar.add_dep_requested.connect(self._on_add_dep)
        self._sidebar.remove_dep_requested.connect(self._on_dep_remove)
        self._sidebar.color_changed.connect(self._on_color_changed)
        self._sidebar.editing_started.connect(self._on_editing_started)
        self._sidebar.editing_finished.connect(self._on_editing_finished)
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
        self._view.view_in_new_window_requested.connect(self._on_view_in_new_window)

    def _setup_menus(self):
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

        edit_menu = self.menuBar().addMenu("Edit")
        new_bean_action = QAction("New bean", self)
        new_bean_action.setShortcut(QKeySequence("Ctrl+N"))
        new_bean_action.triggered.connect(lambda: self._sidebar.start_new_bean())
        edit_menu.addAction(new_bean_action)
        save_action = QAction("Save bean", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._sidebar._on_save)
        edit_menu.addAction(save_action)
        edit_body_action = QAction("Edit body in editor", self)
        edit_body_action.triggered.connect(self._sidebar._on_edit_external)
        edit_menu.addAction(edit_body_action)

        view_menu = self.menuBar().addMenu("View")
        self._toggle_completed_action = QAction("Show completed beans", self)
        self._toggle_completed_action.setCheckable(True)
        self._toggle_completed_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self._toggle_completed_action.triggered.connect(self._on_toggle_completed)
        view_menu.addAction(self._toggle_completed_action)
        self._toggle_on_top_action = QAction("Always on top", self)
        self._toggle_on_top_action.setCheckable(True)
        self._toggle_on_top_action.setShortcut(QKeySequence("Ctrl+T"))
        self._toggle_on_top_action.triggered.connect(self._on_toggle_on_top)
        view_menu.addAction(self._toggle_on_top_action)

    def _viewport_key(self) -> str:
        pid = self._scene.current_parent_id
        return pid if pid is not None else "root"

    def _save_viewport(self):
        key = self._viewport_key()
        state = self._view.get_viewport_state()
        state["show_completed"] = self._scene.show_completed
        if self._scene.selected_id is not None:
            state["selected_id"] = self._scene.selected_id
        self._config.viewports[key] = state

    def _restore_viewport(self):
        key = self._viewport_key()
        state = self._config.viewports.get(key)
        if state:
            self._view.restore_viewport_state(state)
            show = state.get("show_completed", False)
            self._scene.show_completed = show
            self._toggle_completed_action.setChecked(show)
            selected = state.get("selected_id")
            if selected and selected in self._scene._nodes:
                self._scene.selected_id = selected
                self._scene.node_clicked.emit(selected)

    def _apply_navigation(self, parent_id):
        """Update scene to show a parent level. Does NOT touch breadcrumb."""
        if not self._sidebar.check_unsaved_changes():
            return
        self._save_viewport()
        self._scene.selected_id = None
        self._scene.current_parent_id = parent_id
        # Restore show_completed before snapshot so the correct beans are visible
        key = parent_id if parent_id is not None else "root"
        state = self._config.viewports.get(key, {})
        show = state.get("show_completed", False)
        self._scene.show_completed = show
        self._toggle_completed_action.setChecked(show)
        self._scene.update_snapshot(self._beans, self._deps)
        self._view.update_scene_rect()
        self._restore_viewport()

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

    @Slot(list, list)
    def _on_snapshot_changed(self, beans: list[Bean], deps: list[Dep]):
        first_load = not self._beans
        self._beans = beans
        self._deps = deps
        if first_load and self._initial_navigate_to:
            # Navigate to the requested parent on first load
            parent_id = self._initial_navigate_to
            self._initial_navigate_to = None
            bean = next((b for b in beans if b.id == parent_id), None)
            if bean:
                title = bean.title
                self._breadcrumb.push(parent_id, title)
                self._scene.current_parent_id = parent_id
        if first_load:
            state = self._config.viewports.get(self._viewport_key(), {})
            show = state.get("show_completed", False)
            self._scene.show_completed = show
            self._toggle_completed_action.setChecked(show)
        self._scene.update_snapshot(beans, deps)
        self._view.update_scene_rect()
        if first_load:
            self._restore_viewport()
        if self._scene.selected_id:
            bean = next(
                (b for b in beans if b.id == self._scene.selected_id), None
            )
            if bean:
                self._sidebar.show_bean(bean, deps)

    @Slot(str)
    def _on_node_selected(self, bean_id: str):
        if not self._sidebar.check_unsaved_changes():
            # Re-assert the previous selection so Qt item states are restored
            self._scene.selected_id = self._scene.selected_id
            return
        self._scene.selected_id = bean_id
        bean = next((b for b in self._beans if b.id == bean_id), None)
        if bean:
            self._sidebar.show_bean(bean, self._deps)

    @Slot(str, str)
    def _on_dep_toggle(self, from_id: str, to_id: str):
        existing = any(
            d.from_id == from_id
            and d.to_id == to_id
            and d.dep_type == "blocks"
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
    def _on_claim_bean(self, bean_id: str, actor: str):
        try:
            self._store.claim_bean(bean_id, actor)
        except Exception as e:
            self._sidebar.show_status(str(e))

    @Slot(str)
    def _on_release_bean(self, bean_id: str):
        try:
            bean = next((b for b in self._beans if b.id == bean_id), None)
            actor = bean.assignee if bean else ""
            self._store.release_bean(bean_id, actor)
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

    def _on_editing_started(self):
        """Lock the UI while an external editor is open."""
        self._view.locked = True
        self._breadcrumb.setEnabled(False)

    def _on_editing_finished(self):
        """Unlock the UI after the external editor closes."""
        self._view.locked = False
        self._breadcrumb.setEnabled(True)

    @Slot(str)
    def _on_view_in_new_window(self, bean_id: str):
        if self._on_new_window:
            self._on_new_window(str(self._beans_dir), bean_id)

    @Slot(str)
    def _on_layout_changed(self, key: str):
        self._config.layout_algorithm = key
        self._config.save(self._beans_dir)
        self._scene.layout_algorithm = key
        self._scene.update_snapshot(self._beans, self._deps)
        self._view.update_scene_rect()

    @Slot(str, str)
    def _on_color_changed(self, assignee: str, color: str):
        self._config.colors[assignee] = color
        self._config.save(self._beans_dir)
        self._scene.update_snapshot(self._beans, self._deps)
        self._view.update_scene_rect()

    @Slot()
    def _on_toggle_completed(self):
        self._scene.show_completed = self._toggle_completed_action.isChecked()
        self._scene.update_snapshot(self._beans, self._deps)
        self._view.update_scene_rect()

    @Slot()
    def _on_toggle_on_top(self):
        if self._toggle_on_top_action.isChecked():
            self.setWindowFlags(
                self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
            )
        else:
            self.setWindowFlags(
                self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint
            )
        self.show()

    @Slot()
    def _on_open(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select beans directory"
        )
        if dir_path and self._on_open_dir:
            self._on_open_dir(dir_path)

    # Physical Ctrl key modifier — Qt swaps Ctrl/Meta on macOS
    _CTRL_MOD = (
        Qt.KeyboardModifier.MetaModifier
        if sys.platform == "darwin"
        else Qt.KeyboardModifier.ControlModifier
    )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_G and event.modifiers() == self._CTRL_MOD:
            self._sidebar._on_edit_external()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if not self._sidebar.check_unsaved_changes():
            event.ignore()
            return
        self._save_viewport()
        geo = self.geometry()
        self._config.window_geometry = {
            "x": geo.x(), "y": geo.y(),
            "width": geo.width(), "height": geo.height(),
            "splitter_sizes": self._splitter.sizes(),
        }
        self._config.save(self._beans_dir)
        self._watcher.stop()
        self._store.close()
        super().closeEvent(event)
