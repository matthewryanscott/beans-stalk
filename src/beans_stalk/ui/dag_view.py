from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsView, QMenu

from beans_stalk.ui.dag_scene import DagScene
from beans_stalk.ui.bean_node import BeanNode
from beans_stalk.ui.dep_edge import DepEdge

MIN_ZOOM = 0.1
MAX_ZOOM = 10.0
ZOOM_FACTOR = 1.15


class DagView(QGraphicsView):
    new_bean_requested = Signal()
    new_child_requested = Signal(str)
    new_blocker_requested = Signal(str)
    new_blocked_by_requested = Signal(str)

    def __init__(self, scene: DagScene, parent=None):
        super().__init__(scene, parent)
        self._dag_scene = scene
        self._panning = False
        self._pan_start = QPointF()
        self._shift_dragging = False
        self._shift_drag_source: BeanNode | None = None

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grabGesture(Qt.GestureType.PinchGesture)

    def wheelEvent(self, event):
        factor = ZOOM_FACTOR if event.angleDelta().y() > 0 else 1 / ZOOM_FACTOR
        current = self.transform().m11()
        if MIN_ZOOM < current * factor < MAX_ZOOM:
            self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                item = self.itemAt(event.pos())
                if isinstance(item, BeanNode):
                    self._shift_dragging = True
                    self._shift_drag_source = item
                    event.accept()
                    return
                elif isinstance(item, DepEdge):
                    self._dag_scene.dep_remove_requested.emit(item.from_id, item.to_id)
                    event.accept()
                    return
            else:
                item = self.itemAt(event.pos())
                if item is None:
                    self._dag_scene.selected_id = None
                    self._panning = True
                    self._pan_start = event.position()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._panning:
                self._panning = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
                event.accept()
                return
            if self._shift_dragging and self._shift_drag_source is not None:
                self._shift_dragging = False
                item = self.itemAt(event.pos())
                if isinstance(item, BeanNode) and item is not self._shift_drag_source:
                    self._dag_scene.dep_toggle_requested.emit(self._shift_drag_source.bean.id, item.bean.id)
                self._shift_drag_source = None
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._dag_scene.selected_id = None
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        menu = QMenu(self)
        if isinstance(item, BeanNode):
            bean_id = item.bean.id
            menu.addAction("New child bean", lambda: self.new_child_requested.emit(bean_id))
            menu.addAction("New bean blocked by this", lambda: self.new_blocker_requested.emit(bean_id))
            menu.addAction("New bean that blocks this", lambda: self.new_blocked_by_requested.emit(bean_id))
        else:
            menu.addAction("New bean", lambda: self.new_bean_requested.emit())
        menu.exec(event.globalPos())
