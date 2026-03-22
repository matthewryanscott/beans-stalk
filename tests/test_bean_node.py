from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor
from beans.models import Bean, BeanId
from beans_stalk.ui.bean_node import BeanNode

def _bean(title="Test", status="open", assignee=None, priority=2):
    return Bean(id=BeanId.generate(), title=title, status=status, assignee=assignee, priority=priority)

class TestBeanNode:
    def test_bounding_rect(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        rect = node.boundingRect()
        assert rect.width() >= 120  # NODE_MIN_WIDTH
        assert rect.height() > 0

    def test_long_title_wraps(self, qapp):
        node = BeanNode(_bean(title="This is a very long task title that should wrap"), "#e06c75")
        short_node = BeanNode(_bean(title="Short"), "#e06c75")
        assert node.node_height >= short_node.node_height

    def test_click_emits_signal(self, qtbot):
        bean = _bean()
        node = BeanNode(bean, "#e06c75")
        with qtbot.waitSignal(node.clicked, timeout=1000) as blocker:
            node.clicked.emit(bean.id)
        assert blocker.args == [bean.id]

    def test_muted_property(self, qapp):
        node = BeanNode(_bean(), "#e06c75", muted=False)
        assert not node.muted
        node.muted = True
        assert node.muted

    def test_set_color(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.set_color("#61afef")
        assert node._color == QColor("#61afef")

    def test_bean_property_update(self, qapp):
        bean = _bean(title="Original")
        node = BeanNode(bean, "#e06c75")
        assert node.bean.title == "Original"
        node.bean = _bean(title="Updated")
        assert node.bean.title == "Updated"

    def test_anim_pos_property(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.animPos = QPointF(100, 200)
        assert node.pos() == QPointF(100, 200)


class TestBeanNodeGhost:
    def test_ghost_default_false(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        assert not node.ghost

    def test_ghost_property(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.ghost = True
        assert node.ghost

    def test_ghost_sets_pointing_hand_cursor(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.ghost = True
        assert node.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_ghost_clears_cursor(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.ghost = True
        node.ghost = False
        assert node.cursor().shape() == Qt.CursorShape.ArrowCursor


class TestBeanNodeReady:
    def test_ready_default_false(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        assert not node.ready

    def test_ready_setter(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.ready = True
        assert node.ready
        node.ready = False
        assert not node.ready


class TestBeanNodePulsing:
    def test_pulsing_default_false(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        assert not node.pulsing

    def test_pulsing_property(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.pulsing = True
        assert node.pulsing

    def test_pulsing_changes_cache_mode(self, qapp):
        from PySide6.QtWidgets import QGraphicsItem
        node = BeanNode(_bean(), "#e06c75")
        assert node.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache
        node.pulsing = True
        assert node.cacheMode() == QGraphicsItem.CacheMode.NoCache
        node.pulsing = False
        assert node.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_pulse_phase_property(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        node.pulsePhase = 0.5
        assert node.pulsePhase == 0.5
