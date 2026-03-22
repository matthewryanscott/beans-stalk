import os
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QProcess
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QMessageBox,
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
    claim_requested = Signal(str, str)  # bean_id, actor
    release_requested = Signal(str)  # bean_id
    create_bean_requested = Signal(dict)
    add_dep_requested = Signal(str, str)
    remove_dep_requested = Signal(str, str)
    color_changed = Signal(str, str)

    editing_started = Signal()
    editing_finished = Signal()

    def __init__(self, config: StalkConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._current_bean: Bean | None = None
        self._current_deps: list[Dep] = []
        self._creating = False
        self._pre_filled: dict = {}
        self._editor_cmd = os.environ.get("EDITOR")
        self._editor_process: QProcess | None = None
        self._editor_tmp_path: Path | None = None
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

        # Title (editable)
        layout.addWidget(QLabel("Title"))
        self._title_edit = QLineEdit()
        layout.addWidget(self._title_edit)

        # Type (editable for both edit and create) + Status (read-only display)
        type_status_row = QHBoxLayout()
        type_col = QVBoxLayout()
        type_col.addWidget(QLabel("Type"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["task", "bug", "epic", "project"])
        type_col.addWidget(self._type_combo)
        type_status_row.addLayout(type_col)
        status_col = QVBoxLayout()
        status_col.addWidget(QLabel("Status"))
        self._status_label_field = QComboBox()
        self._status_label_field.setEnabled(False)
        status_col.addWidget(self._status_label_field)
        type_status_row.addLayout(status_col)
        layout.addLayout(type_status_row)

        # Priority (editable)
        layout.addWidget(QLabel("Priority"))
        self._priority_spin = QSpinBox()
        self._priority_spin.setMinimum(0)
        self._priority_spin.setMaximum(4)
        self._priority_spin.setValue(2)
        layout.addWidget(self._priority_spin)

        # Assignee (read-only display with color button)
        layout.addWidget(QLabel("Assignee"))
        assignee_row = QHBoxLayout()
        self._assignee_label = QLineEdit()
        self._assignee_label.setReadOnly(True)
        assignee_row.addWidget(self._assignee_label, 1)
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(24, 24)
        self._color_btn.clicked.connect(self._pick_color)
        assignee_row.addWidget(self._color_btn)
        layout.addLayout(assignee_row)

        # Parent ID (editable)
        layout.addWidget(QLabel("Parent ID"))
        self._parent_edit = QLineEdit()
        layout.addWidget(self._parent_edit)

        # Ref ID (editable at creation, read-only after)
        self._ref_id_label_widget = QLabel("Ref ID")
        layout.addWidget(self._ref_id_label_widget)
        self._ref_id_edit = QLineEdit()
        layout.addWidget(self._ref_id_edit)
        self._ref_id_display = QLineEdit()
        self._ref_id_display.setReadOnly(True)
        layout.addWidget(self._ref_id_display)

        # Body — stretches to fill available vertical space (editable)
        body_container = QVBoxLayout()
        body_container.setContentsMargins(0, 0, 0, 0)
        body_container.setSpacing(0)
        body_header = QHBoxLayout()
        body_header.setContentsMargins(0, 0, 0, 0)
        body_header.setSpacing(4)
        body_header.addWidget(QLabel("Body"))
        editor_name = Path(self._editor_cmd).name if self._editor_cmd else None
        self._edit_external_btn = QPushButton(f"Edit with {editor_name}")
        self._edit_external_btn.clicked.connect(self._on_edit_external)
        self._edit_external_btn.setVisible(bool(self._editor_cmd))
        body_header.addWidget(self._edit_external_btn)
        self._editing_label = QLabel(f"(editing with {editor_name})")
        self._editing_label.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        self._editing_label.setVisible(False)
        body_header.addWidget(self._editing_label)
        body_header.addStretch()
        body_container.addLayout(body_header)
        self._body_edit = QTextEdit()
        self._body_edit.setMinimumHeight(80)
        body_container.addWidget(self._body_edit, 1)  # stretch factor 1
        layout.addLayout(body_container, 1)  # stretch factor 1

        # Save button
        self._save_btn = QPushButton("Save")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save)
        layout.addWidget(self._save_btn)

        # Track changes to enable/disable save button
        self._title_edit.textChanged.connect(self._update_save_enabled)
        self._type_combo.currentTextChanged.connect(self._update_save_enabled)
        self._priority_spin.valueChanged.connect(self._update_save_enabled)
        self._parent_edit.textChanged.connect(self._update_save_enabled)
        self._body_edit.textChanged.connect(self._update_save_enabled)

        # Claim section (shown for open beans)
        self._claim_spacer = QWidget()
        self._claim_spacer.setFixedHeight(16)
        layout.addWidget(self._claim_spacer)
        self._claim_group = QGroupBox("Claim")
        claim_layout = QVBoxLayout(self._claim_group)
        claim_layout.addWidget(QLabel("Assignee"))
        self._claim_assignee_edit = QLineEdit()
        claim_layout.addWidget(self._claim_assignee_edit)
        self._claim_btn = QPushButton("Claim")
        self._claim_btn.clicked.connect(self._on_claim)
        claim_layout.addWidget(self._claim_btn)
        layout.addWidget(self._claim_group)

        # Release section (shown for in_progress beans)
        self._release_spacer = QWidget()
        self._release_spacer.setFixedHeight(16)
        layout.addWidget(self._release_spacer)
        self._release_group = QGroupBox("Release")
        release_layout = QVBoxLayout(self._release_group)
        self._release_btn = QPushButton("Release")
        self._release_btn.clicked.connect(self._on_release)
        release_layout.addWidget(self._release_btn)
        layout.addWidget(self._release_group)

        # Close bean section (hidden when viewing closed beans)
        self._close_spacer = QWidget()
        self._close_spacer.setFixedHeight(16)
        layout.addWidget(self._close_spacer)
        self._close_group = QGroupBox("Close Bean")
        close_layout = QVBoxLayout(self._close_group)
        close_layout.addWidget(QLabel("Reason"))
        self._close_reason_edit = QLineEdit()
        close_layout.addWidget(self._close_reason_edit)
        self._close_btn = QPushButton("Close Bean")
        self._close_btn.clicked.connect(self._on_close_bean)
        close_layout.addWidget(self._close_btn)
        layout.addWidget(self._close_group)

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

    def _editable_widgets(self):
        """Return widgets whose changes affect the save button."""
        return (self._title_edit, self._type_combo, self._priority_spin,
                self._parent_edit, self._body_edit)

    def show_bean(self, bean: Bean, deps: list[Dep]):
        """Populate the editor with an existing bean's data."""
        self._current_bean = bean
        self._current_deps = deps
        self._creating = False
        self._status_label.setVisible(False)
        self._stack.setCurrentIndex(1)

        # Block signals while populating to avoid spurious save-button updates
        for w in self._editable_widgets():
            w.blockSignals(True)
        self._title_edit.setText(bean.title)
        self._type_combo.setCurrentText(bean.type)
        self._status_label_field.clear()
        self._status_label_field.addItem(bean.status)
        self._status_label_field.setCurrentText(bean.status)
        self._priority_spin.setValue(bean.priority)
        self._assignee_label.setText(bean.assignee or "")
        self._parent_edit.setText(str(bean.parent_id) if bean.parent_id else "")
        self._ref_id_edit.setVisible(False)
        self._ref_id_display.setVisible(True)
        self._ref_id_display.setText(bean.ref_id or "")
        self._body_edit.setPlainText(bean.body)
        for w in self._editable_widgets():
            w.blockSignals(False)
        self._save_btn.setText("Save")
        self._save_btn.setEnabled(False)

        # Update color button
        color = self._config.get_color(bean.assignee)
        self._color_btn.setStyleSheet(f"background-color: {color};")
        self._color_btn.setVisible(bean.assignee is not None)

        # Show/hide action panels based on status
        is_open = bean.status == "open"
        is_in_progress = bean.status == "in_progress"
        is_closed = bean.status == "closed"

        self._claim_group.setVisible(is_open)
        self._claim_spacer.setVisible(is_open)
        if is_open:
            self._claim_assignee_edit.setText("")

        self._release_group.setVisible(is_in_progress)
        self._release_spacer.setVisible(is_in_progress)

        self._close_group.setVisible(not is_closed)
        self._close_spacer.setVisible(not is_closed)


    def start_new_bean(self, prefill: dict | None = None):
        """Switch to create-new-bean mode, optionally pre-filling fields."""
        self._current_bean = None
        self._current_deps = []
        self._creating = True
        self._pre_filled = prefill or {}
        self._status_label.setVisible(False)
        self._stack.setCurrentIndex(1)

        for w in self._editable_widgets():
            w.blockSignals(True)
        self._title_edit.setText(self._pre_filled.get("title", ""))
        self._type_combo.setCurrentText(self._pre_filled.get("type", "task"))
        self._status_label_field.clear()
        self._status_label_field.addItem("open")
        self._status_label_field.setCurrentText("open")
        self._priority_spin.setValue(self._pre_filled.get("priority", 2))
        self._assignee_label.setText("")
        self._color_btn.setVisible(False)
        self._parent_edit.setText(self._pre_filled.get("parent_id", ""))
        self._ref_id_edit.setVisible(True)
        self._ref_id_display.setVisible(False)
        self._ref_id_edit.setText(self._pre_filled.get("ref_id", ""))
        self._body_edit.setPlainText(self._pre_filled.get("body", ""))
        for w in self._editable_widgets():
            w.blockSignals(False)
        self._save_btn.setText("Create")
        self._save_btn.setEnabled(False)
        self._claim_group.setVisible(False)
        self._claim_spacer.setVisible(False)
        self._release_group.setVisible(False)
        self._release_spacer.setVisible(False)
        self._close_group.setVisible(False)
        self._close_spacer.setVisible(False)


    def show_status(self, message: str):
        """Display a status/error message."""
        self._stack.setCurrentIndex(1)
        self._status_label.setText(message)
        self._status_label.setVisible(True)

    def _update_save_enabled(self):
        """Enable save button only when there are unsaved changes."""
        self._save_btn.setEnabled(self.has_unsaved_changes())

    def has_unsaved_changes(self) -> bool:
        """Check if the current form has been modified from the loaded bean."""
        if self._current_bean is None:
            if self._creating:
                return bool(self._title_edit.text().strip())
            return False
        bean = self._current_bean
        if self._title_edit.text() != bean.title:
            return True
        if self._type_combo.currentText() != bean.type:
            return True
        if self._priority_spin.value() != bean.priority:
            return True
        if (self._parent_edit.text() or None) != bean.parent_id:
            return True
        if self._body_edit.toPlainText() != bean.body:
            return True
        return False

    def check_unsaved_changes(self) -> bool:
        """If there are unsaved changes, prompt the user. Returns True if OK to proceed."""
        if not self.has_unsaved_changes():
            return True
        result = QMessageBox.question(
            self,
            "Unsaved Changes",
            "There are unsaved changes. Would you like to save them before navigating away?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
        )
        if result == QMessageBox.StandardButton.Yes:
            self._on_save()
            return True
        if result == QMessageBox.StandardButton.No:
            return True
        return False  # Cancel

    def _collect_fields(self) -> dict:
        """Gather current field values into a dict."""
        if self._creating:
            # At creation, all Bean fields are valid
            fields = {
                "title": self._title_edit.text(),
                "type": self._type_combo.currentText(),
                "priority": self._priority_spin.value(),
                "parent_id": self._parent_edit.text() or None,
                "ref_id": self._ref_id_edit.text() or None,
                "body": self._body_edit.toPlainText(),
            }
        else:
            # For updates, only BeanUpdate-compatible fields
            fields = {
                "title": self._title_edit.text(),
                "type": self._type_combo.currentText(),
                "priority": self._priority_spin.value(),
                "parent_id": self._parent_edit.text() or None,
                "body": self._body_edit.toPlainText(),
            }
        return fields

    def _set_editing_mode(self, editing: bool):
        """Enable/disable the form while an external editor is open."""
        self._edit_external_btn.setVisible(not editing and bool(self._editor_cmd))
        self._editing_label.setVisible(editing)
        self._title_edit.setEnabled(not editing)
        self._type_combo.setEnabled(not editing)
        self._priority_spin.setEnabled(not editing)
        self._parent_edit.setEnabled(not editing)
        self._body_edit.setEnabled(not editing)
        self._save_btn.setEnabled(not editing)
        self._claim_btn.setEnabled(not editing)
        self._release_btn.setEnabled(not editing)
        self._close_btn.setEnabled(not editing)
        if editing:
            self.editing_started.emit()
        else:
            self.editing_finished.emit()

    def _on_edit_external(self):
        """Launch $EDITOR with body contents in a temp markdown file."""
        if not self._editor_cmd or self._editor_process is not None:
            return
        if self._current_bean is None and not self._creating:
            return

        # Write current body to temp file
        body = self._body_edit.toPlainText()
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", prefix="bean-body-", delete=False
        )
        tmp.write(body)
        tmp.close()
        self._editor_tmp_path = Path(tmp.name)

        self._set_editing_mode(True)

        self._editor_process = QProcess(self)
        self._editor_process.finished.connect(self._on_editor_finished)
        editor_name = Path(self._editor_cmd).name
        # Editors that return immediately without --wait
        wait_flag_editors = {"code", "code-insiders", "subl", "atom", "zed"}
        args = []
        if editor_name in wait_flag_editors:
            args.append("--wait")
        args.append(str(self._editor_tmp_path))
        self._editor_process.start(self._editor_cmd, args)

    def _on_editor_finished(self):
        """Read back the temp file and update the body field."""
        if self._editor_tmp_path and self._editor_tmp_path.exists():
            body = self._editor_tmp_path.read_text()
            self._body_edit.setPlainText(body)
            self._editor_tmp_path.unlink(missing_ok=True)
        self._editor_tmp_path = None
        self._editor_process = None
        self._set_editing_mode(False)
        self.window().raise_()
        self.window().activateWindow()

    def _on_claim(self):
        """Handle claim button click."""
        if self._current_bean is not None:
            actor = self._claim_assignee_edit.text().strip()
            if actor:
                self.claim_requested.emit(str(self._current_bean.id), actor)

    def _on_release(self):
        """Handle release button click."""
        if self._current_bean is not None:
            self.release_requested.emit(str(self._current_bean.id))

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
        """Open a color picker for the current bean's assignee."""
        if self._current_bean is None or not self._current_bean.assignee:
            return
        assignee = self._current_bean.assignee
        current_color = QColor(self._config.get_color(assignee))
        color = QColorDialog.getColor(current_color, self, "Pick Assignee Color")
        if color.isValid():
            hex_color = color.name()
            self._config.colors[assignee] = hex_color
            self._color_btn.setStyleSheet(f"background-color: {hex_color};")
            self.color_changed.emit(assignee, hex_color)
