from PySide6.QtCore import QPointF
from beans_stalk.ui.dep_edge import DepEdge

class TestDepEdge:
    def test_stores_ids(self, qapp):
        edge = DepEdge("bean-00000001", "bean-00000002")
        assert edge.from_id == "bean-00000001"
        assert edge.to_id == "bean-00000002"

    def test_update_path_creates_valid_path(self, qapp):
        edge = DepEdge("a", "b")
        edge.update_path(QPointF(0, 0), (160, 40), QPointF(0, 200), (160, 40))
        assert not edge.path().isEmpty()

    def test_shape_is_wider_than_path(self, qapp):
        edge = DepEdge("a", "b")
        edge.update_path(QPointF(0, 0), (160, 40), QPointF(0, 200), (160, 40))
        assert edge.shape().boundingRect().width() > edge.path().boundingRect().width()

    def test_z_value_is_negative(self, qapp):
        edge = DepEdge("a", "b")
        assert edge.zValue() < 0
