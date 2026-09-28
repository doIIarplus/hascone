"""Read the required-level row of an equipped item's hover tooltip."""

import re

import cv2
import numpy as np

from flaming.vision import ReadError
from utils.payload_data import read_payload_bytes


def level_anchor(frame):
    # Threshold the translucent background away, retaining the native glyphs.
    def mask(image):
        return (image.min(axis=2) > 105).astype(np.uint8) * 255

    # Linux's font differs from the Windows reference. Keep both exact glyph
    # templates instead of relaxing the match threshold for unrelated text.
    results = []
    for filename in ("required_level.png", "required_level_linux.png"):
        anchor = cv2.imdecode(
            np.frombuffer(read_payload_bytes("images/window/equipment/" + filename), np.uint8),
            cv2.IMREAD_COLOR,
        )
        if anchor is None:
            raise ReadError("Could not decode the Required Level reference image")
        results.append(cv2.matchTemplate(mask(frame), mask(anchor), cv2.TM_CCOEFF_NORMED))
    result = np.maximum.reduce(results)
    _, quality, _, (x, y) = cv2.minMaxLoc(result)
    if quality < 0.95:
        raise ReadError("Required Level tooltip label is not visible")
    # A comparison tooltip can show a second item. Never choose between two.
    result[max(0, y - 3) : y + 4, max(0, x - 3) : x + 4] = 0
    if result.max() >= 0.95:
        raise ReadError("Multiple Required Level tooltips are visible")
    return x, y, anchor.shape[1], anchor.shape[0]


def parse_level(text):
    match = re.fullmatch(r"\s*Lv\.?\s*(\d{1,3})(?:\s*\(\s*(\d{1,3})\s*-\s*(\d{1,3})\s*\))?\s*", text, re.I)
    if not match:
        raise ReadError("Unrecognized Required Level number")
    effective = int(match[1])
    base = int(match[2]) if match[2] else effective
    if not 1 <= effective <= base <= 300 or (match[3] and base - int(match[3]) != effective):
        raise ReadError("Required Level reduction does not add up")
    return base
