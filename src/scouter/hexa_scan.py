"""Read HEXA skill levels from the HEXA Matrix screenshot."""

import re
from functools import lru_cache

import cv2
import numpy as np

from flaming.vision import ReadError
from scouter.vision import anchor
from utils.payload_data import read_payload_bytes, read_payload_json

# GMS matrix slots, relative to its title-bar origin. Core numbers follow the
# release order used by Scouter, not skill names (which differ between regions).
NODES = {
    "skillCore1": (222, 271),
    "skillCore2": (152, 271),
    "skillCore3": (187, 211),
    "masteryCore1": (320, 271),
    "masteryCore2": (355, 211),
    "masteryCore3": (425, 211),
    "masteryCore4": (460, 151),
    "reinCore1": (222, 415),
    "reinCore2": (187, 475),
    "reinCore3": (117, 475),
    "reinCore4": (82, 535),
    "generalCore2": (355, 475),
    "generalCore3": (425, 475),
    "solJanus": (320, 415),
}


def matrix_origin(frame, *, skill_tab=True):
    x, y = anchor(frame, "hexa_title")
    ox, oy = x - 20, y - 17
    if ox < 0 or oy < 0 or ox + 856 > frame.shape[1] or oy + 610 > frame.shape[0]:
        raise ReadError("HEXA Matrix is clipped; leave the full window visible")
    if not skill_tab:
        return ox, oy
    mx, my = anchor(frame, "hexa_material")
    if abs(mx - ox - 634) > 1 or abs(my - oy - 101) > 1:
        raise ReadError("HEXA Matrix layout changed or is obscured")
    sx, sy = anchor(frame, "hexa_skill_tab")
    if abs(sx - ox - 75) > 1 or abs(sy - oy - 59) > 1:
        raise ReadError("Open the HEXA Skill tab before scanning")
    return ox, oy


@lru_cache(maxsize=1)
def digit_glyphs():
    data = read_payload_json("images/window/scouter/hexa_digits.json")
    return {glyph: digit for digit, glyph in data["digits"].items()}


def badge_level(frame, x, y):
    # Exclude the oval rim. No substitutions, approximate matches, or inferred
    # zeros: even one unknown pixel sends this node to its tooltip reader.
    pixels = frame[y - 26 : y - 21, x - 9 : x + 9].min(axis=2) > 170
    columns = np.flatnonzero(pixels.any(axis=0))
    groups = np.split(columns, np.flatnonzero(np.diff(columns) > 1) + 1)
    if len(groups) != 2 or any(not len(group) for group in groups):
        raise ReadError("HEXA level badge is unreadable")
    digits = []
    for group in groups:
        glyph = pixels[:, group[0] : group[-1] + 1]
        key = f"{glyph.shape[1]}:" + "".join("1" if p else "0" for p in glyph.flat)
        if key not in digit_glyphs():
            raise ReadError("Unrecognized HEXA level digit")
        digits.append(digit_glyphs()[key])
    level = int("".join(digits))
    if not 0 <= level <= 30:
        raise ReadError("HEXA level is outside 0–30")
    return level


def locked(frame, x, y):
    reference = cv2.imdecode(
        np.frombuffer(read_payload_bytes("images/window/scouter/hexa_locked.png"), np.uint8),
        cv2.IMREAD_GRAYSCALE,
    )
    region = cv2.cvtColor(frame[y - 17 : y + 17, x - 13 : x + 13], cv2.COLOR_BGR2GRAY)
    return float(cv2.matchTemplate(region, reference, cv2.TM_CCOEFF_NORMED).max()) >= 0.98


def field(key):
    return "huntSkill.solJanus" if key == "solJanus" else "hexa." + key


def read_matrix(frame, reader=None):
    ox, oy = matrix_origin(frame)
    values, pending = {}, []
    for key, (dx, dy) in NODES.items():
        x, y = ox + dx, oy + dy
        try:
            is_locked = locked(frame, x, y)
            level = 0 if is_locked else badge_level(frame, x, y)
            values[field(key)] = {
                "value": str(level),
                "confidence": 1.0,
                "text": "Locked HEXA node" if is_locked else f"HEXA level {level:02d} (exact glyphs)",
            }
        except ReadError:
            pending.append(key)
    return {"kind": "scouter", "values": values, "pending": pending}


def read_hover(frame, reader, key):
    ox, oy = matrix_origin(frame)
    dx, dy = NODES[key]
    x, y = ox + dx, oy + dy
    # Retry this node's badge: the matrix may have been briefly covered by
    # another tooltip, including an unlearned node with no [Level] tooltip.
    try:
        level = 0 if locked(frame, x, y) else badge_level(frame, x, y)
        return {"kind": "scouter", "values": {field(key): {
            "value": str(level), "confidence": 1.0, "text": "HEXA node badge",
        }}}
    except ReadError:
        pass
    # The tooltip's level is below its description, beside the skill icon.
    # A narrow column excludes the miniature matrix levels and skill damage.
    region = frame[y + 40 : min(frame.shape[0], y + 400), x + 60 : x + 225]
    bright = region.min(axis=2) > 180
    occupied = np.flatnonzero(bright.sum(axis=1) >= 3)
    groups = np.split(occupied, np.flatnonzero(np.diff(occupied) > 3) + 1)
    crops = [region[max(0, int(g[0]) - 2) : int(g[-1]) + 3] for g in groups if 7 <= len(g) <= 16]
    matches = []
    for text, confidence in reader(crops) if crops else []:
        match = re.fullmatch(r"\[\s*Level\s+(\d{1,2})\s*\]", text.strip(), re.I)
        if match and confidence >= 0.97 and 1 <= int(match[1]) <= 30:
            matches.append({"value": str(int(match[1])), "confidence": confidence, "text": text})
    # A mastery node can describe two skills with the same shared level.
    levels = {match["value"] for match in matches}
    if len(levels) != 1:
        raise ReadError("Could not confidently read the HEXA tooltip level; saved level was left unchanged")
    return {"kind": "scouter", "values": {field(key): min(matches, key=lambda match: match["confidence"])}}
