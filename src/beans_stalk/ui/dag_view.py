from PySide6.QtCore import Qt, QPointF, QEvent, QMarginsF, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsView, QMenu

from beans_stalk.ui.dag_scene import DagScene
from beans_stalk.ui.bean_node import BeanNode
from beans_stalk.ui.dep_edge import DepEdge

MIN_ZOOM = 0.1
MAX_ZOOM = 10.0


class DagView(QGraphicsView):
    new_bean_requested = Signal()
    new_child_requested = Signal(str)
    new_blocker_requested = Signal(str)
    new_blocked_by_requested = Signal(str)
    view_in_new_window_requested = Signal(str)

    def __init__(self, scene: DagScene, parent=None):
        super().__init__(scene, parent)
        self._dag_scene = scene
        self._panning = False
        self._pan_start = QPointF()
        self._shift_dragging = False
        self._shift_drag_source: BeanNode | None = None
        self.locked = False  # when True, only panning/zooming allowed

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grabGesture(Qt.GestureType.PinchGesture)

    def update_scene_rect(self):
        """Set scene rect to graph bounds + half-viewport padding.

        This allows centering any part of the graph in the viewport
        while preventing panning so far that the graph disappears.
        """
        items_rect = self.scene().itemsBoundingRect()
        if items_rect.isEmpty():
            return
        vp = self.viewport().rect()
        # Pad by half viewport size so any graph corner can reach viewport center
        pad_x = vp.width() / 2 / self.transform().m11() if self.transform().m11() > 0 else 0
        pad_y = vp.height() / 2 / self.transform().m11() if self.transform().m11() > 0 else 0
        padded = items_rect.marginsAdded(QMarginsF(pad_x, pad_y, pad_x, pad_y))
        self.setSceneRect(padded)

    def resizeEvent(self, event):
        """Update scene rect padding when viewport size changes."""
        super().resizeEvent(event)
        self.update_scene_rect()

    def wheelEvent(self, event):
        """Scroll wheel scrolls the viewport — no zoom."""
        super().wheelEvent(event)

    def event(self, event):
        """Handle gesture events for pinch-to-zoom."""
        if event.type() == QEvent.Type.Gesture:
            return self._gesture_event(event)
        return super().event(event)

    def _gesture_event(self, event):
        """Handle pinch gesture for smooth zoom."""
        gesture = event.gesture(Qt.GestureType.PinchGesture)
        if gesture:
            if gesture.state() == Qt.GestureState.GestureUpdated:
                scale_factor = gesture.scaleFactor()
                current_scale = self.transform().m11()
                if (current_scale * scale_factor < MIN_ZOOM and scale_factor < 1) or \
                   (current_scale * scale_factor > MAX_ZOOM and scale_factor > 1):
                    return True
                self.scale(scale_factor, scale_factor)
                self.update_scene_rect()
            return True
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.locked and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
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
                if item is None or self.locked:
                    if not self.locked:
                        self._dag_scene.selected_id = None
                    self._panning = True
                    self._pan_start = event.position()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    event.accept()
                    return
                if not self.locked:
                    super().mousePressEvent(event)
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
        if event.key() == Qt.Key.Key_Escape and not self.locked:
            self._dag_scene.selected_id = None
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.locked:
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if isinstance(item, BeanNode):
                if item.ghost:
                    # Navigate to ghost's home view (its parent level)
                    self._dag_scene.navigate_requested.emit(item.bean.parent_id)
                elif item.bean.id in self._dag_scene._parent_ids:
                    # Drill into parent's children
                    self._dag_scene.navigate_requested.emit(item.bean.id)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def get_viewport_state(self) -> dict[str, float]:
        """Return current center (scene coords) and scale."""
        center = self.mapToScene(self.viewport().rect().center())
        scale = self.transform().m11()
        return {"center_x": center.x(), "center_y": center.y(), "scale": scale}

    def restore_viewport_state(self, state: dict[str, float]) -> None:
        """Restore center and scale from saved state."""
        scale = state.get("scale", 1.0)
        current_scale = self.transform().m11()
        if current_scale > 0:
            factor = scale / current_scale
            self.scale(factor, factor)
        self.centerOn(state.get("center_x", 0.0), state.get("center_y", 0.0))

    def contextMenuEvent(self, event):
        if self.locked:
            event.accept()
            return
        item = self.itemAt(event.pos())
        menu = QMenu(self)
        if isinstance(item, BeanNode):
            bean_id = item.bean.id
            menu.addAction("View in new window", lambda: self.view_in_new_window_requested.emit(bean_id))
            menu.addSeparator()
            menu.addAction("New child bean", lambda: self.new_child_requested.emit(bean_id))
            menu.addAction("New bean blocked by this", lambda: self.new_blocker_requested.emit(bean_id))
            menu.addAction("New bean that blocks this", lambda: self.new_blocked_by_requested.emit(bean_id))
        else:
            menu.addAction("New bean", lambda: self.new_bean_requested.emit())
        menu.exec(event.globalPos())
