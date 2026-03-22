import math
from datetime import datetime, timezone

from PySide6.QtCore import QPointF, QEasingCurve, QPropertyAnimation, Signal
from PySide6.QtWidgets import QGraphicsScene, QGraphicsTextItem
from PySide6.QtGui import QColor, QFont

from beans.models import Bean, Dep
from beans_stalk.ui.bean_node import BeanNode, _compute_node_size
from beans_stalk.ui.dep_edge import DepEdge
from beans_stalk.config import StalkConfig
from beans_stalk.graph.layout import build_dag, stabilize_layout
from beans_stalk.graph.layouts import get_provider

ANIMATION_DURATION_MS = 300


class DagScene(QGraphicsScene):
    node_clicked = Signal(str)
    selection_cleared = Signal()
    navigate_requested = Signal(object)
    dep_toggle_requested = Signal(str, str)
    dep_remove_requested = Signal(str, str)
    delete_requested = Signal(str)

    def __init__(self, config: StalkConfig, store=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._store = store
        self._nodes: dict[str, BeanNode] = {}
        self._edges: dict[tuple[str, str], DepEdge] = {}
        self._positions: dict[str, tuple[float, float]] = {}
        self._selected_id: str | None = None
        self._show_completed = False
        self._fade_minutes = config.fade_minutes
        self._placeholder: QGraphicsTextItem | None = None
        self._current_parent_id: str | None = None
        self._parent_ids: set[str] = set()
        self._layout_algorithm = "sugiyama"

    @property
    def layout_algorithm(self) -> str:
        return self._layout_algorithm

    @layout_algorithm.setter
    def layout_algorithm(self, key: str):
        self._layout_algorithm = key

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

        if value is None:
            self.selection_cleared.emit()

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

        # Precompute parent_ids (beans that have children) and child counts
        self._parent_ids = set()
        child_counts: dict[str, int] = {}
        for bean in beans:
            if bean.parent_id is not None:
                self._parent_ids.add(bean.parent_id)
                child_counts[bean.parent_id] = child_counts.get(bean.parent_id, 0) + 1

        # Precompute ready set: open beans with no open blockers
        blocked_ids: set[str] = set()
        for dep in deps:
            if dep.dep_type == "blocks":
                blocker = all_beans.get(dep.from_id)
                blocked = all_beans.get(dep.to_id)
                if blocker and blocked and blocker.status != "closed" and blocked.status != "closed":
                    blocked_ids.add(dep.to_id)
        ready_ids: set[str] = set()
        for bean in beans:
            if bean.status != "closed" and bean.id not in blocked_ids:
                ready_ids.add(bean.id)

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
        provider = get_provider(self._layout_algorithm)
        new_positions = provider.compute(graph, visible_ids, node_sizes=node_sizes)
        new_positions = stabilize_layout(new_positions, self._positions, self._selected_id)

        # Placeholder
        if not visible_beans:
            if self._current_parent_id is not None:
                self._show_placeholder("All children are closed")
            else:
                self._show_placeholder()
        else:
            self._hide_placeholder()

        # Compute ready state from store
        try:
            ready_ids = self._store.ready_bean_ids() if self._store else set()
        except Exception:
            ready_ids = set()

        # Compute child counts
        child_counts: dict[str, int] = {}
        for bean in beans:
            if bean.parent_id is not None:
                child_counts[bean.parent_id] = child_counts.get(bean.parent_id, 0) + 1

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
            node.ready = (bean_id in ready_ids)
            node.child_count = child_counts.get(bean_id, 0)
            node.pulsing = (
                (bean.status == "in_progress" and bean.assignee is not None)
                or bean_id in active_ancestors
            )
            node.ready = (bean_id in ready_ids and not muted)
            node.child_count = child_counts.get(bean_id, 0)

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

        def _center_x(nid):
            if nid in new_positions:
                w = node_sizes.get(nid, (140, 40))[0]
                return new_positions[nid][0] + w / 2
            return 0

        def _center_y(nid):
            if nid in new_positions:
                h = node_sizes.get(nid, (140, 40))[1]
                return new_positions[nid][1] + h / 2
            return 0

        def _aim_frac(anchor_id, peer_id):
            """Compute a port fraction that aims the edge toward the peer node.

            Uses the angle from anchor to peer to determine the exit point.
            Edges to nodes directly below exit from center; edges to nodes
            far to the side exit from the corresponding edge.
            """
            anchor_cx = _center_x(anchor_id)
            peer_cx = _center_x(peer_id)
            dx = peer_cx - anchor_cx
            dy = abs(_center_y(peer_id) - _center_y(anchor_id))
            if dy < 1:
                dy = 1
            # atan2 gives the angle; scale so purely vertical = 0.5,
            # purely horizontal = 0.0 or 1.0
            angle = math.atan2(dx, dy)  # range [-pi/2, pi/2]
            # Map to [0, 1]: -pi/2 -> 0, 0 -> 0.5, pi/2 -> 1
            raw = 0.5 + angle / math.pi
            return max(0.0, min(1.0, raw))

        # For nodes with multiple edges, sort and spread ports to avoid crossing
        for src, targets in outgoing.items():
            targets.sort(key=lambda nid: _center_x(nid))
        for tgt, sources in incoming.items():
            sources.sort(key=lambda nid: _center_x(nid))

        def _spread_fracs(anchor_id, peer_ids):
            """Compute port fractions for multiple edges from/to one node.

            Uses aim-based fractions but ensures minimum spacing between
            adjacent ports, then re-sorts to prevent crossing.
            """
            n = len(peer_ids)
            if n == 0:
                return {}
            if n == 1:
                return {peer_ids[0]: _aim_frac(anchor_id, peer_ids[0])}
            # Compute aimed fracs (peer_ids already sorted by X)
            fracs = [_aim_frac(anchor_id, pid) for pid in peer_ids]
            # Enforce minimum spacing between adjacent ports
            min_gap = min(0.15, 0.8 / max(n - 1, 1))
            for i in range(1, n):
                if fracs[i] - fracs[i - 1] < min_gap:
                    fracs[i] = fracs[i - 1] + min_gap
            # If we exceeded [0, 1], shift everything back
            if fracs[-1] > 1.0:
                shift = fracs[-1] - 1.0
                fracs = [max(0.0, f - shift) for f in fracs]
            # Re-enforce spacing after shift
            for i in range(1, n):
                if fracs[i] - fracs[i - 1] < min_gap:
                    fracs[i] = fracs[i - 1] + min_gap
            return {pid: f for pid, f in zip(peer_ids, fracs)}

        out_fracs: dict[str, dict[str, float]] = {}
        for src, targets in outgoing.items():
            out_fracs[src] = _spread_fracs(src, targets)
        in_fracs: dict[str, dict[str, float]] = {}
        for tgt, sources in incoming.items():
            in_fracs[tgt] = _spread_fracs(tgt, sources)

        # Build list of node bounding rects for obstacle detection
        node_rects: list[tuple[str, float, float, float, float]] = []
        for nid in new_positions:
            nx, ny = new_positions[nid]
            nw, nh = node_sizes.get(nid, (140, 40))
            node_rects.append((nid, nx, ny, nw, nh))

        def _find_obstacle_side(from_id, to_id, from_frac, to_frac):
            """Check if an edge's bezier would pass through any intermediate node.

            Returns 'left', 'right', or None.
            """
            fx, fy = new_positions[from_id]
            fw, fh = node_sizes.get(from_id, (140, 40))
            tx, ty = new_positions[to_id]
            tw, _ = node_sizes.get(to_id, (140, 40))
            # Compute the bezier midpoint (approximate — use average of start/end X)
            from_margin = min(8, fw * 0.1)
            to_margin = min(8, tw * 0.1)
            start_x = fx + from_margin + (fw - 2 * from_margin) * from_frac
            end_x = tx + to_margin + (tw - 2 * to_margin) * to_frac
            mid_x = (start_x + end_x) / 2
            min_y = min(fy + fh, ty) + 5   # just below source bottom
            max_y = max(fy + fh, ty) - 5   # just above target top
            if min_y >= max_y:
                return None
            for nid, nx, ny, nw, nh in node_rects:
                if nid == from_id or nid == to_id:
                    continue
                # Check if node is vertically between source and target
                if ny + nh < min_y or ny > max_y:
                    continue
                # Check if the bezier midpoint X is within the node's horizontal span
                margin = 15  # extra clearance
                if nx - margin <= mid_x <= nx + nw + margin:
                    # Obstacle found — determine which side has more room
                    node_cx = nx + nw / 2
                    if mid_x <= node_cx:
                        return "left"   # edge is on left side of obstacle, push further left
                    else:
                        return "right"
            return None

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
                from_frac = out_fracs.get(dep.from_id, {}).get(dep.to_id, 0.5)
                to_frac = in_fracs.get(dep.to_id, {}).get(dep.from_id, 0.5)
                # Deflect edges that would pass through intermediate nodes
                side = _find_obstacle_side(dep.from_id, dep.to_id, from_frac, to_frac)
                if side == "left":
                    from_frac = min(from_frac, 0.1)
                    to_frac = min(to_frac, 0.1)
                elif side == "right":
                    from_frac = max(from_frac, 0.9)
                    to_frac = max(to_frac, 0.9)
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
        if bean_id == self._selected_id:
            return
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
