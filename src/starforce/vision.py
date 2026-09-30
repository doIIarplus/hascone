"""Count filled and empty Star Force glyphs in an anchored item tooltip."""

from functools import lru_cache

import cv2
import numpy as np

from flaming.item_tooltip import level_anchor
from flaming.vision import ReadError
from utils.payload_data import read_payload_bytes


def gold(image):
    b, g, r = cv2.split(image)
    return ((r > 225) & (g > 165) & (b < 95)).astype(np.uint8) * 255


@lru_cache(maxsize=1)
def templates():
    result = []
    for name in ("filled", "empty"):
        data = read_payload_bytes(f"images/window/equipment/starforce/{name}.png")
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ReadError("Star Force reference image is unavailable")
        result.append(gold(frame) if name == "filled" else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    return result


def positions(cap):
    result = []
    for row, count in enumerate((min(15, cap), max(0, cap - 15))):
        if not count:
            continue
        width = 11 * (count - 1) + 10 * ((count - 1) // 5) + 9
        left = (325 - width) // 2
        result.extend((left + 11 * i + 10 * (i // 5), row * 18) for i in range(count))
    return result


def read(frame):
    x, y, _, _ = level_anchor(frame)
    if x < 15 or x + 308 > frame.shape[1]:
        raise ReadError("Star Force tooltip is clipped")
    crop = frame[max(0, y - 350) : y - 90, x - 15 : x + 308]
    if crop.shape[0] < 30:
        raise ReadError("Star Force tooltip header is clipped")
    full, blank = templates()
    filled = cv2.matchTemplate(gold(crop), full, cv2.TM_CCOEFF_NORMED)
    empty = cv2.matchTemplate(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), blank, cv2.TM_CCOEFF_NORMED)
    candidates = []
    # Caps are not only the level bands, e.g. a Thousand Soul Talisman draws 26 slots.
    for cap in range(5, 31):
        points = positions(cap)
        height = filled.shape[0] - max(dy for _, dy in points)
        scores = np.array(
            [np.maximum(filled[dy : dy + height, px], empty[dy : dy + height, px]) for px, dy in points]
        )
        valid = np.array(
            [
                (filled[dy : dy + height, px] >= 0.88) | (empty[dy : dy + height, px] >= 0.72)
                for px, dy in points
            ]
        )
        for top in np.flatnonzero(valid.all(axis=0)):
            states = [filled[top + dy, px] >= 0.88 for px, dy in points]
            count = int(sum(states))
            if states != [True] * count + [False] * (cap - count):
                continue
            # Reject a smaller layout fitting only a subset of a longer row.
            expected = {(px, top + dy) for px, dy in points}
            ys = {top + dy for _, dy in points}
            ys.update(py for py in (top - 18, top + 18) if 0 <= py < filled.shape[0])
            actual = {
                (int(px), int(py))
                for py in ys
                for px in np.flatnonzero((filled[py] >= 0.88) | (empty[py] >= 0.72))
            }
            if actual - expected:
                continue
            candidates.append((count, cap, float(scores[:, top].min())))
    if not candidates:
        raise ReadError("Could not verify the complete Star Force row; hover the item again")
    meanings = {count for count, _, _ in candidates}
    if len(meanings) != 1:
        raise ReadError("Star Force tooltip is ambiguous")
    count, cap, confidence = max(candidates, key=lambda c: (c[1], c[2]))
    return {
        "status": "scanned",
        "stars": count,
        "max_stars": cap,
        "confidence": confidence,
        "source": "tooltip",
    }
