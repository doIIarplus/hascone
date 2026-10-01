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
from scouter import profiles
from scouter.capture_ready import regions
from scouter.shine_levels import aliases, merge_pages, prepare_save
from scouter.shine_scan import panel, read_page, skill_name

FIXTURES = Path(__file__).parent / "fixtures/shine"


def frame(name, filtered=False):
    image = np.zeros((768, 1366, 3), dtype=np.uint8)
    image[245:524, 579:877] = cv2.imread(str(FIXTURES / (name + ".png")))
    if filtered:
        image = cv2.resize(image, (2560, 1440), interpolation=cv2.INTER_LINEAR)
        image, _ = normalize_scan(image, "shine:erel_light:top")
    return image


def replay(crops, **kwargs):
    records = json.loads((FIXTURES / "readings.json").read_text(encoding="utf-8"))
    return [records[str(c.shape) + hashlib.sha256(c.tobytes()).hexdigest()] for c in crops]


def page(name, filtered=False):
    return read_page(frame(name, filtered), replay, "sia_astelle" if name == "sia" else "erel_light",
                     "bottom" if name.endswith("bottom") else "top")["shine_page"]


@pytest.mark.parametrize("filtered", [False, True])
def test_erel_complete_list_and_shared_mastery(filtered):
    top, bottom = page("erel_top", filtered), page("erel_bottom", filtered)
    assert len(top["rows"]) == 12 and len(bottom["rows"]) == 11
    values = merge_pages(top, bottom)
    assert {k: v["value"] for k, v in values.items()} == {
        "hexa.masteryCore1": "26", "hexa.masteryCore2": "4",
        "hexa.skillCore1": "1", "hexa.skillCore2": "9", "hexa.reinCore3": "20",
        "hexa.generalCore2": "1", "hexa.generalCore3": "1", "huntSkill.solJanus": "1",
        "hexa.reinCore1": "0", "hexa.reinCore2": "0", "hexa.reinCore4": "0",
    }
    assert "hexa.hexaStat" not in values  # Erda Link Stats level 1 is not a stone/core count.


@pytest.mark.parametrize("filtered", [False, True])
def test_sia_single_page_has_no_scroll_and_missing_skills_are_inactive(filtered):
    single = page("sia", filtered)
    assert single["top"] and single["bottom"]
    values = merge_pages(single, single)
    assert values["hexa.skillCore1"]["value"] == "1"
    assert all(v["value"] == "0" for k, v in values.items() if k != "hexa.skillCore1")


def test_wrong_scroll_position_clipping_and_cursor_are_rejected():
    with pytest.raises(ReadError, match="bottom"):
        panel(frame("erel_top"), "bottom")
    with pytest.raises(ReadError, match="top"):
        panel(frame("erel_bottom"), "top")
    with pytest.raises(ReadError, match="full"):
        panel(frame("erel_top")[:500])
    with pytest.raises(ReadError, match="cursor"):
        regions(frame("erel_top"), "shine:erel_light:top", (620, 300), profiles.class_info("Erel Light"))


def test_an_overlay_cannot_be_mistaken_for_empty_skill_slots():
    image = frame("erel_bottom")
    image[488:524, 581:864] = 239
    with pytest.raises(ReadError, match="obscured"):
        read_page(image, replay, "erel_light", "bottom")


@pytest.mark.parametrize("damage", ["gap", "changed", "other_class"])
def test_incomplete_or_inconsistent_pages_never_produce_zero_levels(damage):
    top, bottom = page("erel_top"), page("erel_bottom")
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
    def conflict(crops, **kwargs):
        result = replay(crops, **kwargs)
        if len(result) == 24:
            result[5] = ("5", .999)
        return result
    with pytest.raises(ReadError, match="Shared mastery"):
        read_page(frame("erel_top"), conflict, "erel_light", "top")


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


def test_pages_save_in_background_without_clearing_absent_skills_early(client, monkeypatch):
    import ocr_worker

    shine_character()
    profiles.save_scan(ID, {"hexa.reinCore1": {"value": "15"}}, [], profiles.now())
    for name, position in [("erel_top", "top"), ("erel_bottom", "bottom")]:
        result = read_page(frame(name), replay, "erel_light", position)
        monkeypatch.setattr(ocr_worker, "read", Mock(return_value=result))
        body = {"character": ID, "session": "scan-one", "mode": "shine:erel_light:" + position}
        app._process_character_capture(body, frame(name), {})
        stored = profiles.load(ID)
        assert stored["inputs"]["hexa.reinCore1"] == ("15" if position == "top" else "0")
        assert stored["shine_levels"]["complete"] is (position == "bottom")
    assert stored["inputs"]["hexa.masteryCore1"] == "26"


def test_manual_edits_and_pages_from_another_session_are_protected(client):
    shine_character()
    data = profiles.load(ID)
    _, state = prepare_save(data, page("erel_top"), "one", {})
    data["shine_levels"] = state
    with pytest.raises(ReadError, match="not verified"):
        prepare_save(data, page("erel_bottom"), "two", {})
    data["manual_versions"] = {"hexa.masteryCore1": 3}
    with pytest.raises(ReadError, match="changed"):
        prepare_save(data, page("erel_bottom"), "one", copy.deepcopy(data["manual_versions"]))


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
    image = cv2.resize(frame("erel_top"), (2560, 1440), interpolation=cv2.INTER_LINEAR)
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
    assert profiles.load(ID)["inputs"]["hexa.masteryCore1"] == "26"
