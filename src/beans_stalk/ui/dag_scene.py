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
    navigate_requested = Signal(object)
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
        self._current_parent_id: str | None = None
        self._parent_ids: set[str] = set()

    @property
    def current_parent_id(self) -> str | None:
        return self._current_parent_id

    @current_parent_id.setter
    def current_parent_id(self, value: str | None):
        self._current_parent_id = value

    @property
    def selected_id(self) -> str | None:
        return self._selected_id

    @selected_id.setter
    def selected_id(self, value: str | None):
        # Clear previous selection highlights
        if self._selected_id and self._selected_id in self._nodes:
            self._nodes[self._selected_id].setSelected(False)
        for node in self._nodes.values():
            node.highlighted = False
        for edge in self._edges.values():
            edge.highlighted = False

        self._selected_id = value

        if value and value in self._nodes:
            self._nodes[value].setSelected(True)
            # Highlight connected edges and neighbor nodes
            for edge in self._edges.values():
                if edge.from_id == value or edge.to_id == value:
                    edge.highlighted = True
                    neighbor_id = edge.to_id if edge.from_id == value else edge.from_id
                    if neighbor_id in self._nodes:
                        self._nodes[neighbor_id].highlighted = True

    @property
    def show_completed(self) -> bool:
        return self._show_completed

    @show_completed.setter
    def show_completed(self, value: bool):
        self._show_completed = value

    def update_snapshot(self, beans: list[Bean], deps: list[Dep]):
        now = datetime.now(timezone.utc)

        # Index all beans by id
        all_beans: dict[str, Bean] = {bean.id: bean for bean in beans}

        # Precompute parent_ids (beans that have children)
        self._parent_ids = set()
        for bean in beans:
            if bean.parent_id is not None:
                self._parent_ids.add(bean.parent_id)

        # Precompute active ancestors: walk up from in_progress+assigned beans
        active_ancestors: set[str] = set()
        for bean in beans:
            if bean.status == "in_progress" and bean.assignee is not None:
                # Walk up parent chain
                cur = bean.parent_id
                while cur is not None:
                    if cur in active_ancestors:
                        break
                    active_ancestors.add(cur)
                    parent_bean = all_beans.get(cur)
                    cur = parent_bean.parent_id if parent_bean else None

        # Filter beans at the current level (parent_id == current_parent_id)
        level_beans: dict[str, Bean] = {}
        for bean in beans:
            if bean.parent_id == self._current_parent_id:
                level_beans[bean.id] = bean

        # Find ghost IDs: direct deps from/to level beans that aren't in level beans
        ghost_ids: set[str] = set()
        for dep in deps:
            if dep.from_id in level_beans and dep.to_id not in level_beans and dep.to_id in all_beans:
                ghost_ids.add(dep.to_id)
            if dep.to_id in level_beans and dep.from_id not in level_beans and dep.from_id in all_beans:
                ghost_ids.add(dep.from_id)

        # Also include edges between ghosts (if both endpoints are ghosts)
        # These are deps where both from and to are in ghost_ids

        # Build visible_beans from level_beans + ghost beans, applying closed filtering
        visible_beans: dict[str, tuple[Bean, bool]] = {}
        candidate_ids = set(level_beans.keys()) | ghost_ids
        for bean_id in candidate_ids:
            bean = all_beans[bean_id]
            if bean.status == "closed":
                if self._show_completed:
                    visible_beans[bean_id] = (bean, True)
                elif bean.closed_at and self._is_recently_closed(bean.closed_at, now):
                    visible_beans[bean_id] = (bean, True)
            else:
                visible_beans[bean_id] = (bean, False)

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
            if self._current_parent_id is not None:
                self._show_placeholder("All children are closed")
            else:
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

            node.ghost = (bean_id in ghost_ids)
            node.pulsing = (
                (bean.status == "in_progress" and bean.assignee is not None)
                or bean_id in active_ancestors
            )

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

        # Compute port fractions: spread edge attachment points across each node
        # Group outgoing edges per source, sorted by target X
        # Group incoming edges per target, sorted by source X
        from collections import defaultdict
        outgoing: dict[str, list[str]] = defaultdict(list)  # source -> [targets]
        incoming: dict[str, list[str]] = defaultdict(list)  # target -> [sources]
        for dep in deps:
            key = (dep.from_id, dep.to_id)
            if key in current_dep_keys:
                outgoing[dep.from_id].append(dep.to_id)
                incoming[dep.to_id].append(dep.from_id)

        # Sort each group by the connected node's X position
        def _center_x(nid):
            if nid in new_positions:
                w = node_sizes.get(nid, (140, 40))[0]
                return new_positions[nid][0] + w / 2
            return 0

        for src, targets in outgoing.items():
            targets.sort(key=_center_x)
        for tgt, sources in incoming.items():
            sources.sort(key=_center_x)

        def _port_frac(index: int, total: int) -> float:
            if total <= 1:
                return 0.5
            return index / (total - 1)

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
                out_list = outgoing[dep.from_id]
                in_list = incoming[dep.to_id]
                from_frac = _port_frac(out_list.index(dep.to_id), len(out_list))
                to_frac = _port_frac(in_list.index(dep.from_id), len(in_list))
                edge.update_path(
                    QPointF(*new_positions[dep.from_id]),
                    node_sizes.get(dep.from_id, (140, 40)),
                    QPointF(*new_positions[dep.to_id]),
                    node_sizes.get(dep.to_id, (140, 40)),
                    from_port_frac=from_frac,
                    to_port_frac=to_frac,
                )

        self._positions = new_positions

    def _is_recently_closed(self, closed_at: datetime, now: datetime) -> bool:
        elapsed = (now - closed_at).total_seconds() / 60
        return elapsed < self._fade_minutes

    def _on_node_clicked(self, bean_id: str):
        self.selected_id = bean_id
        self.node_clicked.emit(bean_id)

    def _show_placeholder(self, message="No beans yet \u2014 create one with Cmd-N or right-click"):
        if self._placeholder is not None:
            self.removeItem(self._placeholder)
        self._placeholder = QGraphicsTextItem(message)
        self._placeholder.setDefaultTextColor(QColor("#888888"))
        self._placeholder.setFont(QFont("system-ui", 14))
        self.addItem(self._placeholder)

    def _hide_placeholder(self):
        if self._placeholder is not None:
            self.removeItem(self._placeholder)
            self._placeholder = None
