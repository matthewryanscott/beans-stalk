from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from beans.models import Bean, BeanId
from beans_stalk.ui.bean_node import BeanNode

def _bean(title="Test", status="open", assignee=None, priority=2):
    return Bean(id=BeanId.generate(), title=title, status=status, assignee=assignee, priority=priority)

class TestBeanNode:
    def test_bounding_rect(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        rect = node.boundingRect()
        assert rect.width() >= 140  # NODE_MIN_WIDTH
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
