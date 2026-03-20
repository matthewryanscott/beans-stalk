from datetime import datetime, timezone

from PySide6.QtCore import QPointF, QEasingCurve, QPropertyAnimation, Signal
from PySide6.QtWidgets import QGraphicsScene, QGraphicsTextItem
from PySide6.QtGui import QColor, QFont

from beans.models import Bean, Dep
from beans_stalk.ui.bean_node import BeanNode, _compute_node_size
from beans_stalk.ui.dep_edge import DepEdge
from beans_stalk.config import StalkConfig
from beans_stalk.graph.layout import build_dag, compute_layout, stabilize_layout

ANIMATION_DURATION_MS = 300


class DagScene(QGraphicsScene):
    node_clicked = Signal(str)
    dep_toggle_requested = Signal(str, str)
    dep_remove_requested = Signal(str, str)

    def __init__(self, config: StalkConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._nodes: dict[str, BeanNode] = {}
        self._edges: dict[tuple[str, str], DepEdge] = {}
        self._positions: dict[str, tuple[float, float]] = {}
        self._selected_id: str | None = None
        self._show_completed = False
        self._fade_minutes = config.fade_minutes
        self._placeholder: QGraphicsTextItem | None = None

    @property
    def selected_id(self) -> str | None:
        return self._selected_id

    @selected_id.setter
    def selected_id(self, value: str | None):
        if self._selected_id and self._selected_id in self._nodes:
            self._nodes[self._selected_id].setSelected(False)
        self._selected_id = value
        if value and value in self._nodes:
            self._nodes[value].setSelected(True)

    @property
    def show_completed(self) -> bool:
        return self._show_completed

    @show_completed.setter
    def show_completed(self, value: bool):
        self._show_completed = value

    def update_snapshot(self, beans: list[Bean], deps: list[Dep]):
        now = datetime.now(timezone.utc)

        # Determine visible beans
        visible_beans: dict[str, tuple[Bean, bool]] = {}
        for bean in beans:
            if bean.status == "closed":
                if self._show_completed:
                    visible_beans[bean.id] = (bean, True)
                elif bean.closed_at and self._is_recently_closed(bean.closed_at, now):
                    visible_beans[bean.id] = (bean, True)
            else:
                visible_beans[bean.id] = (bean, False)

        # Precompute node sizes for layout spacing
        node_sizes = {
            bean_id: _compute_node_size(bean.title)
            for bean_id, (bean, _muted) in visible_beans.items()
        }

        # Build DAG and compute layout
        graph = build_dag(beans, deps)
        visible_ids = set(visible_beans.keys())
        new_positions = compute_layout(graph, visible_ids, node_sizes=node_sizes)
        new_positions = stabilize_layout(new_positions, self._positions, self._selected_id)

        # Placeholder
        if not visible_beans:
            self._show_placeholder()
        else:
            self._hide_placeholder()

        # Remove old nodes
        for bean_id in list(self._nodes.keys()):
            if bean_id not in visible_beans:
                self.removeItem(self._nodes.pop(bean_id))

        # Add/update nodes with animation
        for bean_id, (bean, muted) in visible_beans.items():
            color = self._config.get_color(bean.assignee)
            if bean_id in self._nodes:
                node = self._nodes[bean_id]
                node.bean = bean
                node.muted = muted
                node.set_color(color)
            else:
                node = BeanNode(bean, color, muted=muted)
                node.clicked.connect(self._on_node_clicked)
                self._nodes[bean_id] = node
                self.addItem(node)

            if bean_id in new_positions:
                target = QPointF(*new_positions[bean_id])
                if bean_id in self._positions:
                    anim = QPropertyAnimation(node, b"animPos")
                    anim.setDuration(ANIMATION_DURATION_MS)
                    anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
                    anim.setStartValue(node.pos())
                    anim.setEndValue(target)
                    anim.start()
                    node._current_anim = anim
                else:
                    node.setPos(target)

        # Remove old edges
        current_dep_keys = set()
        for dep in deps:
            if dep.from_id in visible_beans and dep.to_id in visible_beans:
                current_dep_keys.add((dep.from_id, dep.to_id))

        for key in list(self._edges.keys()):
            if key not in current_dep_keys:
                self.removeItem(self._edges.pop(key))

        # Add/update edges
        for dep in deps:
            key = (dep.from_id, dep.to_id)
            if key not in current_dep_keys:
                continue
            if key not in self._edges:
                edge = DepEdge(dep.from_id, dep.to_id)
                self._edges[key] = edge
                self.addItem(edge)
            edge = self._edges[key]
            if dep.from_id in new_positions and dep.to_id in new_positions:
                edge.update_path(
                    QPointF(*new_positions[dep.from_id]),
                    node_sizes.get(dep.from_id, (140, 40)),
                    QPointF(*new_positions[dep.to_id]),
                    node_sizes.get(dep.to_id, (140, 40)),
                )

        self._positions = new_positions

    def _is_recently_closed(self, closed_at: datetime, now: datetime) -> bool:
        elapsed = (now - closed_at).total_seconds() / 60
        return elapsed < self._fade_minutes

    def _on_node_clicked(self, bean_id: str):
        self.selected_id = bean_id
        self.node_clicked.emit(bean_id)

    def _show_placeholder(self):
        if self._placeholder is not None:
            return
        self._placeholder = QGraphicsTextItem(
            "No beans yet \u2014 create one with Cmd-N or right-click"
        )
        self._placeholder.setDefaultTextColor(QColor("#888888"))
        self._placeholder.setFont(QFont("system-ui", 14))
        self.addItem(self._placeholder)

    def _hide_placeholder(self):
        if self._placeholder is not None:
            self.removeItem(self._placeholder)
            self._placeholder = None
