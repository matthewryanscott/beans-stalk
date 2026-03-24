import os
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QProcess
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QMenu,
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
    navigate_to_bean = Signal(str)  # bean_id — select and center on a bean

    editing_started = Signal()
    editing_finished = Signal()

    def __init__(self, config: StalkConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._current_bean: Bean | None = None
        self._current_deps: list[Dep] = []
        self._all_beans: list[Bean] = []
        self._visible_bean_ids: set[str] = set()
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

        # Bean ID (read-only, shown when viewing existing bean)
        id_container = QVBoxLayout()
        id_container.setContentsMargins(0, 0, 0, 0)
        id_container.setSpacing(0)
        id_label = QLabel("ID")
        id_container.addWidget(id_label)
        id_row = QHBoxLayout()
        id_row.setContentsMargins(0, 0, 0, 0)
        self._id_display = QLineEdit()
        self._id_display.setReadOnly(True)
        id_row.addWidget(self._id_display, 1)
        self._copy_id_btn = QPushButton("\U0001f4cb Copy")
        self._copy_id_btn.clicked.connect(self._copy_id)
        id_row.addWidget(self._copy_id_btn)
        id_container.addLayout(id_row)
        layout.addLayout(id_container)
        self._id_label = id_label
        self._id_row_widgets = [id_label, self._id_display, self._copy_id_btn]

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

        # Metadata section (read-only, shown for existing beans)
        self._meta_group = QGroupBox("Details")
        meta_layout = QVBoxLayout(self._meta_group)
        meta_layout.setSpacing(2)

        self._created_at_label = QLabel()
        self._created_at_label.setStyleSheet("color: #aaa; font-size: 11px;")
        meta_layout.addWidget(self._created_at_label)

        self._created_by_label = QLabel()
        self._created_by_label.setStyleSheet("color: #aaa; font-size: 11px;")
        meta_layout.addWidget(self._created_by_label)

        self._closed_at_label = QLabel()
        self._closed_at_label.setStyleSheet("color: #aaa; font-size: 11px;")
        meta_layout.addWidget(self._closed_at_label)

        self._close_reason_label = QLabel()
        self._close_reason_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self._close_reason_label.setWordWrap(True)
        meta_layout.addWidget(self._close_reason_label)

        layout.addWidget(self._meta_group)

        # Save button
        self._save_btn = QPushButton("Save")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save)
        layout.addWidget(self._save_btn)

        # Track changes to enable/disable save button
        self._title_edit.textChanged.connect(self._update_save_enabled)
        self._type_combo.currentTextChanged.connect(self._update_save_enabled)
        self._priority_spin.valueChanged.connect(self._update_save_enabled)
        self._body_edit.textChanged.connect(self._update_save_enabled)

        # Blocks section (this bean blocks others)
        self._blocks_group = QGroupBox("Blocks")
        blocks_layout = QVBoxLayout(self._blocks_group)
        blocks_layout.setSpacing(2)
        self._blocks_list = QVBoxLayout()
        blocks_layout.addLayout(self._blocks_list)
        self._add_blocks_btn = QPushButton("+ Add")
        self._add_blocks_btn.clicked.connect(self._on_add_blocks)
        blocks_layout.addWidget(self._add_blocks_btn)
        layout.addWidget(self._blocks_group)

        # Blocked by section (others block this bean)
        self._blocked_by_group = QGroupBox("Blocked by")
        blocked_by_layout = QVBoxLayout(self._blocked_by_group)
        blocked_by_layout.setSpacing(2)
        self._blocked_by_list = QVBoxLayout()
        blocked_by_layout.addLayout(self._blocked_by_list)
        self._add_blocked_by_btn = QPushButton("+ Add")
        self._add_blocked_by_btn.clicked.connect(self._on_add_blocked_by)
        blocked_by_layout.addWidget(self._add_blocked_by_btn)
        layout.addWidget(self._blocked_by_group)

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

    def set_context(self, all_beans: list[Bean], visible_ids: set[str]):
        """Update the list of all beans and visible IDs for dep menus."""
        self._all_beans = all_beans
        self._visible_bean_ids = visible_ids

    def _editable_widgets(self):
        """Return widgets whose changes affect the save button."""
        return (self._title_edit, self._type_combo, self._priority_spin,
                self._body_edit)

    def show_bean(self, bean: Bean, deps: list[Dep]):
        """Populate the editor with an existing bean's data."""
        self._current_bean = bean
        self._current_deps = deps
        self._creating = False
        self._status_label.setVisible(False)
        self._stack.setCurrentIndex(1)

        # Show bean ID
        self._id_display.setText(bean.id)
        for w in self._id_row_widgets:
            w.setVisible(True)

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

        # Metadata
        created_str = bean.created_at.strftime("%Y-%m-%d %H:%M") if bean.created_at else ""
        self._created_at_label.setText(f"Created: {created_str}")
        self._created_at_label.setVisible(bool(created_str))

        self._created_by_label.setText(f"Created by: {bean.created_by}")
        self._created_by_label.setVisible(bool(bean.created_by))

        closed_str = bean.closed_at.strftime("%Y-%m-%d %H:%M") if bean.closed_at else ""
        self._closed_at_label.setText(f"Closed: {closed_str}")
        self._closed_at_label.setVisible(bool(closed_str))

        self._close_reason_label.setText(f"Reason: {bean.close_reason}")
        self._close_reason_label.setVisible(bool(bean.close_reason))

        self._meta_group.setVisible(bool(created_str or bean.created_by or closed_str or bean.close_reason))

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

        # Populate dependency sections
        self._populate_deps(bean, deps)

    def start_new_bean(self, prefill: dict | None = None):
        """Switch to create-new-bean mode, optionally pre-filling fields."""
        self._current_bean = None
        self._current_deps = []
        self._creating = True
        self._pre_filled = prefill or {}
        self._status_label.setVisible(False)
        self._stack.setCurrentIndex(1)

        # Hide ID row for new beans
        for w in self._id_row_widgets:
            w.setVisible(False)

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
        self._meta_group.setVisible(False)
        self._blocks_group.setVisible(False)
        self._blocked_by_group.setVisible(False)

        self._title_edit.setFocus()

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
        fields = {
            "title": self._title_edit.text(),
            "type": self._type_combo.currentText(),
            "priority": self._priority_spin.value(),
            "body": self._body_edit.toPlainText(),
        }
        if self._creating:
            fields["ref_id"] = self._ref_id_edit.text() or None
            # Pass through prefilled keys not shown in the form
            for key in ("parent_id", "_add_blocks", "_add_blocked_by"):
                if key in self._pre_filled:
                    fields[key] = self._pre_filled[key]
        return fields

    def _set_editing_mode(self, editing: bool):
        """Enable/disable the form while an external editor is open."""
        self._edit_external_btn.setVisible(not editing and bool(self._editor_cmd))
        self._editing_label.setVisible(editing)
        self._title_edit.setEnabled(not editing)
        self._type_combo.setEnabled(not editing)
        self._priority_spin.setEnabled(not editing)
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

    def _clear_layout(self, layout):
        """Remove all widgets from a layout."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _populate_deps(self, bean: Bean, deps: list[Dep]):
        """Populate the blocks/blocked-by sections."""
        bean_map = {b.id: b for b in self._all_beans}

        # This bean blocks others (from_id == bean.id)
        blocks = [d for d in deps if d.from_id == bean.id]
        self._clear_layout(self._blocks_list)
        for dep in blocks:
            target = bean_map.get(dep.to_id)
            title = target.title if target else dep.to_id
            tid = dep.to_id
            self._blocks_list.addWidget(
                self._make_dep_row(title, tid, dep.from_id, dep.to_id)
            )
        self._blocks_group.setVisible(True)

        # This bean is blocked by others (to_id == bean.id)
        blocked_by = [d for d in deps if d.to_id == bean.id]
        self._clear_layout(self._blocked_by_list)
        for dep in blocked_by:
            source = bean_map.get(dep.from_id)
            title = source.title if source else dep.from_id
            sid = dep.from_id
            self._blocked_by_list.addWidget(
                self._make_dep_row(title, sid, dep.from_id, dep.to_id)
            )
        self._blocked_by_group.setVisible(True)

    def _make_dep_row(self, title: str, navigate_id: str, from_id: str, to_id: str) -> QWidget:
        """Create a row with a clickable wrapping label and a remove button."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        link = QLabel(f"<a href='#' style='color: #6cb4ee; text-decoration: none;'>{title}</a>")
        link.setWordWrap(True)
        link.setCursor(Qt.CursorShape.PointingHandCursor)
        link.linkActivated.connect(lambda _href, bid=navigate_id: self.navigate_to_bean.emit(bid))
        row.addWidget(link, 1)
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(20, 20)
        remove_btn.clicked.connect(
            lambda checked=False, f=from_id, t=to_id: self.remove_dep_requested.emit(f, t)
        )
        row.addWidget(remove_btn)
        container = QWidget()
        container.setLayout(row)
        return container

    def _reachable_from(self, start_id: str, deps: list[Dep]) -> set[str]:
        """Return all bean IDs reachable from start_id following dep edges."""
        visited = set()
        stack = [start_id]
        while stack:
            nid = stack.pop()
            if nid in visited:
                continue
            visited.add(nid)
            for d in deps:
                if d.from_id == nid and d.to_id not in visited:
                    stack.append(d.to_id)
        return visited

    def _dep_candidates(self, direction: str) -> list[Bean]:
        """Return beans eligible for adding as a dep, excluding self and cycle-creators."""
        if self._current_bean is None:
            return []
        bean_id = self._current_bean.id
        deps = self._current_deps
        # Already connected
        if direction == "blocks":
            existing = {d.to_id for d in deps if d.from_id == bean_id}
        else:
            existing = {d.from_id for d in deps if d.to_id == bean_id}

        # Cycle detection: if adding "self blocks X", check X can't already reach self
        # If adding "X blocks self", check self can't already reach X
        candidates = []
        for b in self._all_beans:
            if b.id == bean_id:
                continue
            if b.id not in self._visible_bean_ids:
                continue
            if b.id in existing:
                continue
            # Check for cycles
            if direction == "blocks":
                # Would add edge: bean_id -> b.id
                # Cycle if b.id can already reach bean_id
                if bean_id in self._reachable_from(b.id, deps):
                    continue
            else:
                # Would add edge: b.id -> bean_id
                # Cycle if bean_id can already reach b.id
                if b.id in self._reachable_from(bean_id, deps):
                    continue
            candidates.append(b)
        return candidates

    def _on_add_blocks(self):
        """Show menu of beans this bean could block."""
        self._show_dep_menu("blocks")

    def _on_add_blocked_by(self):
        """Show menu of beans that could block this bean."""
        self._show_dep_menu("blocked_by")

    def _show_dep_menu(self, direction: str):
        """Show a popup menu to add a dependency."""
        if self._current_bean is None:
            return
        candidates = self._dep_candidates(direction)
        menu = QMenu(self)
        # "New bean..." at top
        new_action = menu.addAction("New bean...")
        menu.addSeparator()
        actions = {}
        for b in candidates:
            action = menu.addAction(b.title)
            actions[action] = b
        chosen = menu.exec(self._add_blocks_btn.mapToGlobal(
            self._add_blocks_btn.rect().bottomLeft()
        ) if direction == "blocks" else self._add_blocked_by_btn.mapToGlobal(
            self._add_blocked_by_btn.rect().bottomLeft()
        ))
        if chosen is None:
            return
        if chosen is new_action:
            prefill = {}
            if direction == "blocks":
                prefill["_add_blocks"] = self._current_bean.id
            else:
                prefill["_add_blocked_by"] = self._current_bean.id
            self.start_new_bean(prefill)
            return
        target = actions.get(chosen)
        if target:
            bean_id = self._current_bean.id
            if direction == "blocks":
                self.add_dep_requested.emit(bean_id, target.id)
            else:
                self.add_dep_requested.emit(target.id, bean_id)

    def _copy_id(self):
        """Copy the current bean's ID to clipboard."""
        text = self._id_display.text()
        if text:
            QApplication.clipboard().setText(text)

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
