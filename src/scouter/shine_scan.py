"""Read SHINE's VI skill list, without inferring levels from the Erda Link graph."""

import re
from functools import lru_cache

import cv2
import numpy as np

from flaming.vision import ReadError
from ocr_confidence import padded, verify
from scouter.vision import anchor
from utils.payload_data import read_payload_bytes

CLASSES = {"sia_astelle", "erel_light"}


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


def aliases(slug):
    from scouter.profiles import class_info

    if slug not in CLASSES:
        raise ReadError("This VI scanner is for Sia Astelle and Erel Light.")
    info = class_info(slug)
    result = {}
    for key, core in info["cores"].items():
        if not core.get("url") or key in ("masteryCore3", "masteryCore4", "generalCore3"):
            continue
        for name in core["english_title"].split("/"):
            result[name] = (name, "hexa." + key)
            if key.startswith("rein"):
                result[name + " Boost"] = (name, "hexa." + key)
    result["SHINE Tree of Stars"] = ("SHINE Tree of Stars", "hexa.generalCore3")
    result["Sol Janus"] = ("Sol Janus", "huntSkill.solJanus")
    for name in ("Sol Janus: Dawn", "Sol Janus: Dusk", "Sol Hecate: Styx", "Sol Hecate: Charon",
                 "Sol Hecate: Phlegethon", "Sol Hecate: Pactum", "Erda Link Stats"):
        result[name] = (name, None)
    return result


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


def row_values(rows):
    values = {}
    for row in rows:
        path = row["path"]
        if path is None:
            continue
        value = {key: row[key] for key in ("value", "confidence", "text")}
        if path in values and values[path]["value"] != value["value"]:
            raise ReadError("Shared mastery skill levels disagree. Rescan the VI list.")
        if path not in values or value["confidence"] < values[path]["confidence"]:
            values[path] = value
    return values


def merge_pages(top, bottom):
    if top["class"] != bottom["class"] or not top["top"] or not bottom["bottom"]:
        raise ReadError("Capture the top and bottom of the same character's VI list.")
    a, b = top["rows"], bottom["rows"]
    names_a, names_b = [r["name"] for r in a], [r["name"] for r in b]
    if top["bottom"]:
        if names_a != names_b:
            raise ReadError("VI skill list changed between captures; rescan both pages.")
        overlap = len(a)
    else:
        overlaps = [n for n in range(2, min(len(a), len(b)) + 1, 2) if names_a[-n:] == names_b[:n]]
        if not overlaps:
            raise ReadError("VI pages do not overlap. Rescan both ends of the list; do not hide or rearrange skills.")
        overlap = max(overlaps)
    for first, second in zip(a[-overlap:], b[:overlap], strict=True):
        if first["value"] != second["value"]:
            raise ReadError("VI levels changed between captures; rescan both pages.")
    combined = a + b[overlap:]
    values = row_values(combined)
    # Absence only means inactive after proving that the whole list was read.
    for _, path in aliases(top["class"]).values():
        if path and path not in values:
            values[path] = {"value": "0", "confidence": 1, "text": "Inactive in the complete Erda Link VI list"}
    return values


def prepare_save(data, page, session, baseline):
    """Reconcile only pages from one guided scan, preserving intervening edits."""
    if not isinstance(session, str) or not session or len(session) > 128:
        raise ReadError("Start a guided SHINE scan to capture the top and bottom together.")
    if page["class"] != data["class_info"]["slug"]:
        raise ReadError("VI skill list does not match the selected character class.")
    if page["position"] == "top":
        state = {"session": session, "top": page, "baseline": baseline, "complete": page["bottom"]}
        values = merge_pages(page, page) if page["bottom"] else row_values(page["rows"])
    else:
        state = data.get("shine_levels", {})
        if state.get("session") != session or not state.get("top"):
            raise ReadError("The top of this VI list was not verified. Rescan both SHINE steps.")
        values = merge_pages(state["top"], page)
        state = {**state, "bottom": page, "complete": True}
        baseline = state["baseline"]
    if any(data.get("manual_versions", {}).get(key) != baseline.get(key) for key in values):
        raise ReadError("HEXA inputs changed during the VI scan. Rescan both SHINE steps.")
    return values, state
