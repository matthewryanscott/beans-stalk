#!/usr/bin/env python3
"""Render the DAG layout to a PNG using the actual Qt scene in headless mode."""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QApplication

from beans_stalk.config import StalkConfig
from beans_stalk.data.store import StalkStore
from beans_stalk.ui.dag_scene import DagScene


def main():
    beans_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".beans")
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/layout.png")

    _app = QApplication.instance() or QApplication(sys.argv)

    config = StalkConfig.load(beans_dir)
    store = StalkStore(beans_dir / "beans.db")
    beans, deps = store.load_snapshot()
    store.close()

    scene = DagScene(config)
    scene.show_completed = True  # Show all beans including closed
    scene.update_snapshot(beans, deps)

    # Compute bounding rect from node positions with margin for edges
    nodes = list(scene._nodes.values())
    if not nodes:
        print("No visible nodes")
        return

    min_x = min(n.pos().x() for n in nodes)
    max_x = max(n.pos().x() + n.boundingRect().width() for n in nodes)
    min_y = min(n.pos().y() for n in nodes)
    max_y = max(n.pos().y() + n.boundingRect().height() for n in nodes)

    margin = 60.0
    source_rect = QRectF(
        min_x - margin, min_y - margin,
        (max_x - min_x) + 2 * margin,
        (max_y - min_y) + 2 * margin,
    )

    # Scale so longest side = 1400px
    max_dim = max(source_rect.width(), source_rect.height())
    scale = 1400.0 / max_dim
    width = int(source_rect.width() * scale)
    height = int(source_rect.height() * scale)

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#1e1e1e"))

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Let scene.render handle the mapping from source_rect to target_rect
    target_rect = QRectF(0, 0, width, height)
    scene.render(painter, target_rect, source_rect)
    painter.end()

    image.save(str(output))
    print(f"Saved to {output} ({width}x{height})")
    print(f"  {len(beans)} beans total, scene has {len(scene._nodes)} visible nodes")
    print(f"  Source rect: {source_rect.x():.0f},{source_rect.y():.0f} "
          f"{source_rect.width():.0f}x{source_rect.height():.0f}")

    # Print node positions for debugging
    for _, node in sorted(scene._nodes.items(), key=lambda kv: (kv[1].pos().y(), kv[1].pos().x())):
        b = node.bean
        x, y = node.pos().x(), node.pos().y()
        print(f"  ({x:7.0f}, {y:7.0f})  {b.title[:45]}")


if __name__ == "__main__":
    main()
