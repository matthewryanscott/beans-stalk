from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from beans.models import Bean
from beans_stalk.config import StalkConfig
from beans_stalk.ui.dag_scene import DagScene
from beans_stalk.ui.dag_view import DagView
from beans_stalk.ui.bean_node import BeanNode

DRAG_THRESHOLD = 5


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

    def test_get_viewport_state(self, qtbot):
        scene = DagScene(StalkConfig())
        view = DagView(scene)
        qtbot.addWidget(view)
        view.show()
        state = view.get_viewport_state()
        assert "center_x" in state
        assert "center_y" in state
        assert "scale" in state
        assert isinstance(state["scale"], float)

    def test_restore_viewport_state(self, qtbot):
        scene = DagScene(StalkConfig())
        view = DagView(scene)
        qtbot.addWidget(view)
        view.show()
        state = {"center_x": 100.0, "center_y": 200.0, "scale": 1.5}
        view.restore_viewport_state(state)
        result = view.get_viewport_state()
        assert abs(result["scale"] - 1.5) < 0.01

    def test_viewport_roundtrip(self, qtbot):
        scene = DagScene(StalkConfig())
        view = DagView(scene)
        qtbot.addWidget(view)
        view.show()
        view.restore_viewport_state({"center_x": 50.0, "center_y": -30.0, "scale": 2.0})
        state = view.get_viewport_state()
        assert abs(state["scale"] - 2.0) < 0.01

    def test_drag_on_node_pans_without_selecting(self, qtbot):
        """Dragging on a node should pan the view, not select the node."""
        config = StalkConfig()
        scene = DagScene(config)
        view = DagView(scene)
        qtbot.addWidget(view)
        view.show()
        view.resize(800, 600)

        bean = Bean(id="bean-1", title="Drag Me", status="open", type="task",
                    priority=2, body="")
        node = BeanNode(bean, "#336699")
        scene.addItem(node)
        node.setPos(100, 100)

        node_center = view.mapFromScene(node.sceneBoundingRect().center())

        clicked_ids = []
        scene.node_clicked.connect(lambda bid: clicked_ids.append(bid))

        # Press on node, drag beyond threshold, release
        qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton,
                         pos=node_center)
        drag_end = node_center + QPointF(DRAG_THRESHOLD + 20, 0).toPoint()
        qtbot.mouseMove(view.viewport(), pos=drag_end)
        qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton,
                           pos=drag_end)

        assert clicked_ids == []
        assert scene.selected_id is None

    def test_click_on_node_selects(self, qtbot):
        """A simple click (no drag) on a node should select it."""
        config = StalkConfig()
        scene = DagScene(config)
        view = DagView(scene)
        qtbot.addWidget(view)
        view.show()
        view.resize(800, 600)

        bean = Bean(id="bean-1", title="Click Me", status="open", type="task",
                    priority=2, body="")
        node = BeanNode(bean, "#336699")
        scene.addItem(node)
        node.setPos(100, 100)

        node_center = view.mapFromScene(node.sceneBoundingRect().center())

        clicked_ids = []
        scene.node_clicked.connect(lambda bid: clicked_ids.append(bid))

        # Click (press + release at same spot)
        qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                         pos=node_center)

        assert clicked_ids == ["bean-1"]

    def test_click_empty_space_deselects(self, qtbot):
        """Clicking empty space should deselect."""
        config = StalkConfig()
        scene = DagScene(config)
        view = DagView(scene)
        qtbot.addWidget(view)
        view.show()
        view.resize(800, 600)

        bean = Bean(id="bean-1", title="Node", status="open", type="task",
                    priority=2, body="")
        node = BeanNode(bean, "#336699")
        scene.addItem(node)
        node.setPos(100, 100)
        scene.selected_id = "bean-1"

        # Click on empty space (far from node)
        empty_pos = view.mapFromScene(QPointF(500, 500))
        qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                         pos=empty_pos)

        assert scene.selected_id is None

    def test_trackpad_scroll_moves_both_axes(self, qtbot):
        """Two-finger trackpad pan with diagonal pixelDelta should scroll both axes."""
        config = StalkConfig()
        scene = DagScene(config)
        view = DagView(scene)
        qtbot.addWidget(view)
        view.show()
        view.resize(800, 600)

        # Add a node so scene rect is non-trivial
        bean = Bean(id="bean-1", title="Node", status="open", type="task",
                    priority=2, body="")
        node = BeanNode(bean, "#336699")
        scene.addItem(node)
        node.setPos(0, 0)
        view.update_scene_rect()

        before_h = view.horizontalScrollBar().value()
        before_v = view.verticalScrollBar().value()

        # Simulate a trackpad scroll with diagonal pixelDelta
        center = view.viewport().rect().center()
        wheel_event = QWheelEvent(
            QPointF(center),
            view.viewport().mapToGlobal(center),
            QPoint(-30, -20),                      # pixelDelta — diagonal
            QPoint(-30, -20),                      # angleDelta
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        view.wheelEvent(wheel_event)

        after_h = view.horizontalScrollBar().value()
        after_v = view.verticalScrollBar().value()

        # Both axes should have moved
        assert after_h != before_h, "horizontal scroll should have changed"
        assert after_v != before_v, "vertical scroll should have changed"

    def test_delete_key_emits_delete_requested(self, qtbot):
        """Pressing Delete with a node selected emits delete_requested."""
        config = StalkConfig()
        scene = DagScene(config)
        view = DagView(scene)
        qtbot.addWidget(view)
        view.show()

        bean = Bean(id="bean-1", title="Delete Me", status="open", type="task",
                    priority=2, body="")
        node = BeanNode(bean, "#336699")
        scene.addItem(node)
        scene._nodes["bean-1"] = node
        scene.selected_id = "bean-1"

        deleted_ids = []
        scene.delete_requested.connect(lambda bid: deleted_ids.append(bid))

        qtbot.keyPress(view, Qt.Key.Key_Delete)

        assert deleted_ids == ["bean-1"]

    def test_delete_key_noop_on_ghost(self, qtbot):
        """Pressing Delete on a ghost node should not emit delete_requested."""
        config = StalkConfig()
        scene = DagScene(config)
        view = DagView(scene)
        qtbot.addWidget(view)
        view.show()

        bean = Bean(id="bean-1", title="Ghost", status="open", type="task",
                    priority=2, body="")
        node = BeanNode(bean, "#336699")
        node.ghost = True
        scene.addItem(node)
        scene._nodes["bean-1"] = node
        scene.selected_id = "bean-1"

        deleted_ids = []
        scene.delete_requested.connect(lambda bid: deleted_ids.append(bid))

        qtbot.keyPress(view, Qt.Key.Key_Delete)

        assert deleted_ids == []

    def test_delete_key_noop_when_locked(self, qtbot):
        """Pressing Delete when view is locked should not emit delete_requested."""
        config = StalkConfig()
        scene = DagScene(config)
        view = DagView(scene)
        qtbot.addWidget(view)
        view.show()
        view.locked = True

        bean = Bean(id="bean-1", title="Locked", status="open", type="task",
                    priority=2, body="")
        node = BeanNode(bean, "#336699")
        scene.addItem(node)
        scene._nodes["bean-1"] = node
        scene.selected_id = "bean-1"

        deleted_ids = []
        scene.delete_requested.connect(lambda bid: deleted_ids.append(bid))

        qtbot.keyPress(view, Qt.Key.Key_Delete)

        assert deleted_ids == []
