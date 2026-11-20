"""Read the Skills → VI (6th Job) list, without inferring levels from the Erda Link graph."""

import re
from functools import lru_cache

import cv2
import numpy as np

from flaming.stats import ReadError
from ocr_confidence import padded
from scouter.shine_levels import aliases, row_values
from scouter.vision import anchor
from utils.payload_data import read_payload_bytes

# Offsets from the "6th Job" header. The list scrolls by pixels, so row
# positions are found in each frame; only the columns and viewport are fixed.
COLUMNS = (2, 247)
CELL_W, CELL_H, PITCH = 240, 57, 61
VIEW_TOP, VIEW_BOTTOM = 39, 473
TRACK_X, TRACK_TOP, TRACK_LEN, THUMB_LEN = 494, 36, 436, 28
WIDTH = 500


@lru_cache(maxsize=8)
def reference(name):
    return cv2.imdecode(np.frombuffer(read_payload_bytes(f"images/window/scouter/{name}.png"), np.uint8), 1)


def panel(frame, position=None):
    try:
        x, y = anchor(frame, "vi_header")
    except ReadError as exc:
        raise ReadError("Open Skills → VI and keep the full 6th Job skill list visible.") from exc
    if x < 0 or y < 0 or x + WIDTH > frame.shape[1] or y + VIEW_BOTTOM > frame.shape[0]:
        raise ReadError("Keep the full VI skill list visible.")
    track = frame[y + TRACK_TOP:y + TRACK_TOP + TRACK_LEN, x + TRACK_X:x + TRACK_X + 5]
    _, quality, _, (_, thumb_y) = cv2.minMaxLoc(cv2.matchTemplate(track, reference("vi_scroll"), cv2.TM_CCOEFF_NORMED))
    if quality >= .9:
        top, bottom = thumb_y <= 1, thumb_y >= TRACK_LEN - THUMB_LEN - 1
    elif track.min() > 205:
        top = bottom = True  # The whole list fits, so there is no scroll thumb.
    else:
        raise ReadError("Move the cursor and tooltips away from the VI skill list and scrollbar.")
    if position == "top" and not top:
        raise ReadError("Scroll the VI skill list all the way to the top.")
    if position == "bottom" and not bottom:
        raise ReadError("Scroll the VI skill list all the way to the bottom.")
    return x, y, top, bottom


def row_tops(frame, x, y):
    """Frame Y of every fully visible row; partially scrolled rows are skipped."""
    view = frame[y + VIEW_TOP:y + VIEW_BOTTOM, x + COLUMNS[0]:x + COLUMNS[0] + 6]
    scores = np.maximum(*(cv2.matchTemplate(view, edge, cv2.TM_CCOEFF_NORMED)[:, 0]
                          for edge in (reference("vi_cell_edge"), reference("vi_empty_cell")[:, :6])))
    tops = [i for i, s in enumerate(scores) if s >= .9 and s == scores[max(0, i - 5):i + 6].max()]
    height = VIEW_BOTTOM - VIEW_TOP
    if (not tops or tops[0] >= PITCH or tops[-1] + PITCH + CELL_H <= height
            or any(not PITCH - 1 <= b - a <= PITCH + 1 for a, b in zip(tops, tops[1:]))):
        raise ReadError("VI skill list is obscured. Uncover every skill row before scanning.")
    return [y + VIEW_TOP + t for t in tops]


def _ink(crop):
    """Stretch light text on a darker fill, or dark text on a lighter fill, to white on black."""
    light = crop.min(axis=2).astype(np.float32)
    low, high = np.percentile(light, 5), light.max()
    text = np.clip((light - low) * 255 / max(1.0, high - low), 0, 255).astype(np.uint8)
    return cv2.cvtColor(text, cv2.COLOR_GRAY2BGR)


@lru_cache(maxsize=1)
def _level_images():
    """Every level 0–30 drawn from the outlined digit glyphs, with background on both sides.

    The trailing background stops "3" from matching the start of "30".
    """
    strip = reference("vi_digits").min(axis=2)
    glyphs = [strip[:, 8 * d:8 * d + 8] for d in range(10)]
    background = strip[:, 8:9]  # The blank first column of the "1" cell.
    return {n: np.hstack([background] * 3 + [glyphs[int(d)] for d in str(n)] + [background] * 4)
            for n in range(31)}


def current_level(cell):
    """Return (level, match score) for the bold current level before " / max"."""
    # Digits start 65 px into the cell; allow a few pixels of drift either way.
    region = cell[29:51, 59:89].min(axis=2)
    scores = sorted(((float(cv2.matchTemplate(region, image, cv2.TM_CCOEFF_NORMED)[:, :7].max()), n)
                     for n, image in _level_images().items()), reverse=True)
    (best, value), (second, _) = scores[:2]
    if best < .85 or best - second < .08:
        raise ReadError("VI skill level is unclear. Move the cursor and tooltips off the skill list.")
    return value, best


def cell_reading(frame, left, top):
    """(name crop for OCR, level from exact glyphs), or None for an empty slot."""
    cell = frame[top:top + CELL_H, left:left + CELL_W]
    if cell[8:10, 60:225].min(axis=2).mean() < 175:
        return _ink(cell[9:27, 58:229]), current_level(cell)[0]
    expected = reference("vi_empty_cell")
    if (cv2.matchTemplate(cell, expected, cv2.TM_CCOEFF_NORMED)[0, 0] < .94
            or np.abs(cell.astype(float) - expected).mean() > 12):
        raise ReadError("VI skill list is obscured. Uncover every skill row before scanning.")
    return None


def skill_name(text, names):
    def clean(value):
        return re.sub(r"[^a-z0-9]", "", value.casefold())

    value = clean(text)
    exact = {target for name, target in names.items() if clean(name) == value}
    if len(exact) == 1:
        return exact.pop()
    if len(value) >= 9 and text.rstrip().endswith((".", "…")):
        # Keep the separator after a Roman numeral: "Stellar I - ..." is
        # distinct from Stellar II/V. Removing punctuation too early loses it.
        prefix = re.sub(r"\s+", "", text.casefold().rstrip(". …"))
        precise = {target for name, target in names.items()
                   if re.sub(r"\s+", "", name.casefold()).startswith(prefix)}
        if len(precise) == 1:
            return precise.pop()
        matches = {target for name, target in names.items() if clean(name).startswith(value)}
        if len(matches) == 1:
            return matches.pop()
    raise ReadError("Unrecognized or ambiguous VI skill: " + text)


def read_page(frame, reader, slug, position):
    x, y, top, bottom = panel(frame, position)
    names = aliases(slug)
    cells = []
    ended = False
    for row_top in row_tops(frame, x, y):
        for column in COLUMNS:
            reading = cell_reading(frame, x + column, row_top)
            if reading is None:
                ended = True
                continue
            if ended:
                raise ReadError("VI skill list is obscured or has an unexpected gap.")
            cells.append(reading)
    if not cells:
        raise ReadError("No VI skills visible. Open Skills → VI.")
    rows = []
    for (crop, value), (text, confidence) in zip(cells, reader([crop for crop, _ in cells]), strict=True):
        if confidence < .97:
            retry, quality = reader([padded(crop)], use_cache=False)[0]
            if quality < .97 or skill_name(text, names) != skill_name(retry, names):
                raise ReadError("VI skill name is unclear: " + text)
            text, confidence = retry, quality
        name, path = skill_name(text, names)
        # Levels are matched against exact digit glyphs, so only the name carries OCR uncertainty.
        rows.append({"name": name, "path": path, "value": str(value),
                     "confidence": confidence, "text": f"{text} · {value}"})
    if len({r["name"] for r in rows}) != len(rows):
        raise ReadError("Duplicate VI skill rows; wait for scrolling to stop.")
    values = row_values(rows)
    return {"kind": "scouter", "values": values, "shine_page": {
        "class": slug, "position": position, "top": top, "bottom": bottom, "rows": rows,
    }}
