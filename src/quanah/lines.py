"""Match a skill line's tooltip text to its catalog key. No image libraries, so the store can use it."""

import re
from difflib import SequenceMatcher

from quanah import solver

# Messages for items that are not Quanah pieces start with this; they are skipped, not failed.
# It lives here, not in vision, so the web server can check it without loading OpenCV.
SKIPPED = "Skipped"
MATCH_RATIO = 0.92
SKILL_END = re.compile(r"Lv\.?\s*\+\s*\d+\s*$", re.I)


def normalise(text):
    # "[Hologram]" prefixes most skill lines, and some job lines read "Attack Skill Level Lv. +1"
    # where others read "Attack Skill Lv. +1"; neither word tells lines apart.
    return re.sub(r"[^a-z0-9+]", "", re.sub(r"hologram|\blevel\b", "", text.casefold()))


def match_line(text):
    """The catalog key for a skill line, or "other" for anything else (e.g. boss damage)."""
    if not SKILL_END.search(text):
        return solver.OTHER
    clean = normalise(text)
    best, ratio = solver.OTHER, 0.0
    for line in solver.catalog()["lines"]:
        score = SequenceMatcher(None, clean, normalise(line["text"])).ratio()
        if score > ratio:
            best, ratio = line["key"], score
    return best if ratio >= MATCH_RATIO else solver.OTHER


def rematch(raw):
    """Keys for a scanned piece's saved texts, or None when they don't make a valid piece."""
    if not raw or len(raw) > solver.catalog()["max_lines"]:
        return None
    keys = [match_line(text) for text in raw]
    real = [k for k in keys if k != solver.OTHER]
    return keys if len(set(real)) == len(real) else None
