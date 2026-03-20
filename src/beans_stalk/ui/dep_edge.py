from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPainterPathStroker, QPen, QColor, QPolygonF
from PySide6.QtWidgets import QGraphicsPathItem

ARROW_SIZE = 8
EDGE_COLOR = "#666666"
EDGE_HOVER_COLOR = "#ffffff"
EDGE_HIGHLIGHT_COLOR = "#cccccc"


class DepEdge(QGraphicsPathItem):
    def __init__(self, from_id: str, to_id: str, parent=None):
        super().__init__(parent)
        self.from_id = from_id
        self.to_id = to_id
        self._hovered = False
        self._highlighted = False
        self.setPen(QPen(QColor(EDGE_COLOR), 1.5))
        self.setAcceptHoverEvents(True)
        self.setZValue(-1)

    @property
    def highlighted(self) -> bool:
        return self._highlighted

    @highlighted.setter
    def highlighted(self, value: bool):
        self._highlighted = value
        self.setZValue(0 if value else -1)  # highlighted edges draw above others
        self.update()

    def update_path(self, from_pos: QPointF, from_size: tuple[float, float],
                    to_pos: QPointF, to_size: tuple[float, float],
                    from_port_frac: float = 0.5, to_port_frac: float = 0.5):
        """Update bezier path with distributed attachment points.

        port_frac: 0.0 = left edge, 0.5 = center, 1.0 = right edge of node.
        """
        from_w, from_h = from_size
        to_w, _ = to_size
        # Inset ports slightly from edges for visual margin
        from_margin = min(8, from_w * 0.1)
        to_margin = min(8, to_w * 0.1)
        from_x = from_pos.x() + from_margin + (from_w - 2 * from_margin) * from_port_frac
        to_x = to_pos.x() + to_margin + (to_w - 2 * to_margin) * to_port_frac
        start = QPointF(from_x, from_pos.y() + from_h)
        end = QPointF(to_x, to_pos.y())
        dy = abs(end.y() - start.y()) / 2
        ctrl1 = QPointF(start.x(), start.y() + dy)
        ctrl2 = QPointF(end.x(), end.y() - dy)
        path = QPainterPath(start)
        path.cubicTo(ctrl1, ctrl2, end)
        self.setPath(path)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hovered:
            color = QColor(EDGE_HOVER_COLOR)
            width = 2.5
        elif self._highlighted:
            color = QColor(EDGE_HIGHLIGHT_COLOR)
            width = 2.0
        else:
            color = QColor(EDGE_COLOR)
            width = 1.5
        painter.setPen(QPen(color, width))
        painter.drawPath(self.path())
        path = self.path()
        if path.elementCount() < 2:
            return
        end = QPointF(
            path.elementAt(path.elementCount() - 1).x,
            path.elementAt(path.elementCount() - 1).y,
        )
        prev = QPointF(
            path.elementAt(path.elementCount() - 2).x,
            path.elementAt(path.elementCount() - 2).y,
        )
        dx = end.x() - prev.x()
        dy = end.y() - prev.y()
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return
        dx /= length
        dy /= length
        p1 = QPointF(
            end.x() - ARROW_SIZE * dx + ARROW_SIZE * 0.5 * dy,
            end.y() - ARROW_SIZE * dy - ARROW_SIZE * 0.5 * dx,
        )
        p2 = QPointF(
            end.x() - ARROW_SIZE * dx - ARROW_SIZE * 0.5 * dy,
            end.y() - ARROW_SIZE * dy + ARROW_SIZE * 0.5 * dx,
        )
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygonF([end, p1, p2]))

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self.path())
