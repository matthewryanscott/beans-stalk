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
