from PySide6.QtCore import Qt
from beans import api
from beans_stalk.ui.main_window import MainWindow


class TestMainWindow:
    def test_creates_with_beans_dir(self, tmp_beans_dir, qtbot):
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        assert "Beans Stalk" in win.windowTitle()
        win.close()

    def test_splitter_has_two_widgets(self, tmp_beans_dir, qtbot):
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        splitter = win.centralWidget()
        assert splitter.count() == 2
        win.close()

    def test_menu_bar_has_expected_menus(self, tmp_beans_dir, qtbot):
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        menu_titles = [a.text() for a in win.menuBar().actions()]
        assert "File" in menu_titles
        assert "Edit" in menu_titles
        assert "View" in menu_titles
        win.close()

    def test_stay_on_top_toggle(self, tmp_beans_dir, qtbot):
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        win.show()
        assert not (win.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        win._toggle_on_top_action.trigger()
        assert win.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        win._toggle_on_top_action.trigger()
        assert not (win.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        win.close()

    def test_layout_algorithm_change(self, qtbot, tmp_beans_dir, store):
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        assert win._scene.layout_algorithm == "sugiyama"
        win._on_layout_changed("sugiyama_compact")
        assert win._scene.layout_algorithm == "sugiyama_compact"
        win.close()

    def test_node_selection_updates_sidebar(self, tmp_beans_dir, store, qtbot):
        a = api.create_bean(store, "Task A")
        store.close()
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        win.show()
        qtbot.waitUntil(lambda: len(win._beans) > 0, timeout=2000)
        win._on_node_selected(a.id)
        assert win._sidebar._title_edit.text() == "Task A"
        win.close()

    def test_ctrl_g_triggers_edit_external(self, tmp_beans_dir, store, qtbot, monkeypatch):
        """Ctrl+G should trigger external editor for body."""
        a = api.create_bean(store, "Task A")
        store.close()
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        win.show()
        qtbot.waitUntil(lambda: len(win._beans) > 0, timeout=2000)
        win._on_node_selected(a.id)

        called = []
        monkeypatch.setattr(win._sidebar, "_on_edit_external", lambda: called.append(True))

        # Simulate physical Ctrl+G (Qt uses MetaModifier for Ctrl on macOS)
        import sys
        mod = Qt.KeyboardModifier.MetaModifier if sys.platform == "darwin" else Qt.KeyboardModifier.ControlModifier
        qtbot.keyPress(win, Qt.Key.Key_G, mod)
        assert called, "Ctrl+G should trigger _on_edit_external"
        win.close()

    def test_cancel_unsaved_reverts_highlight_to_original_node(
        self, tmp_beans_dir, store, qtbot, monkeypatch
    ):
        """Bug fix: cancelling unsaved-changes dialog should revert highlight
        back to node A, not leave node B highlighted."""
        a = api.create_bean(store, "Task A")
        b = api.create_bean(store, "Task B")
        store.close()
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        win.show()
        qtbot.waitUntil(lambda: len(win._beans) > 0, timeout=2000)

        # Select node A and edit its title
        win._scene._on_node_clicked(a.id)
        win._sidebar._title_edit.setText("Task A edited")

        # Monkeypatch dialog to return Cancel
        from PySide6.QtWidgets import QMessageBox
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **kw: QMessageBox.StandardButton.Cancel,
        )

        # Click node B — should be rejected by cancel
        win._scene._on_node_clicked(b.id)

        # After cancel: node A should still be selected/highlighted, not B
        assert win._scene.selected_id == a.id
        assert win._scene._nodes[a.id].isSelected()
        assert not win._scene._nodes[b.id].isSelected()
        assert win._sidebar._title_edit.text() == "Task A edited"
        win.close()

    def test_clicking_same_node_with_edits_does_not_prompt(
        self, tmp_beans_dir, store, qtbot, monkeypatch
    ):
        """Bug fix: clicking the already-selected node should not trigger
        the unsaved-changes dialog."""
        a = api.create_bean(store, "Task A")
        store.close()
        win = MainWindow(tmp_beans_dir)
        qtbot.addWidget(win)
        win.show()
        qtbot.waitUntil(lambda: len(win._beans) > 0, timeout=2000)

        # Select node A and edit its title
        win._scene._on_node_clicked(a.id)
        win._sidebar._title_edit.setText("Task A edited")

        # Monkeypatch dialog to blow up if called
        from PySide6.QtWidgets import QMessageBox
        dialog_called = False

        def fail_dialog(*args, **kwargs):
            nonlocal dialog_called
            dialog_called = True
            return QMessageBox.StandardButton.Cancel

        monkeypatch.setattr(QMessageBox, "question", fail_dialog)

        # Click node A again — should NOT trigger dialog
        win._scene._on_node_clicked(a.id)

        assert not dialog_called
        # Edits should be preserved
        assert win._sidebar._title_edit.text() == "Task A edited"
        win.close()
