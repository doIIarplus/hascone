"""Read an event piece's slot, class and skill lines from any item tooltip.

Works for an inventory hover (where the game always also shows the equipped
item's comparison tooltip) and for an Equipment-window hover. The tooltip is
anchored on its Required Level label; the comparison tooltip is the one that
shows "Currently Equipped", so the hovered item is the other one.

Skill lines follow the base stats, whose last row is "Enemy DEF Ignored", and
end at "Scroll Enhancement". A long line wraps onto a second row, e.g.
"[Hologram] Attack Power & Magic ATT Enhancement" / "Skill Lv. +1"; rows are
joined until the line ends in "Lv. +N" or a stat value.
"""

import re

import numpy as np

from equipment_scan import (
    TEXT_LEFT,
    TEXT_RIGHT,
    _find_currently_equipped,
    row_crop,
    row_regions,
    tooltip_bottom,
)
from flaming.item_tooltip import level_anchors
from flaming.stats import ReadError
from ocr_confidence import AGREEMENT_CONFIDENCE, AUTO_CONFIDENCE, verify
from quanah import solver
from quanah.lines import SKILL_END, SKIPPED, match_line

# Offsets from the Required Level label, measured on GMS hover fixtures and
# event-item screenshots: the tooltip's left edge is 14 px left of it, and a
# "Currently Equipped" label (when shown) sits 72 px above it, 141 px right.
LEFT = 14
EQUIPPED_DY, EQUIPPED_DX = 72, 141
WIDTH = 323
# Event tooltips stack Untradable/Duration rows above the icon, so the name is
# searched for in this many pixels above Required Level rather than at a fixed row.
NAME_SEARCH = 300
MAX_WRAP = 3
END_MARKERS = re.compile(r"^(Scroll\s*Enhancement|Jewel\s*Stats|Potential|Bonus\s*Potential|Check\s*the)", re.I)
BASE_END = re.compile(r"^Enemy\s*DEF\s*Ignored", re.I)
STAT_END = re.compile(r"\+\s*\d+(?:\.\d+)?\s*%?\s*(?:\([^)]*\))?\s*$")
SKILL_START = re.compile(r"^\[?\s*Hologram|Lv\.?\s*\+\s*\d", re.I)


def _is_equipped(frame, x, y):
    quality, _, _ = _find_currently_equipped(frame, near=(x + EQUIPPED_DX, y - EQUIPPED_DY))
    return quality >= 0.95


def locate(frame, pointer=None, anchor=None):
    """The hovered piece's tooltip as (x, name search top, Required Level y, bottom), from one frame; no OCR.

    ANCHOR, the Required Level position chosen when the frame was captured (see
    anchor_of), reads that same tooltip later, when the cursor is no longer known.

    The bottom edge is used when found. A tooltip pushed against the bottom of
    the screen may not show it; the skill lines end well above it, so the
    frame's bottom stands in and read_piece requires the Scroll Enhancement row.
    """
    anchors = level_anchors(frame)
    if not anchors:
        raise ReadError("Hover an event item.")
    hovered = [a for a in anchors if not _is_equipped(frame, *a)]
    if anchor is not None:
        if tuple(anchor) not in anchors:
            raise ReadError("Hover one item at a time.")
        lx, ly = anchor
    elif len(hovered) == 1:
        lx, ly = hovered[0]
    elif not hovered and len(anchors) == 1:
        lx, ly = anchors[0]  # An Equipment-window hover shows only the equipped item.
    elif pointer is not None:
        lx, ly = min(hovered or anchors, key=lambda a: (a[0] - pointer[0]) ** 2 + (a[1] - pointer[1]) ** 2)
    else:
        raise ReadError("Hover one item at a time.")
    x = lx - LEFT
    # Rows are read up to TEXT_RIGHT; the last few pixels are only the border.
    if x < 0 or x + TEXT_RIGHT > frame.shape[1]:
        raise ReadError("Move the tooltip fully on screen.")
    try:
        bottom = tooltip_bottom(frame, x, ly - EQUIPPED_DY)
    except ReadError:
        bottom = frame.shape[0]
    return x, max(0, ly - NAME_SEARCH), ly, bottom


def anchor_of(box):
    """The Required Level position of a box from locate, to pass to read_piece."""
    x, _, level_y, _ = box
    return x + LEFT, level_y


def signature(frame, box):
    """Bright text below Required Level: equal for the same piece wherever its tooltip is drawn."""
    x, _, level_y, bottom = box
    return frame[level_y:bottom, x : x + WIDTH].max(axis=2) > 155


def same_tooltip(a, b, tolerance=0.1):
    """Whether two signatures show the same tooltip, allowing for animated sparkles."""
    if a is None or b is None or a.shape != b.shape:
        return False
    return int((a ^ b).sum()) <= tolerance * max(1, int(a.sum()))


def _word(word, text):
    return re.search(rf"\b{re.escape(word)}\b", text, re.I)


def parse_name(text):
    """(slot, class) from an item name like "Libae's Supercharged Hat (Warrior)"."""
    catalog = solver.catalog()
    if _word("Required", text) or _word("Set", text):
        return None
    slot = next((s["key"] for s in catalog["slots"] if any(_word(k, text) for k in s["keywords"])), None)
    item_class = next((c["key"] for c in catalog["classes"] if _word(c["name"], text)), None)
    return (slot, item_class) if slot and item_class else None


def _accept(reader, crop, reading, parse):
    """A reading's text, retried when uncertain; None if it can't be trusted."""
    if reading[1] >= AUTO_CONFIDENCE:
        return reading[0]
    (text, confidence), accepted = verify(reader, crop, reading, parse)
    return text if accepted and confidence >= AGREEMENT_CONFIDENCE else None


def _text(text):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ReadError("Empty row")
    return text.casefold()


def _complete(text):
    return bool(SKILL_END.search(text) or STAT_END.search(text))


def section(texts):
    """Indexes of the rows holding skill lines, grouped by line: [[row, ...], ...]. Also whether it ended."""
    start = next((i + 1 for i, t in enumerate(texts) if BASE_END.match(t.strip())), None)
    if start is None:
        start = next((i for i, t in enumerate(texts) if SKILL_START.search(t)), len(texts))
    lines, current = [], []
    for i in range(start, len(texts)):
        text = texts[i].strip()
        if END_MARKERS.match(text):
            if current:
                lines.append(current)
            return lines, True
        if not text:
            continue
        current.append(i)
        if _complete(" ".join(texts[j] for j in current)) or len(current) >= MAX_WRAP:
            lines.append(current)
            current = []
    if current:
        lines.append(current)
    return lines, False


NAME_WHITE, NAME_PIXELS = 0.8, 120
BATCH = 6


def tooltip_top(frame, x, search_top, level_y):
    """The tooltip's top border: the one 1 px line above its header, or SEARCH_TOP if none is found.

    Rows above it belong to other windows, so the name is looked for only below it.
    """
    strip = frame[search_top:level_y, x + 20 : x + 300].astype(int)
    if len(strip) < 3:
        return search_top
    line = ((strip[1:-1] - strip[:-2]).min(axis=2) > 8) & ((strip[1:-1] - strip[2:]).min(axis=2) > 8)
    # Even a short tooltip (a medal) has 160 px of header above Required Level; separators sit closer.
    found = [search_top + 1 + int(i) for i in np.flatnonzero(line.mean(axis=1) > 0.9)]
    found = [y for y in found if y < level_y - 100]
    return max(found) if found else search_top


def name_rows(frame, x, rows):
    """Indexes of the name's row(s): the first white text below the border (stars are yellow,
    Untradable and Duration orange). A long name wraps onto a second white row."""
    white = []
    for i, (a, b) in enumerate(rows):
        area = frame[a:b, x + TEXT_LEFT : x + TEXT_RIGHT]
        bright = int((area.max(axis=2) > 155).sum())
        if bright >= NAME_PIXELS and (area.min(axis=2) > 150).sum() >= NAME_WHITE * bright:
            white.append(i)
    if not white:
        return list(range(min(4, len(rows))))
    first = white[0]
    wrap = first + 1 in white and rows[first + 1][0] - rows[first][1] < 8
    return [first, first + 1] if wrap else [first]


class _Rows:
    """Rows of one tooltip, read only when asked; each model call costs about 0.6 s per row."""

    def __init__(self, frame, x, rows, reader):
        self.rows, self.reader, self.readings = rows, reader, {}
        self.crops = [row_crop(frame, x, row) for row in rows]

    def read(self, indexes):
        todo = [i for i in indexes if i not in self.readings]
        if todo:
            for i, reading in zip(todo, self.reader([self.crops[i] for i in todo]), strict=True):
                self.readings[i] = reading
        return [self.readings[i] for i in indexes]

    def accept(self, i, parse):
        return _accept(self.reader, self.crops[i], self.readings[i], parse)


def clean_name(text):
    """The name without stray marks in front, e.g. the cursor over its first letter read as "_"."""
    return re.sub(r"^[^A-Za-z0-9\[(]+", "", text.strip())


def _identify(rows, wanted):
    """(name, (slot, class)) from the name rows, or (text read, None)."""
    readings = rows.read(wanted)
    text = clean_name(" ".join(t.strip() for t, _ in readings if t.strip()))
    for parts in ([wanted[0]], wanted):
        if not parse_name(" ".join(rows.readings[i][0] for i in parts)):
            continue
        texts = [rows.accept(i, _text) for i in parts]
        if None in texts:
            return text, None
        name = clean_name(" ".join(t.strip() for t in texts))
        return name, parse_name(name)
    return text, None


def read_piece(frame, reader, anchor=None):
    x, search_top, level_y, bottom = locate(frame, anchor=anchor)
    top = tooltip_top(frame, x, search_top, level_y)
    found = row_regions(frame, x, top + 2, bottom - (4 if bottom == frame.shape[0] else 12), split=True)
    rows = _Rows(frame, x, found, reader)

    # Name first: a shoulder, medal or other item is turned away after one or two rows.
    above = [i for i, (a, _) in enumerate(found) if a < level_y]
    name, identity = _identify(rows, name_rows(frame, x, [found[i] for i in above])) if above else ("", None)
    if not identity:
        if name and len(name) > 3:
            raise ReadError(f"{SKIPPED} {name}: not a Quanah piece")
        raise ReadError("Couldn't read the item name")

    # Then the stats, a few rows at a time, stopping at Scroll Enhancement.
    below = [i for i, (a, _) in enumerate(found) if a > level_y]
    texts = []
    for n in range(0, len(below), BATCH):
        texts += [t for t, _ in rows.read(below[n : n + BATCH])]
        groups, ended = section(texts)
        if ended:
            break
    else:
        groups, ended = section(texts)
    if not ended:
        raise ReadError("Skill lines cut off")
    lines, raw = [], []
    for group in groups:
        parts = []
        for i in (below[j] for j in group):
            text = rows.accept(i, _text)
            if text is None:
                raise ReadError(f"Unclear line: {rows.readings[i][0].strip()}")
            parts.append(text.strip())
        full = re.sub(r"\s+", " ", " ".join(parts))
        lines.append(match_line(full))
        raw.append(full)
    if not lines:
        raise ReadError("No skill lines found")
    if len(lines) > solver.catalog()["max_lines"]:
        raise ReadError("More than 3 lines read")
    real = [k for k in lines if k != solver.OTHER]
    if len(set(real)) != len(real):
        raise ReadError("Same line read twice")
    slot, item_class = identity
    return {"kind": "quanah", "name": name, "slot": slot, "item_class": item_class, "lines": lines, "raw": raw}


