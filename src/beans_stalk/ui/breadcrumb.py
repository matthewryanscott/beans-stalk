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
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
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
