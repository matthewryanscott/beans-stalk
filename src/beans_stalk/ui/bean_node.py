from PySide6.QtCore import QRectF, Qt, Signal, QPointF, Property
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics
from PySide6.QtWidgets import QGraphicsObject, QStyleOptionGraphicsItem, QWidget
from beans.models import Bean

NODE_WIDTH = 160
NODE_HEIGHT = 40
CORNER_RADIUS = 8
PRIORITY_RADIUS = 6


class BeanNode(QGraphicsObject):
    clicked = Signal(str)

    def __init__(self, bean: Bean, color: str, muted: bool = False, parent=None):
        super().__init__(parent)
        self._bean = bean
        self._color = QColor(color)
        self._muted = muted
        self._hovered = False
        self.setAcceptHoverEvents(True)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setCacheMode(self.CacheMode.DeviceCoordinateCache)

    @property
    def bean(self) -> Bean:
        return self._bean

    @bean.setter
    def bean(self, value: Bean):
        self._bean = value
        self.update()

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool):
        self._muted = value
        self.update()

    def set_color(self, color: str):
        self._color = QColor(color)
        self.update()

    def _get_anim_pos(self) -> QPointF:
        return self.pos()

    def _set_anim_pos(self, pos: QPointF):
        self.setPos(pos)

    animPos = Property(QPointF, _get_anim_pos, _set_anim_pos)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, NODE_WIDTH, NODE_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill_color = QColor(self._color)
        if self._muted:
            fill_color.setAlphaF(0.3)
        if self._hovered and not self._muted:
            fill_color = fill_color.lighter(120)

        painter.setPen(QPen(fill_color.darker(130), 2))
        painter.setBrush(fill_color)
        painter.drawRoundedRect(QRectF(1, 1, NODE_WIDTH - 2, NODE_HEIGHT - 2), CORNER_RADIUS, CORNER_RADIUS)

        if self.isSelected():
            painter.setPen(QPen(Qt.GlobalColor.white, 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(1, 1, NODE_WIDTH - 2, NODE_HEIGHT - 2), CORNER_RADIUS, CORNER_RADIUS)

        text_color = Qt.GlobalColor.white if fill_color.lightnessF() < 0.5 else Qt.GlobalColor.black
        if self._muted:
            tc = QColor(text_color)
            tc.setAlphaF(0.5)
            text_color = tc
        painter.setPen(text_color)
        font = QFont("system-ui", 10)
        painter.setFont(font)
        text_rect = QRectF(8, 2, NODE_WIDTH - 24, NODE_HEIGHT - 4)
        elided = QFontMetrics(font).elidedText(self._bean.title, Qt.TextElideMode.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, elided)

        priority_colors = ["#ff4444", "#ff8800", "#ffcc00", "#88cc00", "#44aa44"]
        pc = QColor(priority_colors[self._bean.priority])
        if self._muted:
            pc.setAlphaF(0.3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(pc)
        painter.drawEllipse(QPointF(NODE_WIDTH - PRIORITY_RADIUS - 6, PRIORITY_RADIUS + 6), PRIORITY_RADIUS, PRIORITY_RADIUS)

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.clicked.emit(self._bean.id)
        super().mousePressEvent(event)
