import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from scouter import vision

CHARACTER_INFO = Path(__file__).parent / "fixtures/character_info"


def test_collapsed_character_panel_keeps_waiting(monkeypatch):
    monkeypatch.setattr(vision, "origin", lambda frame: (100, 100))
    def absent(*args, **kwargs):
        raise vision.ReadError("missing")
    monkeypatch.setattr(vision, "anchor", absent)
    with pytest.raises(vision.ReadError, match="Expand Details"):
        vision.overview(None, lambda crops: pytest.fail("OCR must wait for Details"))


def test_unrelated_stats_heading_is_rejected(monkeypatch):
    monkeypatch.setattr(vision, "origin", lambda frame: (100, 100))
    monkeypatch.setattr(vision, "anchor", lambda *args: (900, 500))
    with pytest.raises(vision.ReadError, match="fully visible"):
        vision.overview(None, lambda crops: pytest.fail("Wrong panel"))


def test_uncertain_name_retry_requires_agreement():
    import numpy as np

    from scouter import vision
    index = list(vision.OVERVIEW_FIELDS).index("character_name")
    originals = [np.zeros((21, 112, 3), dtype=np.uint8)] * len(vision.OVERVIEW_FIELDS)
    results = [("ok", 1.0)] * len(originals)
    results[index] = ("HameTest", .91)
    vision._retry_uncertain_identity(lambda crops, **kwargs: [("NameTest", .99)], results, originals)
    assert results[index] == ("NameTest", .99)
    results[index] = ("HameTest", .91)
    # Neither the padded pair nor the background-adjusted pair agrees.
    readings = iter([("NameTest", .99), ("other", .99), ("NameTest", .99), ("other", .99)])
    vision._retry_uncertain_identity(lambda crops, **kwargs: [next(readings)], results, originals)
    assert results[index] == ("HameTest", .91)



@pytest.mark.parametrize("second,accepted", [("NotFamAny.", True), ("NotFamAny", False)])
def test_cut_off_name_renderings_agree_despite_dot_count(second, accepted):
    # Live capture: "NotFamAny.." read with two, one or no dots across renderings.
    index = list(vision.OVERVIEW_FIELDS).index("character_name")
    originals = [np.zeros((21, 112, 3), dtype=np.uint8)] * len(vision.OVERVIEW_FIELDS)
    results = [("ok", 1.0)] * len(originals)
    results[index] = ("NotFamAny..", .9602)
    readings = iter([("NotFamAny..", .9632), ("NotFamAny", .9750), ("NotFamAny..", .9827), (second, .9734)])
    vision._retry_uncertain_identity(lambda crops, **kwargs: [next(readings)], results, originals)
    assert (results[index][1] >= .97) is accepted

@pytest.mark.parametrize("retry_text,accepted", [("96.91%", True), ("96.97%", False)])
def test_numeric_retry_uses_uncached_padded_crop_and_rejects_conflicts(retry_text, accepted):
    import numpy as np
    index = list(vision.OVERVIEW_FIELDS).index("stat.ignoreDef")
    results = [("1", 1.0)] * len(vision.OVERVIEW_FIELDS)
    results[index] = ("96.91%", .96561795)
    originals = [np.zeros((21, 52, 3), dtype=np.uint8)] * len(results)
    calls = []
    def reader(crops, *, use_cache=True):
        assert not use_cache
        calls.append(crops[0].shape)
        return [("", 0.0)] if len(calls) == 1 else [(retry_text, .997919)]
    vision._retry_uncertain_overview(reader, results, originals)
    assert calls == [(21, 52, 3), (37, 68, 3)]
    assert results[index] == (("96.91%", .997919) if accepted else ("96.91%", .96561795))


def test_low_confidence_error_does_not_round_up_to_the_cutoff():
    with pytest.raises(vision.ReadError, match=r"96\.56%; requires 97%"):
        vision._parse_overview_field("stat.ignoreDef", "96.91%", .96561795, {}, {})
    with pytest.raises(vision.ReadError, match=r"96\.99%; requires 97%"):
        vision._parse_overview_field("stat.ignoreDef", "96.91%", .96999999, {}, {})


@pytest.mark.parametrize("digits,accepted", [("295", True), ("285", False)])
def test_level_retry_recovers_broken_prefix_but_rejects_conflicting_digits(digits, accepted):
    import numpy as np

    index = list(vision.OVERVIEW_FIELDS).index("stat.level")
    originals = [np.zeros((21, 51, 3), dtype=np.uint8)] * len(vision.OVERVIEW_FIELDS)
    results = [("1", 1.0)] * len(originals)
    results[index] = ("L.295", .9131)
    # Actual failure: both full crops lose the v, while the padded reading
    # recovers the label at insufficient confidence. Digits remain clear.
    # The background-adjusted pill renderings come first and lose the v too.
    readings = iter([("L.295", .92), ("L.295", .93), ("L.295", .9169), ("Lv. 295", .7634), (digits, .9999)])
    shapes = []

    def reader(crops, *, use_cache=True):
        assert not use_cache
        shapes.append(crops[0].shape)
        return [next(readings)]

    confirmed = vision._retry_uncertain_overview(reader, results, originals)
    assert shapes == [(21, 51, 3), (32, 76, 3), (21, 51, 3), (37, 67, 3), (21, 34, 3)]
    assert ("stat.level" in confirmed) is accepted
    if accepted:
        values = {}
        vision._parse_overview_field("stat.level", *results[index], values, {}, confirmed=True)
        assert values["stat.level"]["value"] == "295"
    else:
        assert results[index] == ("L.295", .9131)


@pytest.mark.parametrize("background", ["purple", "lavender", "pink"])
def test_profile_backgrounds_do_not_wash_out_level_and_class(background):
    # Live pills on user profile backgrounds, with their recorded OCR readings.
    records = json.loads((CHARACTER_INFO / "readings.json").read_text(encoding="utf8"))

    def reader(crops, **kwargs):
        return [tuple(records[str(c.shape) + hashlib.sha256(c.tobytes()).hexdigest()]) for c in crops]

    fields = list(vision.OVERVIEW_FIELDS)
    level, job = fields.index("stat.level"), fields.index("character_class")
    originals = [np.zeros((21, 51, 3), np.uint8)] * len(fields)
    originals[level] = cv2.imread(str(CHARACTER_INFO / f"{background}_level.png"))
    originals[job] = cv2.imread(str(CHARACTER_INFO / f"{background}_class.png"))
    results = [("1", 1.0)] * len(fields)
    results[level], results[job] = reader([vision.foreground(originals[level]), vision.foreground(originals[job])])
    assert min(results[level][1], results[job][1]) < 0.97
    vision._retry_uncertain_identity(reader, results, originals)
    confirmed = vision._retry_uncertain_overview(reader, results, originals)
    values, identity = {}, {}
    vision._parse_overview_field("stat.level", *results[level], values, identity, confirmed="stat.level" in confirmed)
    vision._parse_overview_field("character_class", *results[job], values, identity)
    assert values["stat.level"]["value"] == "290"
    assert identity["character_class"] == "Illium"
