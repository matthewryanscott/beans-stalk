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

    def test_lr_path_exits_right_enters_left(self, qapp):
        """In LR mode, edge exits right side of source and enters left side of target."""
        edge = DepEdge("a", "b")
        from_pos = QPointF(0, 0)
        from_size = (160, 40)
        to_pos = QPointF(300, 0)
        to_size = (160, 40)
        edge.update_path(
            from_pos, from_size, to_pos, to_size,
            from_port_frac=0.5, to_port_frac=0.5,
            direction="LR",
        )
        path = edge.path()
        assert not path.isEmpty()
        # Start point should be at right edge of source (x = 0 + 160 = 160)
        start_x = path.elementAt(0).x
        start_y = path.elementAt(0).y
        assert start_x == 160.0  # from_pos.x() + from_w
        # Y should be distributed along height: margin + (h - 2*margin) * 0.5
        from_margin = min(8, 40 * 0.1)
        expected_y = 0 + from_margin + (40 - 2 * from_margin) * 0.5
        assert start_y == expected_y
        # End point should be at left edge of target (x = 300)
        end_elem = path.elementAt(path.elementCount() - 1)
        assert end_elem.x == 300.0  # to_pos.x()
        to_margin = min(8, 40 * 0.1)
        expected_end_y = 0 + to_margin + (40 - 2 * to_margin) * 0.5
        assert end_elem.y == expected_end_y
