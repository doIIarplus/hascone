import copy
import hashlib
import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from test_app import ID, client, get

import app
from flaming import characters
from flaming.stats import ReadError
from game_resolution import normalize_scan
from scouter import profiles, shine_levels, shine_scan
from scouter.capture_ready import regions
from scouter.shine_levels import aliases, merge_pages, prepare_save, row_values
from scouter.shine_scan import current_level, panel, read_page, skill_name

FIXTURES = Path(__file__).parent / "fixtures/shine"
# The fixtures' "6th Job" header sits at (3, 4); place it at (433, 154) on the client.
LEFT, TOP = 430, 150


def frame(name, filtered=False):
    image = np.zeros((768, 1366, 3), dtype=np.uint8)
    fixture = cv2.imread(str(FIXTURES / (name + ".png")))
    image[TOP:TOP + fixture.shape[0], LEFT:LEFT + fixture.shape[1]] = fixture
    if filtered:
        image = cv2.resize(image, (2560, 1440), interpolation=cv2.INTER_LINEAR)
        image, _ = normalize_scan(image, "shine:erel_light:top")
    return image


def replay(crops, **kwargs):
    records = json.loads((FIXTURES / "readings.json").read_text(encoding="utf-8"))
    return [records[str(c.shape) + hashlib.sha256(c.tobytes()).hexdigest()] for c in crops]


# The scrolled fixtures are a HEXA class, so stand in SHINE paths for a few of its skills.
SCROLLED = {
    "HEXA Assassinate": "hexa.masteryCore1", "Shadow Assault Boost": "hexa.reinCore2",
    "Sol Janus": "huntSkill.solJanus", "Sol Hecate": "hexa.generalCore2", "Not In This List": "hexa.reinCore1",
}
SCROLLED_NAMES = [
    "HEXA Assassinate", "HEXA Pulverize", "HEXA Meso Explosion", "HEXA Dark Flare", "HEXA Cruel Stab",
    "HEXA Sudden Raid", "HEXA Shadow Veil", "Covert Edge", "Halve Cut", "Covetous Darkness", "Sol Janus",
    "Sol Janus: Dawn", "Sol Hecate", "Sol Hecate: Styx", "Sol Hecate: Charon", "Sol Hecate: Phlegethon",
    "Sol Hecate: Pactum", "HEXA Shadow Walker", "Shadow Assault Boost", "Trickblade Boost", "Sonic Blow Boost",
    "Slash Shadow Formation Boost", "HEXA Stats", "Not In This List",
]


@pytest.fixture
def scrolled_aliases(monkeypatch):
    names = {name: (name, SCROLLED.get(name)) for name in SCROLLED_NAMES}
    monkeypatch.setattr(shine_scan, "aliases", lambda slug: names)
    monkeypatch.setattr(shine_levels, "aliases", lambda slug: names)


def page(name, filtered=False, position=None):
    position = position or ("bottom" if name.endswith("bottom") else "top")
    return read_page(frame(name, filtered), replay, "erel_light", position)["shine_page"]


@pytest.mark.parametrize("filtered", [False, True])
def test_scrolled_list_reads_whole_rows_and_merges_both_ends(filtered, scrolled_aliases):
    top, bottom = page("vi_top", filtered), page("vi_bottom", filtered)
    assert (top["top"], top["bottom"], bottom["top"], bottom["bottom"]) == (True, False, False, True)
    # The bottom page starts part-way through a row; that partial row is skipped.
    assert len(top["rows"]) == 14 and len(bottom["rows"]) == 13
    assert bottom["rows"][0]["name"] == "Sol Janus"
    assert [r["value"] for r in bottom["rows"] if r["value"] != "30"] == ["1", "9", "1"]
    values = merge_pages(top, bottom)
    assert {k: v["value"] for k, v in values.items()} == {
        "hexa.masteryCore1": "30", "hexa.reinCore2": "9", "huntSkill.solJanus": "30",
        "hexa.generalCore2": "30", "hexa.reinCore1": "0",
    }


@pytest.mark.parametrize("filtered", [False, True])
def test_list_without_scrollbar_is_a_single_page_and_missing_skills_are_inactive(filtered):
    single = page("erel", filtered)
    assert single["top"] and single["bottom"]
    assert [(r["name"], r["value"]) for r in single["rows"]] == [("Fall of Melin", "1"), ("Erda Link Stats", "1")]
    values = merge_pages(single, single)
    assert values["hexa.skillCore1"]["value"] == "1"
    assert all(v["value"] == "0" for k, v in values.items() if k != "hexa.skillCore1")
    assert "hexa.hexaStat" not in values  # Erda Link Stats level 1 is not a stone/core count.


def blank_cell(digits):
    """A filled cell drawn from the digit strip, for levels the fixtures do not show."""
    cell = cv2.imread(str(FIXTURES / "vi_bottom.png"))[232:289, 5:245].copy()  # "Sol Hecate: Pactum · 1 / 1"
    strip = shine_scan.reference("vi_digits")
    cell[31:49, 62:110] = strip[:, 8:9]
    for i, d in enumerate(digits):
        cell[31:49, 65 + 8 * i:73 + 8 * i] = strip[:, 8 * int(d):8 * int(d) + 8]
    return cell


@pytest.mark.parametrize("value", list(range(31)))
def test_every_level_decodes_from_exact_glyphs(value):
    assert current_level(blank_cell(str(value)))[0] == value


def test_wrong_scroll_position_clipping_and_cursor_are_rejected(scrolled_aliases):
    with pytest.raises(ReadError, match="bottom"):
        panel(frame("vi_top"), "bottom")
    with pytest.raises(ReadError, match="top"):
        panel(frame("vi_bottom"), "top")
    with pytest.raises(ReadError, match="full"):
        panel(frame("vi_top")[:500])
    with pytest.raises(ReadError, match="cursor"):
        regions(frame("erel"), "shine:erel_light:top", (LEFT + 150, TOP + 200), profiles.class_info("Erel Light"))


def test_an_overlay_cannot_be_mistaken_for_empty_skill_slots():
    image = frame("erel")
    image[TOP + 120:TOP + 180, LEFT + 20:LEFT + 480] = 230
    with pytest.raises(ReadError, match="obscured"):
        read_page(image, replay, "erel_light", "top")


def test_a_covered_row_edge_is_not_skipped_as_a_partial_row(scrolled_aliases):
    image = frame("vi_top")
    image[TOP + 230:TOP + 270, LEFT:LEFT + 30] = 40
    with pytest.raises(ReadError, match="obscured"):
        read_page(image, replay, "erel_light", "top")


def test_unclear_level_is_rejected():
    cell = blank_cell("30")
    cell[33:47, 65:81] = 200
    with pytest.raises(ReadError, match="level"):
        current_level(cell)


@pytest.mark.parametrize("damage", ["gap", "changed", "other_class"])
def test_incomplete_or_inconsistent_pages_never_produce_zero_levels(damage, scrolled_aliases):
    top, bottom = page("vi_top"), page("vi_bottom")
    if damage == "gap":
        bottom["rows"] = bottom["rows"][-1:]
    elif damage == "changed":
        bottom["rows"][0]["value"] = "5"
    else:
        bottom["class"] = "sia_astelle"
    with pytest.raises(ReadError):
        merge_pages(top, bottom)


def test_name_matching_does_not_confuse_auxiliary_skills_or_ambiguous_truncation():
    names = aliases("erel_light")
    assert skill_name("Sol Hecate: Pactum", names) == ("Sol Hecate: Pactum", None)
    assert skill_name("Eternal Guardian...", names)[1] == "hexa.reinCore3"
    assert skill_name("SHINE Stellar I -...", aliases("sia_astelle"))[1] == "hexa.masteryCore1"
    assert skill_name("SHINE Stellar II -...", aliases("sia_astelle"))[1] == "hexa.masteryCore2"
    with pytest.raises(ReadError):
        skill_name("SHINE Stellar...", aliases("sia_astelle"))
    with pytest.raises(ReadError):
        skill_name("Celestial Design", names)


def test_shared_mastery_conflict_rejects_page():
    row = {"path": "hexa.masteryCore2", "confidence": 1, "text": ""}
    with pytest.raises(ReadError, match="Shared mastery"):
        row_values([{**row, "name": "SHINE Fury of Roan", "value": "4"},
                    {**row, "name": "SHINE Sting of Roan", "value": "5"}])


def shine_character():
    data = characters.load(ID)
    data["class"] = "ErelLight"
    characters.write(data)


def test_shine_steps_replace_standard_matrix_and_hide_placeholder_cores(client):
    shine_character()
    steps = get(client, f"/api/characters/{ID}/steps").json
    assert [s["mode"] for s in steps[-2:]] == ["shine:erel_light:top", "shine:erel_light:bottom"]
    assert not any(s["mode"].startswith("hexa") for s in steps)
    info = profiles.load(ID)["class_info"]
    assert "hexa.masteryCore3" not in profiles.input_paths(info)
    assert info["cores"]["generalCore3"]["english_title"] == "SHINE Tree of Stars"


def test_pages_save_in_background_without_clearing_absent_skills_early(client, monkeypatch, scrolled_aliases):
    import ocr_worker

    shine_character()
    profiles.save_scan(ID, {"hexa.reinCore1": {"value": "15"}}, [], profiles.now())
    for name, position in [("vi_top", "top"), ("vi_bottom", "bottom")]:
        result = read_page(frame(name), replay, "erel_light", position)
        monkeypatch.setattr(ocr_worker, "read", Mock(return_value=result))
        body = {"character": ID, "session": "scan-one", "mode": "shine:erel_light:" + position}
        app._process_character_capture(body, frame(name), {})
        stored = profiles.load(ID)
        assert stored["inputs"]["hexa.reinCore1"] == ("15" if position == "top" else "0")
        assert stored["shine_levels"]["complete"] is (position == "bottom")
    assert stored["inputs"]["hexa.reinCore2"] == "9"


def test_manual_edits_and_pages_from_another_session_are_protected(client, scrolled_aliases):
    shine_character()
    data = profiles.load(ID)
    _, state = prepare_save(data, page("vi_top"), "one", {})
    data["shine_levels"] = state
    with pytest.raises(ReadError, match="not verified"):
        prepare_save(data, page("vi_bottom"), "two", {})
    data["manual_versions"] = {"hexa.masteryCore1": 3}
    with pytest.raises(ReadError, match="changed"):
        prepare_save(data, page("vi_bottom"), "one", copy.deepcopy(data["manual_versions"]))


def test_stale_placeholder_inputs_do_not_reach_shine_payload(client):
    shine_character()
    data = profiles.load(ID)
    data["inputs"] = {"hexa.masteryCore3": "15", "hexa.masteryCore4": "30"}
    assert profiles.effective(data)["hexa"]["masteryCore3"] == "0"
    assert profiles.effective(data)["hexa"]["masteryCore4"] == "0"


def test_live_1440p_shine_capture_releases_game_before_ocr_finishes(client, monkeypatch):
    import capture
    import hover_queue
    import ocr_worker

    shine_character()
    image = cv2.resize(frame("erel"), (2560, 1440), interpolation=cv2.INTER_LINEAR)
    monkeypatch.setattr(capture, "frame", lambda window: image.copy())
    monkeypatch.setattr(capture, "pointer", lambda window: (0, 0))
    started, release = threading.Event(), threading.Event()

    def read(image, mode):
        started.set()
        assert release.wait(5)
        return read_page(image, replay, "erel_light", "top")

    monkeypatch.setattr(ocr_worker, "read", read)
    hover_queue.reset(ID)
    try:
        app.perform({"character": ID, "session": "live-shine", "mode": "shine:erel_light:top",
                     "watch": True, "background": True, "window": 1}, app.generation, "", 0)
        assert app.job["status"] == "captured"
        assert started.wait(2)
        assert capture._session is None
        assert hover_queue.status(ID)["pending"] == ["shine:erel_light:top"]
    finally:
        release.set()
        for _ in range(300):
            if not hover_queue.status(ID)["pending"]:
                break
            time.sleep(.01)
    assert hover_queue.status(ID)["failed"] == {}
    assert profiles.load(ID)["inputs"]["hexa.skillCore1"] == "1"
