"""Read SHINE's VI skill list, without inferring levels from the Erda Link graph."""

import re
from functools import lru_cache

import cv2
import numpy as np

from flaming.stats import ReadError
from ocr_confidence import padded, verify
from scouter.shine_levels import aliases, row_values
from scouter.vision import anchor
from utils.payload_data import read_payload_bytes


@lru_cache(maxsize=8)
def reference(name):
    return cv2.imdecode(np.frombuffer(read_payload_bytes(f"images/window/scouter/{name}.png"), np.uint8), 1)


def panel(frame, position=None):
    try:
        x, y = anchor(frame, "erda_banner")
    except ReadError as exc:
        raise ReadError("Open Skills → VI (Erda Link) and keep the full skill list visible.") from exc
    if x < 0 or y < 0 or x + 297 > frame.shape[1] or y + 277 > frame.shape[0]:
        raise ReadError("Keep the full Erda Link VI skill list visible.")
    track = frame[y + 52:y + 266, x + 286:x + 294]
    _, quality, _, (_, thumb_y) = cv2.minMaxLoc(cv2.matchTemplate(track, reference("erda_scroll"), cv2.TM_CCOEFF_NORMED))
    if quality >= .95:
        top, bottom = thumb_y <= 1, thumb_y >= 185
    else:
        empty = reference("erda_scroll_empty")
        if cv2.matchTemplate(track, empty, cv2.TM_CCOEFF_NORMED)[0, 0] < .96:
            raise ReadError("Move the cursor and tooltips away from the VI skill list and scrollbar.")
        top = bottom = True
    if position == "top" and not top:
        raise ReadError("Scroll the VI skill list all the way to the top.")
    if position == "bottom" and not bottom:
        raise ReadError("Scroll the VI skill list all the way to the bottom.")
    return x, y, top, bottom


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


def level(text):
    if not re.fullmatch(r"\d{1,2}", text.strip()) or not 0 <= int(text) <= 30:
        raise ReadError("Unrecognized VI skill level: " + text)
    return int(text)


def read_page(frame, reader, slug, position):
    x, y, top, bottom = panel(frame, position)
    names = aliases(slug)
    crops = []
    ended = False
    for row in range(6):
        for col in range(2):
            left, cy = x + 37 + col * 144, y + 43 + row * 40
            icon = frame[cy + 2:cy + 27, left - 32:left - 7]
            empty = icon.min() > 180 and icon.std() < 18
            if empty:
                cell = frame[cy:cy + 32, left - 34:left + 101]
                expected = reference("erda_empty_right" if col else "erda_empty_cell")
                if (cv2.matchTemplate(cell, expected, cv2.TM_CCOEFF_NORMED)[0, 0] < .94
                        or np.abs(cell.astype(float) - expected).mean() > 12):
                    raise ReadError("VI skill list is obscured. Uncover every skill row before scanning.")
                ended = True
                continue
            if ended:
                raise ReadError("VI skill list is obscured or has an unexpected gap.")
            # The list has dark text on a pale background. Inversion preserves
            # antialiasing while giving the shared white-ink reader usable text.
            crops.extend((255 - frame[cy:cy + 16, left:left + 101],
                          255 - frame[cy + 17:cy + 32, left:left + 55]))
    if not crops:
        raise ReadError("No VI skills visible. Open Skills → VI → Erda Link.")
    readings = reader(crops)
    rows = []
    for i in range(0, len(readings), 2):
        text, confidence = readings[i]
        if confidence < .97:
            retry, quality = reader([padded(crops[i])], use_cache=False)[0]
            if quality < .97 or skill_name(text, names) != skill_name(retry, names):
                raise ReadError("VI skill name is unclear: " + text)
            text, confidence = retry, quality
        name, path = skill_name(text, names)
        number, accepted = verify(reader, crops[i + 1], readings[i + 1], level)
        if not accepted:
            raise ReadError("VI skill level is unclear or readings disagree: " + name)
        rows.append({"name": name, "path": path, "value": str(level(number[0])),
                     "confidence": min(confidence, number[1]), "text": text + " · " + number[0]})
    if len({r["name"] for r in rows}) != len(rows):
        raise ReadError("Duplicate VI skill rows; wait for scrolling to stop.")
    values = row_values(rows)
    return {"kind": "scouter", "values": values, "shine_page": {
        "class": slug, "position": position, "top": top, "bottom": bottom, "rows": rows,
    }}
