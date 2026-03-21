from beans_stalk.ui.breadcrumb import BreadcrumbBar


class TestBreadcrumbBar:
    def test_initial_state_is_root(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        assert bar.current_parent_id is None
        assert len(bar._path) == 0

    def test_push_adds_segment(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "My Epic")
        assert bar.current_parent_id == "bean-001"
        assert len(bar._path) == 1

    def test_push_multiple(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "Epic")
        bar.push("bean-002", "Task")
        assert bar.current_parent_id == "bean-002"
        assert len(bar._path) == 2

    def test_pop_to_root(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "Epic")
        bar.push("bean-002", "Task")
        with qtbot.waitSignal(bar.navigate_to, timeout=1000) as blocker:
            bar.pop_to(None)
        assert blocker.args == [None]
        assert bar.current_parent_id is None
        assert len(bar._path) == 0

    def test_pop_to_mid_level(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "Epic")
        bar.push("bean-002", "Task")
        bar.push("bean-003", "Subtask")
        with qtbot.waitSignal(bar.navigate_to, timeout=1000) as blocker:
            bar.pop_to("bean-001")
        assert blocker.args == ["bean-001"]
        assert bar.current_parent_id == "bean-001"
        assert len(bar._path) == 1

    def test_clear_resets_to_root(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "Epic")
        bar.clear()
        assert bar.current_parent_id is None
        assert len(bar._path) == 0

    def test_button_click_emits_navigate(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "Epic")
        bar.push("bean-002", "Task")
        # Click the Root button (first button in layout)
        root_btn = bar._buttons[0]
        with qtbot.waitSignal(bar.navigate_to, timeout=1000) as blocker:
            root_btn.click()
        assert blocker.args == [None]

    def test_has_layout_combo(self, qtbot):
        from PySide6.QtWidgets import QComboBox

        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        assert hasattr(bar, "_layout_combo")
        assert isinstance(bar._layout_combo, QComboBox)

    def test_layout_combo_has_providers(self, qtbot):
        from beans_stalk.graph.layouts import PROVIDERS

        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        assert bar._layout_combo.count() == len(PROVIDERS)

    def test_layout_combo_emits_signal(self, qtbot):
        import pytest

        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        if bar._layout_combo.count() < 2:
            pytest.skip("Need at least 2 providers to test signal")
        with qtbot.waitSignal(bar.layout_changed, timeout=1000) as blocker:
            bar._layout_combo.setCurrentIndex(1)
        assert isinstance(blocker.args[0], str)

    def test_layout_combo_survives_rebuild(self, qtbot):
        from beans_stalk.graph.layouts import PROVIDERS

        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.push("bean-001", "Epic")  # triggers _rebuild
        assert bar._layout_combo.count() == len(PROVIDERS)

    def test_set_layout_algorithm(self, qtbot):
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.set_layout_algorithm("sugiyama_compact")
        assert bar._layout_combo.currentData() == "sugiyama_compact"
