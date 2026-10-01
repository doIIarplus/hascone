"""Equipment grid and item tooltip readers."""

import hashlib
import re
from dataclasses import asdict
from functools import lru_cache

import cv2
import numpy as np

from flaming.stats import ReadError, parse_stat
from ocr_confidence import verify
from utils.payload_data import read_payload_bytes, read_payload_json


@lru_cache(maxsize=12)
def template(name):
    return cv2.imdecode(
        np.frombuffer(read_payload_bytes("images/window/equipment/" + name + ".png"), np.uint8), cv2.IMREAD_COLOR
    )


def panel_origin(frame):
    ref = template("windows_title")
    scores = cv2.matchTemplate(frame, ref, cv2.TM_CCOEFF_NORMED)
    _, quality, _, (x, y) = cv2.minMaxLoc(scores)
    if quality < 0.97:
        raise ReadError("Open Equipment and leave its title bar visible.")
    return x - 11, y - 7


def grid(frame):
    x, y = panel_origin(frame)
    layout = read_payload_json("src/flaming_data/equipment_layout.json")
    if x < 0 or y < 0 or x + 366 > frame.shape[1] or y + 443 > frame.shape[0]:
        raise ReadError("Move the whole Equipment window on screen.")
    slots = {}
    for slot, box in layout["slots"].items():
        sx, sy = x + 27 + box["x"], y + 99 + box["y"]
        gap = frame[sy + 6 : sy + 36, sx - 3 : sx - 1]
        # Filtering blends the white gap with the adjacent slot outline.
        if np.mean(gap.min(axis=2) > 200) < 0.9:
            raise ReadError("Move the cursor and overlapping windows away from the equipment grid.")
        icon = frame[sy + 4 : sy + 38, sx + 4 : sx + 38]
        center = icon[4:-4, 4:-4]
        if center.std() < 20 and (center.min(axis=2) < 90).sum() < 10:
            continue
        if center.std() <= 35 or (center.min(axis=2) < 90).sum() < 15:
            raise ReadError("Cannot distinguish the item in " + slot + "; uncover the grid.")
        slots[slot] = {"icon_hash": hashlib.sha256(icon.tobytes()).hexdigest(), "icon_box": [sx + 4, sy + 4, 34, 34]}
    if not slots:
        raise ReadError("No equipped items detected. Switch to the Equipment tab.")
    return {"kind": "equipment", "slots": slots, "bounds": [x, y, 366, 443]}


def hovered_slot(frame, point, origin=None):
    x, y = origin or panel_origin(frame)
    if point is None:
        return None
    layout = read_payload_json("src/flaming_data/equipment_layout.json")
    for slot, box in layout["slots"].items():
        sx, sy = x + 27 + box["x"], y + 99 + box["y"]
        if sx <= point[0] < sx + 42 and sy <= point[1] < sy + 42:
            return slot
    raise ReadError("Hover an item in the Equipment grid, not an inventory or comparison item.")


def _glyph_mask(image):
    # Transparent panel backgrounds vary. Match the actual glyphs only.
    return (image.min(axis=2) > 140).astype(np.uint8) * 255


def _verified_bottom_candidates(frame, x, ay, coverage, *, coverage_min=0.8, corner_min=0.9):
    """A bright animated background can hide part of the translucent edge. Require both
    a mostly continuous bottom line and its rounded corner; lowering the line threshold
    alone can accept the game's HUD instead."""
    corner = cv2.cvtColor(template("tooltip_bottom_right"), cv2.COLOR_BGR2GRAY)
    verified = []
    for offset in np.flatnonzero(coverage > coverage_min):
        bottom = ay + 65 + int(offset) + 3
        crop = frame[bottom - 11 : bottom, x + 306 : x + 323]
        if crop.shape[:2] == corner.shape:
            quality = cv2.matchTemplate(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), corner, cv2.TM_CCOEFF_NORMED)[0, 0]
            if quality >= corner_min:
                verified.append(offset)
    return np.array(verified)


def _find_currently_equipped(frame, near=None):
    """Locate the tooltip's "Currently Equipped" label, optionally only near a known spot."""
    ref = _glyph_mask(template("currently_equipped"))
    ox = oy = 0
    area = frame
    if near is not None:
        ox, oy = max(0, near[0] - 40), max(0, near[1] - 40)
        area = frame[oy : near[1] + ref.shape[0] + 40, ox : near[0] + ref.shape[1] + 40]
        if area.shape[0] < ref.shape[0] or area.shape[1] < ref.shape[1]:
            return 0.0, 0, 0
    scores = cv2.matchTemplate(_glyph_mask(area), ref, cv2.TM_CCOEFF_NORMED)
    _, q, _, (ax, ay) = cv2.minMaxLoc(scores)
    return q, ax + ox, ay + oy


def tooltip_bounds(frame, allow_clipped_footer=False, near=None):
    q, ax, ay = _find_currently_equipped(frame, near)
    if q < 0.95:
        raise ReadError("Hover an equipped item until its Currently Equipped tooltip appears.")
    x = ax - 155
    if x < 0 or x + 323 > frame.shape[1] or ay < 105:
        raise ReadError("Keep the item name, stars and full tooltip width on screen.")
    strip = frame[ay + 65 :, x + 20 : x + 300].astype(int)
    if strip.shape[1] != 280:
        raise ReadError("Move the full tooltip on screen.")
    bright = (strip[1:-1] - strip[:-2]).min(axis=2) > 18
    dark = (strip[1:-1] - strip[2:]).min(axis=2) > 25
    coverage = (bright & dark).mean(axis=1)
    candidates = np.flatnonzero(coverage > 0.94)
    if not len(candidates):
        candidates = _verified_bottom_candidates(frame, x, ay, coverage)
    if not len(candidates):
        # The 1440p display filter softens the one-pixel border. Require a
        # nearly continuous line AND its rounded corner for this softer edge;
        # a bright background or the HUD alone must not stand in for a footer.
        soft = ((strip[1:-1] - strip[:-2]).min(axis=2) > 8) & ((strip[1:-1] - strip[2:]).min(axis=2) > 15)
        candidates = _verified_bottom_candidates(frame, x, ay, soft.mean(axis=1), coverage_min=.94, corner_min=.85)
    if not len(candidates):
        if allow_clipped_footer and frame.shape[:2] == (768, 1366):
            return x, ay, frame.shape[0]
        raise ReadError("Show the entire item tooltip, including its bottom edge.")
    return x, ay, ay + 65 + int(candidates[0]) + 3


def hover_target(frame, pointer, slots):
    """The hovered slot among SLOTS, with the tooltip's bounds, from one frame; no OCR."""
    origin = panel_origin(frame)
    slot = hovered_slot(frame, pointer, origin)
    if slot not in slots:
        if len(slots) == 1:
            raise ReadError("Hover your " + slots[0].replace("_", " ") + " in Equipment.")
        raise ReadError("Hover one of the highlighted items that still needs a scan.")
    return slot, origin, tooltip_bounds(frame, allow_clipped_footer=True)


def hover_capture_ready(first, second, slot, origin, bounds, pointer):
    """Cheap pre-OCR check that SECOND holds SLOT's finished tooltip.

    The cursor is still on SLOT, and the tooltip content matches FIRST, so it is
    not mid-draw or left over from another item. The tooltip follows the cursor,
    so each frame is compared at its own position.
    """
    if hovered_slot(second, pointer, origin) != slot:
        raise ReadError("Hold the cursor over the item until it is captured.")
    x1, ay1, bottom1 = bounds
    x2, ay2, bottom2 = tooltip_bounds(second, allow_clipped_footer=True, near=(x1 + 155, ay1))
    if bottom1 - ay1 != bottom2 - ay2:
        raise ReadError("Waiting for the tooltip to finish drawing.")
    top = min(70, ay1, ay2)
    # The tooltip is translucent, so compare its bright text rather than raw
    # colours; star sparkles animate, so allow a small mismatch.
    a = first[ay1 - top : bottom1, x1 : x1 + 323].max(axis=2) > 155
    b = second[ay2 - top : bottom2, x2 : x2 + 323].max(axis=2) > 155
    if a.shape != b.shape or (a ^ b).sum() > 0.1 * max(1, a.sum()):
        raise ReadError("Waiting for the tooltip to finish drawing.")


def mono(image):
    return cv2.cvtColor((image.max(axis=2) > 155).astype(np.uint8) * 255, cv2.COLOR_GRAY2BGR)


def row_regions(frame, x, top, bottom):
    area = frame[top:bottom, x + 15 : x + 310]
    mask = area.max(axis=2) > 155
    ys = np.flatnonzero(mask.sum(axis=1) >= 3)
    groups = [g for g in np.split(ys, np.flatnonzero(np.diff(ys) > 2) + 1) if len(g)]
    return [(top + int(g[0]) - 2, top + int(g[-1]) + 3) for g in groups if 6 <= g[-1] - g[0] + 1 <= 19]


def capabilities(slot, name, potential, stats, text):
    from flaming.item_database import lookup

    data = lookup(name, slot)
    layout = read_payload_json("src/flaming_data/equipment_layout.json")["slots"][slot]
    flame = layout.get("flameable", True)
    if slot == "medal":
        # Ordinary medals are not flameable. New/unlisted medals require
        # positive tooltip evidence, never a guess.
        flame = bool(stats) or name.casefold() == "immortal legacy" or bool(data and data.get("flameable"))
    elif data:
        flame = data["flameable"]
    if "bonusstatscantenhance" in re.sub(r"[^a-z]", "", text.lower()):
        flame = False
    plain = re.sub(r"[^a-z]", "", text.lower())
    cube = True if potential else (False if "potentialcantenhance" in plain or not layout.get("cubeable") else None)
    if slot == "badge":
        cube = name.casefold() in ("ghost ship exorcist", "sengoku hakase badge", "sengoku badge")
    return {"flameable": flame, "cubeable": cube}


def parse_bonus_detail(text):
    text = re.sub(r"^Required\s+Level", "Reduced level requirement", text.strip(), flags=re.I)
    dual = re.fullmatch(r"(STR|DEX|INT|LUK)\s*,\s*(STR|DEX|INT|LUK)\s*\+\s*(\d+)", text, re.I)
    if dual:
        return [parse_stat(name + "+" + dual[3]) for name in (dual[1], dual[2])]
    return [parse_stat(text)]


def _resolve_item_name(reader, frame, x, ay, name_row, name, confidence):
    if confidence < 0.94 or not name.strip():
        # Read a difficult title alone, without the batch's narrower stat rows.
        # Preserve antialiasing in one pass; do not relax identity confidence.
        native = frame[ay - 70 : ay - 48, x + 15 : x + 310]
        for candidate in (name_row, native):
            retry_name, retry_confidence = reader([candidate], use_cache=False)[0]
            if retry_confidence >= 0.94 and retry_name.strip():
                name, confidence = retry_name, retry_confidence
                break
    if confidence < 0.94 or not name.strip():
        raise ReadError("Item name is not clear. Keep the tooltip unobstructed.")
    return name, confidence


def _scan_stat_rows(frame, x, reader, rows, readings, result):
    stats, attack_totals, stat_rows, in_stats = [], {}, 0, True
    for (a, b), (text, confidence) in zip(rows, readings[1:], strict=True):
        level = re.search(r"Required\s*Level\s*(Lv\.?\s*.*)", text, re.I)
        if level:
            from flaming.item_tooltip import parse_level

            def level_values(value):
                found = re.search(r"Required\s*Level\s*(Lv\.?\s*.*)", value, re.I)
                if not found:
                    raise ReadError("Missing Required Level label")
                parse_level(found[1])
                # Optional punctuation in Lv. can differ between reads, but
                # the effective level, base level and reduction must all agree.
                return tuple(map(int, re.findall(r"\d+", found[1])))

            (text, confidence), accepted = verify(
                reader, mono(frame[a:b, x + 15:x + 310]), (text, confidence), level_values,
            )
            if not accepted:
                raise ReadError("Required level is unclear; scan again")
            level = re.search(r"Required\s*Level\s*(Lv\.?\s*.*)", text, re.I)
            result["required_level"] = parse_level(level[1])
        if re.search(r"Bonus Stats|Potential|Check the enhancement|Interact/Harvest|Soul\s*:", text, re.I):
            in_stats = False
        region = frame[a:b, x + 15 : x + 310]
        blue, green, red = [v.astype(int) for v in cv2.split(region)]
        cyan = (blue > 115) & (green > 130) & (red < 135) & (green > red + 40) & (blue > red + 35)
        if in_stats and re.match(
            r"(STR|DEX|INT|LUK|All Stats|Max HP|Max MP|Attack Power|Magic ATT|Defense|Speed|Jump|Damage|Boss Damage)\s*[+:]",
            text,
            re.I,
        ):
            (text, confidence), accepted = verify(reader, mono(region), (text, confidence))
            if not accepted:
                raise ReadError("Stat row is unclear or readings disagree: " + text)
            stat_rows += 1
            match = re.match(r"(Attack Power|Magic ATT)\s*\+\s*(\d+)", text, re.I)
            if match and confidence >= 0.90:
                attack_totals["MATT" if match[1].lower().startswith("magic") else "ATT"] = int(match[2])
            if cyan.sum() >= 4:
                crop = cv2.cvtColor(cyan.astype(np.uint8) * 255, cv2.COLOR_GRAY2BGR)
                value, quality = reader([crop])[0]
                label = re.split(r"\s*[+:]", text, maxsplit=1)[0]
                (value, quality), accepted = verify(reader, crop, (value, quality), lambda value: parse_stat(label + value))
                if not accepted:
                    raise ReadError("Flame bonus not clear: " + text)
                stats.append(asdict(parse_stat(label + value)))
    return stats, attack_totals, stat_rows


def _bonus_detail_crops(frame, x, texts, rows, start):
    crops = []
    for j in range(start, len(rows)):
        if re.search(r"Potential|Exceptional|Star Force|Soul", texts[j], re.I):
            break
        a, b = rows[j]
        for left, right in ((26, 164), (181, 312)):
            crop = mono(frame[a:b, x + left : x + right])
            if np.count_nonzero(crop[:, :, 0]) >= 4:
                crops.append(crop)
    return crops


def _bonus_stats_detail(frame, x, reader, texts, rows):
    """Expanded tooltips list flame lines separately. Read each column, avoiding
    the cursor over total-stat labels and summing dual-stat and single lines."""
    for i, text in enumerate(texts):
        if not re.fullmatch(r"Bonus\s+Stats", text.strip(), re.I):
            continue
        detail_crops = _bonus_detail_crops(frame, x, texts, rows, i + 1)
        if not detail_crops or len(detail_crops) > 4:
            raise ReadError("Bonus Stats details are incomplete. Move the cursor away from the tooltip.")
        totals = {}
        for crop, reading in zip(detail_crops, reader(detail_crops), strict=True):
            (text, quality), accepted = verify(reader, crop, reading, parse_bonus_detail)
            if not accepted:
                raise ReadError("Bonus Stats detail is unclear. Move the cursor away from the tooltip.")
            for stat in parse_bonus_detail(text):
                key = (stat.name, stat.percent)
                totals[key] = totals.get(key, 0) + stat.value
        return [{"name": name, "value": value, "percent": percent} for (name, percent), value in totals.items()]
    return None


def _potential_tier(frame, x, a, b):
    bullet = frame[a:b, x + 15 : x + 23]
    pixels = bullet.reshape(-1, 3).astype(int)
    colored = pixels[(pixels.max(axis=1) > 180) & (np.ptp(pixels, axis=1) > 65)]
    if not len(colored):
        return None
    blue, green, red = np.median(colored, axis=0)
    if green > red + 10 and green > blue + 50:
        return "Legendary"
    if red > 180 and green > 150 and blue < 130:
        return "Unique"
    if red > 140 and blue > 140:
        return "Epic"
    return "Rare"


def _read_potential(frame, x, reader, readings, rows, name):
    """The potential header and lines use a colored bullet, not a letter here."""
    for i, (text, confidence) in enumerate(readings[1:]):
        found = re.search(r"Potential\s*:\s*(Rare|Epic|Unique|Legendary)", text, re.I)
        if not found:
            continue
        if confidence < 0.90:
            raise ReadError("Potential tier is unclear. Hold the tooltip still.")
        rank = found[1].title()
        lines, tiers = [], []
        for j in range(i + 1, min(i + 4, len(rows))):
            a, b = rows[j]
            text, confidence = readings[j + 1]
            tier = _potential_tier(frame, x, a, b)
            if tier is None:
                break
            def potential_text(value):
                return re.sub(r"\s+", "", re.sub(r"^[\s\u25a0\u2022\-]+", "", value)).casefold()
            if re.search(r"\d", text):
                (text, confidence), accepted = verify(
                    reader, mono(frame[a:b, x + 26:x + 310]), (text, confidence), potential_text,
                )
            else:
                # Text-only skill-granting potentials retain their existing gate.
                if confidence < 0.90:
                    text, confidence = reader([mono(frame[a:b, x + 26:x + 310])], use_cache=False)[0]
                accepted = confidence >= 0.90
            if not accepted or "..." in text or "\u2026" in text:
                raise ReadError("A potential line is unclear or truncated. Expand the tooltip and scan again.")
            lines.append(re.sub(r"^[\s\u25a0\u2022\-]+", "", text))
            tiers.append(tier)
        if len(lines) not in (2, 3):
            raise ReadError("Potential lines are incomplete. Keep the entire tooltip visible.")
        return {
            "kind": "potential",
            "item": name,
            "rank": rank,
            "lines": lines,
            "line_tiers": tiers,
            "source": "equipped_tooltip",
            "status": "scanned",
        }
    return None


def _read_starforce(frame, slot, full):
    from starforce.vision import read

    try:
        return read(frame)
    except ReadError as exc:
        # Missing stars must not turn into zero stars.
        if (
            "starforce" in re.sub(r"[^a-z]", "", full.lower())
            and "enhance" in full.lower()
            or slot in ("medal", "badge", "pocket", "android", "secondary", "emblem")
        ):
            return {"status": "not_applicable"}
        return {"status": "unavailable", "error": str(exc)}


def _apply_slot_capabilities(result, slot, name, stats, full):
    if not slot:
        return
    result.update(slot=slot, **capabilities(slot, name, result.get("potential"), stats, full))
    if result["flameable"] is False:
        result.pop("stats", None)


def _ring_level(readings, name, reader=None, crops=None):
    if name.strip() not in ("Continuous Ring", "Ring of Restraint", "Weapon Jump Ring"):
        return None
    for index, (text, quality) in enumerate(readings[1:], 1):
        match = re.fullmatch(r"Lv\.?\s*(\d)", text.strip())
        if match and 1 <= int(match[1]) <= 6:
            accepted = quality >= 0.97
            if reader is not None and not accepted:
                (text, quality), accepted = verify(reader, crops[index], (text, quality))
            if accepted:
                return int(match[1])
    return None


def hover(frame, reader, slot=None):
    x, ay, bottom = tooltip_bounds(frame, allow_clipped_footer=True)
    clipped_footer = bottom == frame.shape[0]
    name_row = mono(frame[ay - 70 : ay - 48, x + 15 : x + 310])
    rows = row_regions(frame, x, ay + 53, bottom - (4 if clipped_footer else 12))
    crops = [name_row] + [mono(frame[a:b, x + 15 : x + 310]) for a, b in rows]
    readings = reader(crops)
    name, confidence = _resolve_item_name(reader, frame, x, ay, name_row, *readings[0])
    result = {"kind": "hover", "item": name.strip(), "source": "equipped_tooltip", "errors": []}
    texts = [text for text, _ in readings[1:]]
    full = "\n".join(texts)
    stats, attack_totals, stat_rows = _scan_stat_rows(frame, x, reader, rows, readings, result)
    detail_stats = _bonus_stats_detail(frame, x, reader, texts, rows)
    if detail_stats is not None:
        stats = detail_stats
        stat_rows = max(stat_rows, 1)
    potential = _read_potential(frame, x, reader, readings, rows, name)
    if potential:
        result["potential"] = potential
    if clipped_footer:
        potential = result.get("potential") or {}
        if len(potential.get("lines", [])) != 3 or not stat_rows or not result.get("required_level"):
            raise ReadError("Tooltip is clipped. Show all stats and three complete potential lines.")
    if slot == "weapon" and attack_totals:
        result["weapon_attack"] = attack_totals
    if stat_rows:
        result["stats"] = stats
    result["starforce"] = _read_starforce(frame, slot, full)
    _apply_slot_capabilities(result, slot, name, stats, full)
    ring_level = _ring_level(readings, name, reader, crops)
    if ring_level:
        result["ring_level"] = ring_level
    result["readings"] = texts
    return result


def hover_icon(frame):
    """The hovered item's 34 x 34 icon from its tooltip, as PNG bytes."""
    from utils.image_files import encode_png

    x, ay, _ = tooltip_bounds(frame, allow_clipped_footer=True)
    icon = frame[ay - 27 : ay + 49, x + 19 : x + 95]
    return encode_png(cv2.resize(icon, (34, 34), interpolation=cv2.INTER_AREA))


def icons(frame, result):
    """PNG icons that equipment_save.save stores for RESULT, cut from its frame."""
    from utils.image_files import encode_png

    if result["kind"] == "equipment":
        return {
            slot: encode_png(frame[y : y + h, x : x + w])
            for slot, reading in result["slots"].items()
            for x, y, w, h in [reading["icon_box"]]
        }
    return {result["slot"]: hover_icon(frame)}
