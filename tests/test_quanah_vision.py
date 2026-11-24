"""The Quanah tooltip reader.

Real event-item screenshots live in fixtures/quanah with OCR readings recorded by
tools/record_quanah_fixtures.py. Tooltip finding is also checked on the GMS hover
fixtures, and edge cases of parsing run with a scripted reader.
"""

import hashlib
import json
from pathlib import Path

import cv2
import pytest

from equipment_scan import ROW_MAX, row_crop, row_regions, tooltip_bounds
from flaming.stats import ReadError
from quanah import vision

FIXTURES = Path(__file__).parent / "fixtures"


def frame(name="equipment_hover/hat.png"):
    return cv2.imread(str(FIXTURES / name))


def comparison():
    """An inventory hover: the equipped hat's tooltip, plus a copy without its label to the left."""
    image = frame()
    x, ay, bottom = tooltip_bounds(image, allow_clipped_footer=True)
    tooltip = image[ay - 75 : bottom, x : x + 323].copy()
    # Blank "Currently Equipped" in the copy; the hovered item shows no label.
    tooltip[70:95, 100:220] = tooltip[100:125, 250:280].mean(axis=(0, 1))
    left = x - 400
    image[ay - 75 : bottom, left : left + 323] = tooltip
    return image, left, x


def test_locate_matches_the_equipment_tooltip_bounds():
    for name in ("equipment_hover/hat.png", "equipment_hover/gloves.png", "resolution_1366/hat.png"):
        image = frame(name)
        x, _, level_y, bottom = vision.locate(image)
        assert (x, level_y - vision.EQUIPPED_DY, bottom) == tooltip_bounds(image, allow_clipped_footer=True)


def test_locate_picks_the_hovered_tooltip_over_the_comparison():
    image, hovered, equipped = comparison()
    assert vision.locate(image)[0] == hovered
    # The pointer does not override which tooltip is the comparison.
    assert vision.locate(image, pointer=(equipped + 150, 500))[0] == hovered


def two_unlabelled():
    """Two tooltips, neither marked "Currently Equipped": only the cursor tells them apart."""
    image, left, right = comparison()
    x, ay, bottom = tooltip_bounds(frame(), allow_clipped_footer=True)
    image[ay - 5 : ay + 20, right + 100 : right + 220] = image[ay + 25 : ay + 50, right + 250 : right + 280].mean(axis=(0, 1))
    return image, left, right


def test_the_captured_tooltip_is_read_without_the_cursor():
    image, left, right = two_unlabelled()
    with pytest.raises(ReadError, match="one item at a time"):
        vision.locate(image)
    captured = vision.locate(image, pointer=(right + 150, 500))
    assert captured[0] == right
    # The OCR step gets the capture's position instead of the cursor, and reads that same tooltip.
    assert vision.locate(image, anchor=vision.anchor_of(captured)) == captured
    with pytest.raises(ReadError, match="one item at a time"):
        vision.locate(image, anchor=(5, 5))


def test_reader_passes_the_captured_position(monkeypatch):
    import reader
    from quanah import vision as module

    seen = []
    monkeypatch.setattr(reader, "_recognizer", lambda: None)
    monkeypatch.setattr(module, "read_piece", lambda image, ocr, anchor=None: seen.append(anchor) or {})
    reader.read(frame(), "quanah:1191:446")
    reader.read(frame(), "quanah")
    assert seen == [(1191, 446), None]


def test_no_tooltip():
    image = frame()
    image[:] = 0
    with pytest.raises(ReadError, match="Hover an event item"):
        vision.locate(image)


def test_signature_follows_the_tooltip_not_its_position():
    image, _, _ = comparison()
    hovered = vision.signature(image, vision.locate(image))
    original = frame()
    assert vision.same_tooltip(hovered, vision.signature(original, vision.locate(original)))
    gloves = frame("equipment_hover/gloves.png")
    assert not vision.same_tooltip(hovered, vision.signature(gloves, vision.locate(gloves)))
    assert not vision.same_tooltip(hovered, None)


QUANAH = FIXTURES / "quanah"


def replay(crops, **kwargs):
    records = json.loads((QUANAH / "readings.json").read_text(encoding="utf-8"))
    return [tuple(records[str(c.shape) + hashlib.sha256(c.tobytes()).hexdigest()]) for c in crops]


@pytest.mark.parametrize("name, slot, lines", [
    # Inventory hover: the hovered top is left, the equipped comparison right. The ATT line wraps.
    ("top_comparison", "top", ["atk", "wh", "reg"]),
    # The same equipped top alone, as in an Equipment-window hover.
    ("top_equipped", "top", ["atk", "magician", "wh"]),
    # Its bottom edge is cut off, as when the game pushes a tooltip against the screen's bottom.
    ("hat_bottom_clipped", "hat", ["dl", "reg", "dmg"]),
    # One line only, and job lines that read "Attack Skill Level Lv. +1".
    ("bottom_comparison", "bottom", ["warrior"]),
    # Drawn against the screenshot's right edge, without its last border pixels.
    ("bottom_equipped", "bottom", ["reg", "wh", "warrior"]),
    ("top2_comparison", "top", ["atk", "crit", "bowman"]),
])
def test_reads_real_event_tooltips(name, slot, lines):
    piece = vision.read_piece(cv2.imread(str(QUANAH / f"{name}.png")), replay)
    assert (piece["slot"], piece["item_class"], piece["lines"]) == (slot, "warrior", lines)
    word = {"bottom": "Pants"}.get(slot, slot.title())
    assert piece["name"] == f"Libae's Supercharged {word} (Warrior)"


def test_other_libae_pieces_are_named_when_skipped():
    # A real failed capture: the cursor rests on the name, which wraps onto a second row.
    with pytest.raises(ReadError, match=r"^Skipped Libae's Supercharged Shoulder Accessory \(Warrior\): not a Quanah piece$"):
        vision.read_piece(cv2.imread(str(QUANAH / "shoulder_equipped.png")), replay)


def test_cursor_joined_rows_are_split_not_dropped():
    image = cv2.imread(str(QUANAH / "shoulder_equipped.png"))
    x, top, level_y, bottom = vision.locate(image)
    joined = [(a, b) for a, b in row_regions(image, x, top, bottom) if a < 90]
    split = [(a, b) for a, b in row_regions(image, x, top, bottom, split=True) if a < 90]
    # The second star row and the name were one block, too tall for a row, so the name was lost.
    assert len(split) > len(joined)
    assert all(b - a <= ROW_MAX + 5 for a, b in split)


def test_wrapped_line_is_kept_whole():
    piece = vision.read_piece(cv2.imread(str(QUANAH / "top_comparison.png")), replay)
    assert piece["raw"][0] == "[Hologram] Attack Power & Magic ATT Enhancement Skill Lv. +1"


@pytest.mark.parametrize("text, key", [
    ("Dimensional Leap Lv. +1", "dl"),
    ("Dimensional Leap Lv.+1", "dl"),
    ("White Hole Lv. +1", "wh"),
    ("[Hologram] Registry Lv. +1", "reg"),
    ("Hologram] Registry Lv. +1", "reg"),
    ("[Hologram] Damage Enhancement Skill Lv. +1", "dmg"),
    ("[Hologram] Attack Power & Magic ATT Enhancement Skill Lv. +1", "atk"),
    ("Attack Power & Magic ATT Enhancement Skill Lv. +1", "atk"),
    ("Critical Damage Enhancement Skill Lv. +1", "crit"),
    ("[Hologram] Critical Damage Enhancement Skill Lv. +1", "crit"),
    ("[Hologram] Warrior Attack Skill Lv. +1", "warrior"),
    ("[Hologram] Warrior Attack Skill Level Lv. +1", "warrior"),
    ("[Hologram] Bowman Attack Skill Level Lv. +1", "bowman"),
    ("[Hologram] Magician Attack Skill Lv. +1", "magician"),
    ("[Hologram] Bowman Attack Skill Lv. +1", "bowman"),
    ("[Hologram] Thief Attack Skill Lv. +1", "thief"),
    ("[Hologram] Pirate Attack Skill Lv. +1", "pirate"),
    # A wrapped line's second row alone is not a skill line.
    ("Skill Lv. +1", "other"),
    ("Boss Damage +10%", "other"),
    ("Ignored Enemy DEF +10%", "other"),
    ("Some Future Skill Lv. +1", "other"),
])
def test_match_line(text, key):
    assert vision.match_line(text) == key


def test_section_joins_wrapped_rows_and_stops_at_scroll_enhancement():
    texts = ["Set Effect", "STR +60 (50 +10)", "Enemy DEF Ignored +5%",
             "[Hologram] Attack Power & Magic ATT Enhancement", "Skill Lv. +1",
             "Boss Damage +10%", "White Hole Lv. +1", "Scroll Enhancement None", "Dimensional Leap Lv. +1"]
    assert vision.section(texts) == ([[3, 4], [5], [6]], True)
    # Without the Scroll Enhancement row, the skill lines may continue off screen.
    assert vision.section(texts[:7])[1] is False


def test_section_without_a_base_ied_row_starts_at_the_first_skill_line():
    texts = ["STR +60 (50 +10)", "Defense +418 (325 +93)", "White Hole Lv. +1", "Jewel Stats"]
    assert vision.section(texts) == ([[2]], True)


def test_clean_name_drops_the_cursor_read_as_a_mark():
    assert vision.clean_name("_ibae's Supercharged Hat (Warrior)") == "ibae's Supercharged Hat (Warrior)"
    assert vision.clean_name("  · [Hologram] Top") == "[Hologram] Top"
    assert vision.clean_name("Libae's Supercharged Top (Warrior)") == "Libae's Supercharged Top (Warrior)"


def test_parse_name():
    assert vision.parse_name("Libae's Supercharged Hat (Warrior)") == ("hat", "warrior")
    assert vision.parse_name("Libaes Supercharged Pants ( Bowman )") == ("bottom", "bowman")
    assert vision.parse_name("Libae's Supercharged Cape (Magician") == ("cape", "magician")
    assert vision.parse_name("Libae's Supercharged Ring (Thief)") is None
    assert vision.parse_name("Heroic: Untradable") is None
    assert vision.parse_name("Required Job Warrior") is None
    assert vision.parse_name("Set Effect Libae's Supercharged Equipment Set") is None


def crop_key(crop):
    return str(crop.shape) + hashlib.sha256(crop.tobytes()).hexdigest()


class Scripted:
    """A reader answering by row, as read_piece finds them: NAME on the name row, LINES below Required Level."""

    def __init__(self, image, name, lines, confidence=0.99):
        x, search_top, level_y, bottom = vision.locate(image)
        top = vision.tooltip_top(image, x, search_top, level_y)
        rows = row_regions(image, x, top + 2, bottom - (4 if bottom == image.shape[0] else 12), split=True)
        above = [r for r in rows if r[0] < level_y]
        below = [r for r in rows if r[0] > level_y]
        texts = {above[i]: ("Heroic: Untradable", 0.99) for i in range(len(above))}
        texts[above[vision.name_rows(image, x, above)[0]]] = (name, 0.99)
        for i, row in enumerate(below):
            text = lines[i] if i < len(lines) else ""
            texts[row] = (text, 0.99 if "Lv." not in text else confidence)
        self.readings = {crop_key(row_crop(image, x, row)): t for row, t in texts.items()}
        self.calls = []

    def __call__(self, crops, use_cache=True):
        self.calls.append(len(crops))
        if not use_cache:  # A verification retry reads nothing better.
            return [("", 0.0)] * len(crops)
        return [self.readings[crop_key(c)] for c in crops]


IED, END = "Enemy DEF Ignored +5%", "Scroll Enhancement None"


def test_read_piece_with_other_lines():
    image, _, _ = comparison()
    reader = Scripted(image, "Libae's Supercharged Hat (Warrior)",
                      ["STR +143", IED, "Dimensional Leap Lv. +1", "Boss Damage +10%",
                       "[Hologram] Damage Enhancement Skill Lv. +1", END, "Mystery Skill Lv. +1"])
    piece = vision.read_piece(image, reader)
    assert piece["slot"] == "hat" and piece["item_class"] == "warrior"
    assert piece["lines"] == ["dl", "other", "dmg"]
    assert piece["raw"][1] == "Boss Damage +10%"


def test_reading_stops_at_scroll_enhancement():
    image, _, _ = comparison()
    reader = Scripted(image, "Libae's Supercharged Hat (Warrior)",
                      [IED, "White Hole Lv. +1", END] + ["Jewel Stats"] * 20)
    assert vision.read_piece(image, reader)["lines"] == ["wh"]
    # The name row(s), then one batch: the rows after Scroll Enhancement are never read.
    assert reader.calls[0] <= 2 and reader.calls[1:] == [vision.BATCH]


def test_other_items_are_turned_away_after_reading_the_name():
    reader = Scripted(cv2.imread(str(QUANAH / "medal_equipped.png")), "HYPER BURNING MAX", [])
    with pytest.raises(ReadError, match="^Skipped HYPER BURNING MAX: not a Quanah piece$"):
        vision.read_piece(cv2.imread(str(QUANAH / "medal_equipped.png")), reader)
    assert reader.calls == [1]


def test_tooltip_top_ignores_windows_above_it():
    image = cv2.imread(str(QUANAH / "medal_equipped.png"))
    x, search_top, level_y, _ = vision.locate(image)
    # The inventory window above the medal's tooltip is not mistaken for its header.
    assert search_top < vision.tooltip_top(image, x, search_top, level_y) == 151


def test_read_piece_rejects_impossible_readings():
    image = frame()
    for lines, message in [([IED, "Dimensional Leap Lv. +1", "Dimensional Leap Lv. +1", END], "Same line read twice"),
                           ([IED, END], "No skill lines found"),
                           ([IED] + ["White Hole Lv. +1"] * 4 + [END], "More than 3 lines read"),
                           ([IED, "White Hole Lv. +1"], "Skill lines cut off")]:
        with pytest.raises(ReadError, match=message):
            vision.read_piece(image, Scripted(image, "Libae's Supercharged Top (Thief)", lines))
    with pytest.raises(ReadError, match="^Skipped Arcane Umbra Hat: not a Quanah piece$"):
        vision.read_piece(image, Scripted(image, "Arcane Umbra Hat", [IED, "White Hole Lv. +1", END]))


def test_uncertain_lines_are_not_guessed():
    image = frame()
    with pytest.raises(ReadError, match=r"^Unclear line: White Hole Lv\. \+1$"):
        vision.read_piece(image, Scripted(image, "Libae's Supercharged Top (Thief)",
                                          [IED, "White Hole Lv. +1", END], confidence=0.5))
