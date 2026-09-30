"""Client validation and panel-scale normalization for the UI readers."""
from functools import lru_cache

import cv2
import numpy as np

from utils.payload_data import read_payload_bytes

SUPPORTED_SIZES = ((2560, 1440), (1920, 1080), (1366, 768))
RESOLUTION_HELP = "Use 2560 x 1440 with Default Ratio (Filter Applied), or 1920 x 1080 or 1366 x 768 with Ideal Ratio."


def validate_frame(image):
    if image is None or image.ndim != 3 or image.shape[2] != 3 or (image.shape[1], image.shape[0]) not in SUPPORTED_SIZES:
        raise ValueError(RESOLUTION_HELP)


@lru_cache(maxsize=8)
def _reference(path):
    return cv2.imdecode(np.frombuffer(read_payload_bytes(path), np.uint8), cv2.IMREAD_GRAYSCALE)


def normalize_scan(image, mode):
    """Return a reader-sized UI and its cursor divisor for 1440p filtered ratio.

    Select scale from the requested panel, not the HUD: some game windows keep
    their native size. Do not resample the 1080p/768p paths. Previews, pointers,
    OCR and saved equipment icon crops all use the resulting coordinate system.
    """
    validate_frame(image)
    if image.shape[:2] != (1440, 2560):
        return image, 1
    if mode.startswith("shine:"):
        path = "images/window/scouter/erda_banner.png"
    elif mode == "equipment" or mode.startswith("hover:"):
        path = "images/window/equipment/windows_title.png"
    elif mode == "weapon":
        path = "images/window/equipment/currently_equipped.png"
    elif mode == "links":
        path = "images/window/scouter/links_applied.png"
    elif mode.startswith("hexa"):
        path = "images/window/scouter/hexa_title.png"
    else:
        path = "images/window/scouter/character.png"
    reference = _reference(path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Default Ratio (Filter Applied) stretches a 1366 x 768 UI to the client.
    # Its horizontal scale is slightly different from its vertical scale. A
    # uniform 1.875 divisor drifts across the window and damages small glyphs.
    filtered = cv2.resize(image, (1366, 768), interpolation=cv2.INTER_LINEAR)
    samples = (gray, cv2.cvtColor(filtered, cv2.COLOR_BGR2GRAY), gray[::2, ::2])
    scores = [float(cv2.matchTemplate(sample, reference, cv2.TM_CCOEFF_NORMED).max()) for sample in samples]
    best = int(np.argmax(scores))
    if best == 0 or scores[best] < .94:
        return image, 1
    if best == 1:
        if mode.startswith("hexa"):
            # Restore the tiny badge edges softened by the display filter.
            # The reader still requires exact digit glyphs, including zero;
            # uncertain badges continue to use the hover fallback.
            filtered = cv2.addWeighted(filtered, 2, cv2.GaussianBlur(filtered, (3, 3), .6), -1, 0)
        return filtered, (2560 / 1366, 1440 / 768)
    normalized = np.zeros_like(image)
    normalized[:720, :1280] = image[::2, ::2]
    return normalized, 2


def scan_point(point, scale):
    if point is None:
        return None
    sx, sy = scale if isinstance(scale, tuple) else (scale, scale)
    return int(point[0] / sx), int(point[1] / sy)
