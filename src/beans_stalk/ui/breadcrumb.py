from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox

from beans_stalk.graph.layouts import PROVIDERS


class BreadcrumbBar(QWidget):
    """Navigation breadcrumb for parent/child drill-down."""

    navigate_to = Signal(object)  # str (bean ID) or None (root)
    layout_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: list[tuple[str, str]] = []  # [(parent_id, title), ...]
        self._buttons: list[QPushButton] = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 2, 4, 2)
        self._layout.setSpacing(2)

        # Layout algorithm dropdown — created once, persists across _rebuild calls
        self._layout_combo = QComboBox()
        self._layout_combo.setStyleSheet(
            "QComboBox { border: 1px solid #555; color: #ccc; background: #333; "
            "font-size: 11px; padding: 1px 4px; min-width: 100px; }"
        )
        for key, provider in PROVIDERS.items():
            self._layout_combo.addItem(provider.NAME, key)
        self._layout_combo.currentIndexChanged.connect(self._on_layout_changed)

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
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w and w is not self._layout_combo:
                w.deleteLater()
        self._buttons.clear()

        root_btn = self._make_button("Root", None)
        self._buttons.append(root_btn)
        self._layout.addWidget(root_btn)

        for parent_id, title in self._path:
            sep = QLabel(">")
            sep.setStyleSheet("color: #888; font-size: 11px;")
            self._layout.addWidget(sep)
            btn = self._make_button(title, parent_id)
            self._buttons.append(btn)
            self._layout.addWidget(btn)

        self._layout.addStretch()
        self._layout.addWidget(self._layout_combo)

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

    def _on_layout_changed(self, index: int):
        key = self._layout_combo.itemData(index)
        if key:
            self.layout_changed.emit(key)

    def set_layout_algorithm(self, key: str):
        index = self._layout_combo.findData(key)
        if index >= 0:
            self._layout_combo.blockSignals(True)
            self._layout_combo.setCurrentIndex(index)
            self._layout_combo.blockSignals(False)
