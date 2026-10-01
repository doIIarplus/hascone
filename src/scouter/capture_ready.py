"""Cheap panel checks used before handing character captures to background OCR."""

import numpy as np

from flaming.stats import ReadError
from game_resolution import validate_frame
from scouter.vision import _overview_crops, anchor, applied_anchor, origin, verify_hover


def regions(frame, mode, point, info):
    validate_frame(frame)
    if mode.startswith("shine:"):
        from scouter.shine_scan import panel
        _, slug, position = mode.split(":")
        if slug != info["slug"]:
            raise ReadError("Select the matching SHINE character before scanning.")
        x, y, _, _ = panel(frame, position)
        if point is not None and x <= point[0] < x + 284 and y + 40 <= point[1] < y + 277:
            raise ReadError("Move the cursor off the VI skill rows so their names and levels are visible.")
        return [frame[y:y + 277, x:x + 297]]
    if mode == "overview":
        ox, oy = origin(frame)
        sx, sy = anchor(frame, "stats_panel")
        if not (ox < sx < ox + 460 and oy + 230 < sy < oy + 260):
            raise ReadError("Expand Details and keep the full stats panel visible.")
        return _overview_crops(frame, ox, oy)[1]
    if mode.startswith("tooltip:"):
        stat = {"mainStat": info["main"], "subStat": info["sub"], "ssubStat": info.get("sub2"),
                "atk": "MATT" if info["main"] == "INT" else "ATT"}[mode.split(":")[1]]
        verify_hover(frame, point, stat)
        x, y = applied_anchor(frame)
        return [frame[y:y + 80, x - 2:x + 252]]
    if mode == "links":
        from scouter.link_scan import links_origin
        x, y = links_origin(frame)
        return [frame[y + 281:y + 552, x + 475:x + 1445]]
    if mode == "weapon":
        from equipment_scan import hovered_slot, tooltip_bounds
        if hovered_slot(frame, point) != "weapon":
            raise ReadError("Hover your equipped weapon.")
        x, y, bottom = tooltip_bounds(frame, allow_clipped_footer=True)
        return [frame[y:bottom, x:x + 310]]
    from scouter.hexa_scan import NODES, matrix_origin
    x, y = matrix_origin(frame)
    if mode.startswith("hexa_hover:"):
        dx, dy = NODES[mode.split(":")[1]]
        if point is None or abs(point[0] - x - dx) > 30 or abs(point[1] - y - dy) > 30:
            raise ReadError("Hover the requested HEXA node.")
    return [frame[y:y + 610, x:x + 856]]


def stable(first, second):
    if len(first) != len(second) or any(
        not a.size or a.shape != b.shape or np.mean(np.abs(a.astype(float) - b.astype(float))) > 2
        for a, b in zip(first, second)
    ):
        raise ReadError("Panel is changing. Hold still while it finishes drawing.")
