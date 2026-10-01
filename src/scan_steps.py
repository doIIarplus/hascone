"""Capture-side scan steps: screenshots and quick image checks, no OCR.

The desktop app runs these in the scanner process (see scan_worker), so OpenCV
and Windows.Graphics.Capture load only while scanning. Each step returns only
the frame it accepted; frames it rejects never leave the scanner.
"""

import base64
import time


def _frame(body):
    """A reader-sized client frame and its cursor divisor."""
    import capture
    from game_resolution import normalize_scan

    return normalize_scan(capture.frame(body["window"]), body["mode"])


def _pointer(body, scale):
    import capture
    from game_resolution import scan_point

    return scan_point(capture.pointer(body["window"]), scale)


def hover_step(body):
    """Look once for a hovered item's finished tooltip: (slot, frame, icons).

    "hover:any" accepts whichever of body["slots"] is hovered, in any order.
    """
    import capture
    from equipment_scan import hover_capture_ready, hover_icon, hover_target
    from game_resolution import scan_point

    requested = body["mode"].split(":")[1]
    slots = body["slots"] if requested == "any" else [requested]
    # Check one frame cheaply; only a promising one gets a second frame.
    raw_pointer = capture.pointer(body["window"])
    first, scale = _frame(body)
    slot, origin, bounds = hover_target(first, scan_point(raw_pointer, scale), slots)
    second, scale = _frame(body)
    hover_capture_ready(first, second, slot, origin, bounds, _pointer(body, scale))
    return slot, second, {slot: hover_icon(second)}


def character_step(body, info):
    """Two matching frames of a character panel: (frame, HEXA matrix or None)."""
    from scouter import capture_ready

    first, scale = _frame(body)
    crops = capture_ready.regions(first, body["mode"], _pointer(body, scale), info)
    time.sleep(0.15)
    second, scale = _frame(body)
    capture_ready.stable(crops, capture_ready.regions(second, body["mode"], _pointer(body, scale), info))
    if body["mode"] == "hexa":
        from scouter.hexa_scan import read_matrix

        return second, read_matrix(second)
    return second, None


def acquire(body):
    """The frame to read, from the game or an uploaded screenshot: (image, pointer, scale).

    Hover steps check that the expected slot stayed hovered across the capture.
    """
    from game_resolution import normalize_scan, scan_point

    if body.get("image"):
        import cv2
        import numpy as np

        image = cv2.imdecode(
            np.frombuffer(base64.b64decode(body["image"], validate=True), dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        image, scale = normalize_scan(image, body["mode"])
        return image, None, scale
    import capture

    mode = body["mode"]
    raw_pointer = capture.pointer(body["window"]) if mode.startswith(("hover:", "tooltip:")) else None
    image, scale = _frame(body)
    before_pointer = scan_point(raw_pointer, scale)
    if mode.startswith("hover:"):
        from equipment_scan import hovered_slot

        expected = mode.split(":")[1]
        if hovered_slot(image, before_pointer) != expected or hovered_slot(image, _pointer(body, scale)) != expected:
            raise ValueError("Hover your " + expected.replace("_", " ") + " in Equipment.")
    return image, before_pointer, scale


def verify(body, image, before_pointer, info):
    """Check, after reading IMAGE, that the cursor is still on the requested item or stat row."""
    mode = body["mode"]
    pointer = _pointer(body, body.get("_scan_scale", 1))
    if mode.startswith("hover:"):
        from equipment_scan import hovered_slot

        expected = mode.split(":")[1]
        if hovered_slot(image, pointer) != expected:
            raise ValueError("The cursor moved before the reading finished. Hold it over " + expected + ".")
    elif mode.startswith("tooltip:"):
        from scouter.vision import verify_hover

        stat = {"mainStat": info["main"], "subStat": info["sub"], "ssubStat": info.get("sub2"),
                "atk": "MATT" if info["main"] == "INT" else "ATT"}[mode.split(":")[1]]
        verify_hover(image, before_pointer, stat)
        verify_hover(image, pointer, stat)
    elif mode == "weapon":
        from equipment_scan import hovered_slot

        if hovered_slot(image, pointer) != "weapon":
            raise ValueError("Hover your equipped weapon.")


def render(image, mode, result):
    """The review preview as PNG, and for gear the icons that saving it stores."""
    from utils.image_files import encode_png

    icons = {}
    if mode == "equipment" or mode.startswith("hover:"):
        from equipment_scan import icons as cut_icons

        icons = cut_icons(image, result)
    return encode_png(image), icons
