from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QSplitter, QFileDialog

from beans.models import Bean, Dep
from beans_stalk.config import StalkConfig
from beans_stalk.data.store import StalkStore
from beans_stalk.data.watcher import DataWatcher
from beans_stalk.ui.dag_scene import DagScene
from beans_stalk.ui.dag_view import DagView
from beans_stalk.ui.sidebar import Sidebar


class MainWindow(QMainWindow):
    def __init__(self, beans_dir: Path, on_open_dir=None, parent=None):
        super().__init__(parent)
        self._beans_dir = beans_dir
        self._on_open_dir = on_open_dir
        self._db_path = beans_dir / "beans.db"
        self._config = StalkConfig.load(beans_dir)
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

    @Slot(list, list)
    def _on_snapshot_changed(self, beans: list[Bean], deps: list[Dep]):
        self._beans = beans
        self._deps = deps
        self._scene.update_snapshot(beans, deps)
        if self._scene.selected_id:
            bean = next(
                (b for b in beans if b.id == self._scene.selected_id), None
            )
            if bean:
                self._sidebar.show_bean(bean, deps)

    @Slot(str)
    def _on_node_selected(self, bean_id: str):
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
        self._scene.update_snapshot(self._beans, self._deps)

    @Slot()
    def _on_toggle_completed(self):
        self._scene.show_completed = self._toggle_completed_action.isChecked()
        self._scene.update_snapshot(self._beans, self._deps)

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

    def closeEvent(self, event):
        self._watcher.stop()
        self._store.close()
        super().closeEvent(event)
