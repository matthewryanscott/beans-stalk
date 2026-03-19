from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from beans.models import Bean, BeanId
from beans_stalk.ui.bean_node import BeanNode, NODE_WIDTH, NODE_HEIGHT

def _bean(title="Test", status="open", assignee=None, priority=2):
    return Bean(id=BeanId.generate(), title=title, status=status, assignee=assignee, priority=priority)

class TestBeanNode:
    def test_bounding_rect(self, qapp):
        node = BeanNode(_bean(), "#e06c75")
        rect = node.boundingRect()
        assert rect.width() == NODE_WIDTH
        assert rect.height() == NODE_HEIGHT

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
