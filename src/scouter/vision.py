"""Read anchored, individual stat rows with the shared PP-OCRv6 worker."""

import re
from typing import Any

import cv2
import numpy as np

from flaming.vision import ReadError
from utils.payload_data import read_payload_bytes


def anchor(frame, name, threshold=0.96, masked=False):
    source = cv2.imdecode(
        np.frombuffer(read_payload_bytes(f"images/window/scouter/{name}.png"), np.uint8), cv2.IMREAD_COLOR
    )
    if source is None:
        raise ReadError(f"Missing Scouter anchor: {name}")
    if masked:
        source = (source.min(axis=2) > 105).astype(np.uint8) * 255
        frame = (frame.min(axis=2) > 105).astype(np.uint8) * 255
    scores = cv2.matchTemplate(frame, source, cv2.TM_CCOEFF_NORMED)
    _, quality, _, point = cv2.minMaxLoc(scores)
    if quality < threshold:
        raise ReadError(f"Could not locate the {name} panel. Leave the full window visible.")
    x, y = point
    scores[max(0, y - 3) : y + 4, max(0, x - 3) : x + 4] = 0
    if scores.max() >= threshold:
        raise ReadError(f"Multiple {name} panels are visible")
    return point


def origin(frame):
    x, y = anchor(frame, "character")
    return x - 12, y - 9


def foreground(crop):
    # Character Info uses a light gray background and yellow buffed numbers.
    white = (crop[:, :, 2] > 180) & (crop[:, :, 1] > 170)
    yellow = (crop[:, :, 2] > 210) & (crop[:, :, 1] > 170) & (crop[:, :, 0] < 160)
    return cv2.cvtColor((white | yellow).astype(np.uint8) * 255, cv2.COLOR_GRAY2BGR)


def numeric(text):
    text = text.strip().replace(" ", "")
    # Deliberately do not silently turn uncertain letters into digits.
    if not re.fullmatch(r"\d+(?:,\d{3})*(?:\.\d+)?%?", text):
        raise ReadError(f"Unrecognized stat number: {text}")
    return text.replace(",", "").removesuffix("%")


# Coordinates below are relative to the detected title, at native UI scale in both supported resolutions.
OVERVIEW_FIELDS = {
    "entireStat.str": (875, 416, 920),
    "entireStat.dex": (1075, 416, 1130),
    "entireStat.int": (875, 438, 920),
    "entireStat.luk": (1075, 438, 1130),
    "stat.maple_combatPower": (868, 354, 981),
    "stat.dmg": (1083, 477, 1138),
    "stat.bossDmg": (1083, 499, 1138),
    "stat.normalDmg": (1083, 521, 1138),
    "stat.ignoreDef": (867, 521, 919),
    "stat.critical": (1085, 543, 1138),
    "stat.criticalDmg": (1083, 565, 1138),
    "stat.buffDuration": (1095, 587, 1138),
    "stat.resetCoolDown": (867, 609, 919),
    "stat.ignoreElementalResist": (1095, 609, 1138),
    "stat.statusAdditionalDmg": (866, 631, 919),
    "stat.summonPersistTime": (1095, 631, 1138),
    "stat.arcaneForce": (1100, 693, 1138),
    "stat.authenticForce": (1095, 715, 1138),
    "cooldown": (843, 587, 920),
    "stat.level": (899, 109, 950),
    "character_name": (867, 248, 979),
    "character_class": (710, 118, 817),
}


def _overview_crops(frame, ox, oy):
    crops, originals = [], []
    for left, cy, right in OVERVIEW_FIELDS.values():
        left, right, cy = left + ox - 688, right + ox - 688, cy + oy - 70
        if left < 0 or right > frame.shape[1] or cy < 9 or cy + 9 > frame.shape[0]:
            raise ReadError("Character Info is clipped; move it fully inside the game")
        crop = frame[cy - 10 : cy + 11, left:right]
        originals.append(crop)
        prepared = foreground(crop)
        # Short mixed number/unit labels need vertical whitespace for PP-OCR.
        if len(crops) == list(OVERVIEW_FIELDS).index("cooldown"):
            prepared = cv2.copyMakeBorder(prepared, 8, 8, 8, 8, cv2.BORDER_CONSTANT)
        crops.append(prepared)
    return crops, originals


def _retry_uncertain_overview(reader, results, originals):
    # Buff arrows can become OCR characters after thresholding (e.g. 100%
    # reads at 93%). Retry only uncertain numbers using the original colors.
    retry = [
        i
        for i, (path, (_, confidence)) in enumerate(zip(OVERVIEW_FIELDS, results, strict=True))
        if path not in ("character_name", "character_class", "cooldown") and confidence < 0.97
    ]
    if not retry:
        return
    for i, alternate in zip(retry, reader([originals[i] for i in retry]), strict=True):
        if alternate[1] < 0.97:
            continue
        try:
            original = numeric(results[i][0])
        except ReadError:
            original = None
        try:
            recovered = numeric(alternate[0])
        except ReadError:
            continue
        if original is None or original == recovered:
            results[i] = alternate


def _retry_uncertain_identity(reader, results, originals):
    # Tight name/class crops can turn the first letter into a different glyph.
    # Require agreement between two padded renderings at the usual threshold.
    for path in ("character_name", "character_class"):
        index = list(OVERVIEW_FIELDS).index(path)
        if results[index][1] >= 0.97:
            continue
        original = originals[index]
        variants = [
            cv2.copyMakeBorder(original, 8, 8, 8, 8, cv2.BORDER_REPLICATE),
            cv2.copyMakeBorder(foreground(original), 8, 8, 8, 8, cv2.BORDER_CONSTANT),
        ]
        readings = [list(reader([crop], use_cache=False))[0] for crop in variants]
        if all(confidence >= 0.97 for _, confidence in readings) and len({text.strip().casefold() for text, _ in readings}) == 1:
            results[index] = min(readings, key=lambda result: result[1])


def _parse_cooldown(text, confidence, values):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*sec\s*/\s*(\d+(?:\.\d+)?)\s*%", text, re.I)
    if not match:
        raise ReadError("Could not read both cooldown values")
    for k, v in zip(("coolTimeReduce", "coolTimeReducePercent"), match.groups(), strict=True):
        values["stat." + k] = {"value": v, "confidence": confidence, "text": text}


def _parse_overview_field(path, text, confidence, values, identity):
    if confidence < (0.95 if path == "cooldown" else 0.97):
        raise ReadError(f"Low confidence ({confidence:.0%})")
    if path in ("character_name", "character_class"):
        identity[path] = text
        return
    if path == "cooldown":
        _parse_cooldown(text, confidence, values)
        return
    if path == "stat.level":
        text = re.sub(r"^Lv\.?\s*", "", text, flags=re.I)
    value = numeric(text)
    values[path] = {"value": value, "confidence": confidence, "text": text}


def overview(frame, reader):
    ox, oy = origin(frame)
    try:
        sx, sy = anchor(frame, "stats_panel")
    except ReadError as exc:
        raise ReadError("Expand Details in Character Info and keep the stats visible.") from exc
    if not (ox < sx < ox + 460 and oy + 230 < sy < oy + 260):
        raise ReadError("Keep the expanded stats panel fully visible.")
    crops, originals = _overview_crops(frame, ox, oy)
    results = list(reader(crops))
    _retry_uncertain_identity(reader, results, originals)
    _retry_uncertain_overview(reader, results, originals)
    values, errors, identity = {}, [], {}
    for path, (text, confidence) in zip(OVERVIEW_FIELDS, results, strict=True):
        try:
            _parse_overview_field(path, text, confidence, values, identity)
        except ReadError as exc:
            errors.append(f"{path}: {exc}")
    return {"kind": "scouter", "values": values, "errors": errors, **identity}


def tooltip(frame, reader):
    x, y = anchor(frame, "applied", masked=True, threshold=0.95)
    crops = [frame[y + 14 + i * 16 : y + 29 + i * 16, x - 2 : x + 252] for i in range(3)]
    values = {}
    for index, (key, (text, confidence)) in enumerate(
        zip(("base", "percent", "unaffected"), reader(crops), strict=True)
    ):
        pattern = {
            "base": r"Base\s*Value\s*:\s*(\d+)",
            "percent": r"%\s*Value\s*:\s*(\d+(?:\.\d+)?)\s*%",
            "unaffected": r"%\s*Value\s*Not\s*Applied\s*:\s*(\d+)",
        }[key]
        match = re.fullmatch(pattern, text.strip(), re.I)
        if confidence < 0.95 and text.strip():
            # Batch padding can hurt short tooltip rows. Reread that row alone,
            # bypassing the glyph cache which otherwise returns the same failure.
            retry_text, retry_confidence = list(reader([crops[index]], use_cache=False))[0]
            retry_match = re.fullmatch(pattern, retry_text.strip(), re.I)
            if retry_match and retry_confidence >= 0.95:
                if match and match[1] != retry_match[1]:
                    raise ReadError(f"Conflicting tooltip {key} readings")
                text, confidence, match = retry_text, retry_confidence, retry_match
        if not match or confidence < 0.95:
            if key == "unaffected":
                # Only clear an absent row when the next section is visible.
                heading = frame[y + 58:y + 80, x - 2:x + 252]
                heading_text, heading_confidence = list(reader([heading]))[0]
                if heading_confidence >= 0.95 and re.fullmatch(r"\[?\s*Base\s*Value\s*\]?", heading_text.strip(), re.I):
                    values[key] = {"value": "0", "confidence": heading_confidence,
                                   "text": "No unaffected value before Base Value section"}
                continue
            raise ReadError(f"Could not confidently read tooltip {key}: {text}")
        values[key] = {"value": match[1], "confidence": confidence, "text": text}
    return {"kind": "scouter", "values": values}


def weapon(frame, reader):
    # Restrict OCR to the stat section below Required Level, excluding potentials.
    try:
        x, y = anchor(frame, "required", masked=True, threshold=0.95)
    except ReadError:
        from flaming.item_tooltip import level_anchor

        x, y, _, _ = level_anchor(frame)
    region = frame[y + 14 : min(frame.shape[0], y + 285), x : x + 294]
    bright = region.min(axis=2) > 180
    occupied = np.flatnonzero(bright.sum(axis=1) >= 4)
    groups = [g for g in np.split(occupied, np.flatnonzero(np.diff(occupied) > 3) + 1) if len(g)]
    crops = [region[max(0, int(g[0]) - 2) : int(g[-1]) + 3] for g in groups if 7 <= len(g) <= 14]
    matches = {}
    for text, confidence in reader(crops):
        match = re.fullmatch(r"(Attack Power|Magic ATT)\s*\+\s*(\d+)(?:\s*\([^%]*\))?", text.strip(), re.I)
        if match and confidence >= 0.97:
            matches["MATT" if match[1].lower().startswith("magic") else "ATT"] = {
                "value": match[2],
                "confidence": confidence,
                "text": text,
            }
    if not matches:
        raise ReadError("Could not read total weapon attack; enter it manually")
    return {"kind": "scouter", "values": matches}


def scene(frame, reader, mode) -> dict[str, Any]:
    from scouter.hexa_scan import read_hover, read_matrix
    from scouter.link_scan import read_links

    if mode == "hexa":
        return read_matrix(frame)
    if mode.startswith("hexa_hover:"):
        return read_hover(frame, reader, mode.split(":", 1)[1])

    return {"overview": overview, "tooltip": tooltip, "weapon": weapon, "links": read_links}[mode](
        frame, reader
    )


def verify_hover(frame, point, stat):
    """Identify a breakdown anywhere on its row, including label and blank space."""
    ox,oy=origin(frame)
    # Left and right stat rows share a Y position; keep their bounds separate.
    cells={'STR':(12,346,239),'DEX':(240,346,449),'INT':(12,368,239),'LUK':(240,368,449),
           'HP':(12,324,239),'ATT':(12,473,239),'MATT':(12,495,239)}
    if stat not in cells:
        raise ReadError('This stat breakdown needs manual confirmation.')
    left,cy,right=cells[stat]
    if point is None or not (ox+left<=point[0]<=ox+right and oy+cy-10<=point[1]<=oy+cy+11):
        raise ReadError('Hover the '+stat+' row in Character Info and keep its tooltip visible.')
