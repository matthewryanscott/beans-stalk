from PySide6.QtCore import Qt
from beans_stalk.config import StalkConfig
from beans_stalk.ui.dag_scene import DagScene
from beans_stalk.ui.dag_view import DagView


class TestDagView:
    def test_creates_with_scene(self, qapp):
        scene = DagScene(StalkConfig())
        view = DagView(scene)
        assert view.scene() is scene

    def test_scroll_bars_hidden(self, qapp):
        scene = DagScene(StalkConfig())
        view = DagView(scene)
        assert view.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert view.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    def test_escape_deselects(self, qtbot):
        scene = DagScene(StalkConfig())
        view = DagView(scene)
        qtbot.addWidget(view)
        scene.selected_id = "some-id"
        qtbot.keyPress(view, Qt.Key.Key_Escape)
        assert scene.selected_id is None

    def test_signals_exist(self, qapp):
        scene = DagScene(StalkConfig())
        view = DagView(scene)
        assert hasattr(view, "new_bean_requested")
        assert hasattr(view, "new_child_requested")
        assert hasattr(view, "new_blocker_requested")
        assert hasattr(view, "new_blocked_by_requested")
