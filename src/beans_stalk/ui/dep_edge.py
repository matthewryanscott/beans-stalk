from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPainterPathStroker, QPen, QColor, QPolygonF
from PySide6.QtWidgets import QGraphicsPathItem
from beans_stalk.ui.bean_node import NODE_WIDTH, NODE_HEIGHT

ARROW_SIZE = 8
EDGE_COLOR = "#aaaaaa"
EDGE_HOVER_COLOR = "#ffffff"


class DepEdge(QGraphicsPathItem):
    def __init__(self, from_id: str, to_id: str, parent=None):
        super().__init__(parent)
        self.from_id = from_id
        self.to_id = to_id
        self._hovered = False
        self.setPen(QPen(QColor(EDGE_COLOR), 1.5))
        self.setAcceptHoverEvents(True)
        self.setZValue(-1)

    def update_path(self, from_pos: QPointF, to_pos: QPointF):
        start = QPointF(from_pos.x() + NODE_WIDTH / 2, from_pos.y() + NODE_HEIGHT)
        end = QPointF(to_pos.x() + NODE_WIDTH / 2, to_pos.y())
        dy = abs(end.y() - start.y()) / 2
        ctrl1 = QPointF(start.x(), start.y() + dy)
        ctrl2 = QPointF(end.x(), end.y() - dy)
        path = QPainterPath(start)
        path.cubicTo(ctrl1, ctrl2, end)
        self.setPath(path)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(EDGE_HOVER_COLOR if self._hovered else EDGE_COLOR)
        width = 2.5 if self._hovered else 1.5
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
