from PySide6.QtCore import QRectF, Qt, Signal, QPointF, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics
from PySide6.QtWidgets import QGraphicsObject, QStyleOptionGraphicsItem, QWidget
from beans.models import Bean

NODE_MIN_WIDTH = 120
NODE_MAX_WIDTH = 200
NODE_PADDING_H = 8
NODE_PADDING_V = 5
PRIORITY_COL_WIDTH = 16  # space reserved for priority dot on right
CORNER_RADIUS = 6
PRIORITY_RADIUS = 5
LINE_HEIGHT_FACTOR = 1.15
NODE_FONT = QFont("system-ui", 10)
READY_BORDER_COLOR = "#4fc1ff"


CHILD_COUNT_LINE_HEIGHT = 10  # extra height when showing child count indicator


def _compute_node_size(title: str, has_children: bool = False) -> tuple[float, float]:
    """Compute node width and height based on title, allowing up to 2 lines."""
    fm = QFontMetrics(NODE_FONT)
    chrome = NODE_PADDING_H * 2 + PRIORITY_COL_WIDTH
    text_avail_max = NODE_MAX_WIDTH - chrome
    full_width = fm.horizontalAdvance(title)

    if full_width <= text_avail_max:
        # Single line fits — size to content
        width = max(NODE_MIN_WIDTH, full_width + chrome)
        height = fm.height() + NODE_PADDING_V * 2
    else:
        # Need 2 lines — find the narrowest width where the title wraps into 2 lines
        # by trying to balance the two lines (target ~half the text width)
        target_text_w = full_width / 2
        # Find the actual break point width — measure each word prefix
        words = title.split()
        best_text_w = text_avail_max
        for i in range(1, len(words)):
            line1 = " ".join(words[:i])
            w = fm.horizontalAdvance(line1)
            if w >= target_text_w:
                # Also measure the second line to pick the more balanced split
                line2 = " ".join(words[i:])
                best_text_w = max(w, fm.horizontalAdvance(line2))
                break

        line_height = int(fm.height() * LINE_HEIGHT_FACTOR)
        height = line_height * 2 + NODE_PADDING_V * 2
        width = min(NODE_MAX_WIDTH, max(NODE_MIN_WIDTH, best_text_w + chrome))

    if has_children:
        height += CHILD_COUNT_LINE_HEIGHT
    return width, height


def _wrap_title(title: str, max_width: int) -> list[str]:
    """Split title into up to 2 lines, eliding the second if needed."""
    fm = QFontMetrics(NODE_FONT)
    if fm.horizontalAdvance(title) <= max_width:
        return [title]

    # Find break point for first line — try word boundaries
    words = title.split()
    line1 = ""
    for i, word in enumerate(words):
        candidate = f"{line1} {word}".strip()
        if fm.horizontalAdvance(candidate) > max_width and line1:
            break
        line1 = candidate
    else:
        # All words fit on one line (shouldn't happen but be safe)
        return [title]

    remainder = " ".join(words[i:])
    line2 = fm.elidedText(remainder, Qt.TextElideMode.ElideRight, max_width)
    return [line1, line2]


class BeanNode(QGraphicsObject):
    clicked = Signal(str)

    def __init__(self, bean: Bean, color: str, muted: bool = False, parent=None):
        super().__init__(parent)
        self._bean = bean
        self._color = QColor(color)
        self._muted = muted
        self._ghost = False
        self._ready = False
        self._child_count = 0
        self._open_child_count = 0
        self._active_child_count = 0  # in_progress children
        self._pulsing = False
        self._pulse_phase = 0.0
        self._pulse_anim: QPropertyAnimation | None = None
        self._hovered = False
        self._highlighted = False
        self._width, self._height = _compute_node_size(bean.title)
        self.setAcceptHoverEvents(True)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setCacheMode(self.CacheMode.DeviceCoordinateCache)

    @property
    def node_width(self) -> float:
        return self._width

    @property
    def node_height(self) -> float:
        return self._height

    @property
    def bean(self) -> Bean:
        return self._bean

    @bean.setter
    def bean(self, value: Bean):
        self._bean = value
        self._recompute_size()

    def _recompute_size(self):
        self._width, self._height = _compute_node_size(
            self._bean.title, has_children=self._child_count > 0
        )
        self.prepareGeometryChange()
        self.update()

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool):
        self._muted = value
        self.update()

    @property
    def highlighted(self) -> bool:
        return self._highlighted

    @highlighted.setter
    def highlighted(self, value: bool):
        self._highlighted = value
        self.update()

    @property
    def child_count(self) -> int:
        return self._child_count

    @child_count.setter
    def child_count(self, value: int):
        had_children = self._child_count > 0
        self._child_count = value
        if (value > 0) != had_children:
            self._recompute_size()
        else:
            self.update()

    @property
    def open_child_count(self) -> int:
        return self._open_child_count

    @open_child_count.setter
    def open_child_count(self, value: int):
        self._open_child_count = value
        self.update()

    @property
    def active_child_count(self) -> int:
        return self._active_child_count

    @active_child_count.setter
    def active_child_count(self, value: int):
        self._active_child_count = value
        self.update()

    @property
    def ghost(self) -> bool:
        return self._ghost

    @ghost.setter
    def ghost(self, value: bool):
        self._ghost = value
        if value:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    @property
    def ready(self) -> bool:
        return self._ready

    @ready.setter
    def ready(self, value: bool):
        self._ready = value
        self.update()

    @property
    def pulsing(self) -> bool:
        return self._pulsing

    @pulsing.setter
    def pulsing(self, value: bool):
        if self._pulsing == value:
            return
        self._pulsing = value
        if value:
            self.setCacheMode(self.CacheMode.NoCache)
            self._pulse_anim = QPropertyAnimation(self, b"pulsePhase")
            self._pulse_anim.setDuration(1500)
            self._pulse_anim.setStartValue(0.0)
            self._pulse_anim.setEndValue(1.0)
            self._pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
            self._pulse_anim.setLoopCount(-1)
            self._pulse_anim.start()
        else:
            if self._pulse_anim is not None:
                self._pulse_anim.stop()
                self._pulse_anim = None
            self._pulse_phase = 0.0
            self.setCacheMode(self.CacheMode.DeviceCoordinateCache)
        self.update()

    def _get_pulse_phase(self) -> float:
        return self._pulse_phase

    def _set_pulse_phase(self, value: float):
        self._pulse_phase = value
        self.update()

    pulsePhase = Property(float, _get_pulse_phase, _set_pulse_phase)

    def set_color(self, color: str):
        self._color = QColor(color)
        self.update()

    def _get_anim_pos(self) -> QPointF:
        return self.pos()

    def _set_anim_pos(self, pos: QPointF):
        self.setPos(pos)

    animPos = Property(QPointF, _get_anim_pos, _set_anim_pos)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, self._height)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self._width, self._height
        fill_color = QColor(self._color)
        if self._muted:
            fill_color.setAlphaF(0.3)
        if self._highlighted and not self._muted:
            fill_color = fill_color.lighter(115)
        if self._hovered and not self._muted:
            fill_color = fill_color.lighter(120)

        border_width = 2.0
        if self._pulsing:
            border_width = 2.0 + 2.0 * self._pulse_phase

        if self._ghost:
            fill_color.setAlphaF(0.2)
            painter.setPen(QPen(fill_color.darker(130), border_width, Qt.PenStyle.DashLine))
        elif self._ready and not self._muted:
            painter.setPen(QPen(QColor(READY_BORDER_COLOR), max(border_width, 2.5)))
        else:
            painter.setPen(QPen(fill_color.darker(130), border_width))
        painter.setBrush(fill_color)
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), CORNER_RADIUS, CORNER_RADIUS)

        if self.isSelected():
            painter.setPen(QPen(Qt.GlobalColor.white, 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), CORNER_RADIUS, CORNER_RADIUS)

        # Use perceived luminance for contrast
        r, g, b = self._color.redF(), self._color.greenF(), self._color.blueF()
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        text_color = Qt.GlobalColor.black if luminance > 0.55 else Qt.GlobalColor.white
        if self._ghost:
            tc = QColor(text_color)
            tc.setAlphaF(0.4)
            text_color = tc
        elif self._muted:
            tc = QColor(text_color)
            tc.setAlphaF(0.5)
            text_color = tc
        painter.setPen(text_color)
        painter.setFont(NODE_FONT)

        text_max_width = int(w - NODE_PADDING_H * 2 - PRIORITY_COL_WIDTH)
        lines = _wrap_title(self._bean.title, text_max_width)
        fm = QFontMetrics(NODE_FONT)
        line_height = int(fm.height() * LINE_HEIGHT_FACTOR)
        total_text_height = line_height * len(lines)
        y_start = (h - total_text_height) / 2 + fm.ascent()

        for i, line in enumerate(lines):
            painter.drawText(
                QPointF(NODE_PADDING_H, y_start + i * line_height),
                line,
            )

        # Priority indicator
        if not self._ghost:
            priority_colors = ["#ff4444", "#ff8800", "#ffcc00", "#88cc00", "#44aa44"]
            pc = QColor(priority_colors[self._bean.priority])
            if self._muted:
                pc.setAlphaF(0.3)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(pc)
            painter.drawEllipse(
                QPointF(w - PRIORITY_RADIUS - 6, PRIORITY_RADIUS + 6),
                PRIORITY_RADIUS, PRIORITY_RADIUS,
            )

        # Child count indicator (below title, in extra row)
        if self._child_count > 0 and not self._ghost:
            child_font = QFont("system-ui", 8)
            parts = []
            if self._active_child_count > 0:
                parts.append(f"{self._active_child_count} active")
            if self._open_child_count > 0:
                parts.append(f"{self._open_child_count} open")
            closed = self._child_count - self._open_child_count - self._active_child_count
            if closed > 0:
                parts.append(f"{closed} closed")
            child_text = f"\u25B8 {self._child_count}: {', '.join(parts)}"
            tc = QColor(text_color)
            tc.setAlphaF(0.4)
            painter.setPen(tc)
            painter.setFont(child_font)
            painter.drawText(
                QPointF(NODE_PADDING_H, h - 5),
                child_text,
            )

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        # Selection and click handling are managed by DagView
        event.ignore()
