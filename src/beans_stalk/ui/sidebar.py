from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from beans.models import Bean, Dep
from beans_stalk.config import StalkConfig


class Sidebar(QWidget):
    """Property editor panel for viewing and editing beans."""

    save_requested = Signal(str, dict)
    close_bean_requested = Signal(str, str)
    create_bean_requested = Signal(dict)
    add_dep_requested = Signal(str, str)
    remove_dep_requested = Signal(str, str)
    color_changed = Signal(str, str)

    def __init__(self, config: StalkConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._current_bean: Bean | None = None
        self._current_deps: list[Dep] = []
        self._creating = False
        self._pre_filled: dict = {}
        self._setup_ui()
        self.show()

    def _setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        outer_layout.addWidget(self._stack)

        # Page 0: placeholder when no bean selected
        placeholder = QWidget()
        ph_layout = QVBoxLayout(placeholder)
        ph_layout.addStretch()
        ph_label = QLabel("Select or create a bean\nto see details")
        ph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_label.setStyleSheet("color: #888; font-size: 13px;")
        ph_layout.addWidget(ph_label)
        ph_layout.addStretch()
        self._stack.addWidget(placeholder)

        # Page 1: editor form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._stack.addWidget(scroll)

        container = QWidget()
        layout = QVBoxLayout(container)

        # Title
        layout.addWidget(QLabel("Title"))
        self._title_edit = QLineEdit()
        layout.addWidget(self._title_edit)

        # Type + Status side-by-side
        type_status_row = QHBoxLayout()
        type_col = QVBoxLayout()
        type_col.addWidget(QLabel("Type"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["task", "bug", "feature", "epic"])
        type_col.addWidget(self._type_combo)
        type_status_row.addLayout(type_col)
        status_col = QVBoxLayout()
        status_col.addWidget(QLabel("Status"))
        self._status_combo = QComboBox()
        self._status_combo.addItems(["open", "in_progress", "closed"])
        status_col.addWidget(self._status_combo)
        type_status_row.addLayout(status_col)
        layout.addLayout(type_status_row)

        # Priority
        layout.addWidget(QLabel("Priority"))
        self._priority_spin = QSpinBox()
        self._priority_spin.setMinimum(0)
        self._priority_spin.setMaximum(5)
        self._priority_spin.setValue(2)
        layout.addWidget(self._priority_spin)

        # Assignee with color button
        layout.addWidget(QLabel("Assignee"))
        assignee_row = QHBoxLayout()
        self._assignee_edit = QLineEdit()
        assignee_row.addWidget(self._assignee_edit)
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(24, 24)
        self._color_btn.clicked.connect(self._pick_color)
        assignee_row.addWidget(self._color_btn)
        layout.addLayout(assignee_row)

        # Parent ID
        layout.addWidget(QLabel("Parent ID"))
        self._parent_edit = QLineEdit()
        layout.addWidget(self._parent_edit)

        # Ref ID
        layout.addWidget(QLabel("Ref ID"))
        self._ref_id_edit = QLineEdit()
        layout.addWidget(self._ref_id_edit)

        # Body
        layout.addWidget(QLabel("Body"))
        self._body_edit = QTextEdit()
        self._body_edit.setMinimumHeight(80)
        layout.addWidget(self._body_edit)

        # Save button
        self._save_btn = QPushButton("Save")
        self._save_btn.clicked.connect(self._on_save)
        layout.addWidget(self._save_btn)

        # Close bean section
        close_group = QGroupBox("Close Bean")
        close_layout = QVBoxLayout(close_group)
        close_layout.addWidget(QLabel("Reason"))
        self._close_reason_edit = QLineEdit()
        close_layout.addWidget(self._close_reason_edit)
        self._close_btn = QPushButton("Close Bean")
        self._close_btn.clicked.connect(self._on_close_bean)
        close_layout.addWidget(self._close_btn)
        layout.addWidget(close_group)

        # Status label for messages
        self._status_label = QLabel()
        self._status_label.setVisible(False)
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        layout.addStretch()
        scroll.setWidget(container)

    def clear_selection(self):
        """Show the placeholder — no bean selected."""
        self._current_bean = None
        self._current_deps = []
        self._creating = False
        self._stack.setCurrentIndex(0)

    def show_bean(self, bean: Bean, deps: list[Dep]):
        """Populate the editor with an existing bean's data."""
        self._current_bean = bean
        self._current_deps = deps
        self._creating = False
        self._status_label.setVisible(False)
        self._stack.setCurrentIndex(1)

        self._title_edit.setText(bean.title)
        self._type_combo.setCurrentText(bean.type)
        self._status_combo.setCurrentText(bean.status)
        self._priority_spin.setValue(bean.priority)
        self._assignee_edit.setText(bean.assignee or "")
        self._parent_edit.setText(str(bean.parent_id) if bean.parent_id else "")
        self._ref_id_edit.setText(bean.ref_id or "")
        self._body_edit.setPlainText(bean.body)
        self._save_btn.setText("Save")

        # Update color button
        color = self._config.get_color(bean.assignee)
        self._color_btn.setStyleSheet(f"background-color: {color};")


    def start_new_bean(self, prefill: dict | None = None):
        """Switch to create-new-bean mode, optionally pre-filling fields."""
        self._current_bean = None
        self._current_deps = []
        self._creating = True
        self._pre_filled = prefill or {}
        self._status_label.setVisible(False)
        self._stack.setCurrentIndex(1)

        self._title_edit.setText(self._pre_filled.get("title", ""))
        self._type_combo.setCurrentText(self._pre_filled.get("type", "task"))
        self._status_combo.setCurrentText(self._pre_filled.get("status", "open"))
        self._priority_spin.setValue(self._pre_filled.get("priority", 2))
        self._assignee_edit.setText(self._pre_filled.get("assignee", ""))
        self._parent_edit.setText(self._pre_filled.get("parent_id", ""))
        self._ref_id_edit.setText(self._pre_filled.get("ref_id", ""))
        self._body_edit.setPlainText(self._pre_filled.get("body", ""))
        self._save_btn.setText("Create")


    def show_status(self, message: str):
        """Display a status/error message."""
        self._stack.setCurrentIndex(1)
        self._status_label.setText(message)
        self._status_label.setVisible(True)

    def _collect_fields(self) -> dict:
        """Gather current field values into a dict."""
        fields = {
            "title": self._title_edit.text(),
            "type": self._type_combo.currentText(),
            "status": self._status_combo.currentText(),
            "priority": self._priority_spin.value(),
            "assignee": self._assignee_edit.text() or None,
            "parent_id": self._parent_edit.text() or None,
            "ref_id": self._ref_id_edit.text() or None,
            "body": self._body_edit.toPlainText(),
        }
        return fields

    def _on_save(self):
        """Handle save/create button click."""
        fields = self._collect_fields()
        if self._creating:
            self.create_bean_requested.emit(fields)
        else:
            if self._current_bean is not None:
                self.save_requested.emit(str(self._current_bean.id), fields)

    def _on_close_bean(self):
        """Handle close-bean button click."""
        if self._current_bean is not None:
            reason = self._close_reason_edit.text()
            self.close_bean_requested.emit(str(self._current_bean.id), reason)

    def _pick_color(self):
        """Open a color picker for the current assignee."""
        assignee = self._assignee_edit.text()
        if not assignee:
            return
        current_color = QColor(self._config.get_color(assignee))
        color = QColorDialog.getColor(current_color, self, "Pick Assignee Color")
        if color.isValid():
            hex_color = color.name()
            self._config.colors[assignee] = hex_color
            self._color_btn.setStyleSheet(f"background-color: {hex_color};")
            self.color_changed.emit(assignee, hex_color)

