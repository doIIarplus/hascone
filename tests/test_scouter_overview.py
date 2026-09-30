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
        vision._parse_overview_field("stat.ignoreDef", "96.91%", .96561795, {})
    with pytest.raises(vision.ReadError, match=r"96\.99%; requires 97%"):
        vision._parse_overview_field("stat.ignoreDef", "96.91%", .96999999, {})


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
        vision._parse_overview_field("stat.level", *results[index], values, confirmed=True)
        assert values["stat.level"]["value"] == "295"
    else:
        assert results[index] == ("L.295", .9131)


@pytest.mark.parametrize("background", ["purple", "lavender", "pink"])
def test_profile_backgrounds_do_not_wash_out_level(background):
    # Live level pills on user profile backgrounds, with their recorded OCR readings.
    records = json.loads((CHARACTER_INFO / "readings.json").read_text(encoding="utf8"))

    def reader(crops, **kwargs):
        return [tuple(records[str(c.shape) + hashlib.sha256(c.tobytes()).hexdigest()]) for c in crops]

    fields = list(vision.OVERVIEW_FIELDS)
    level = fields.index("stat.level")
    originals = [np.zeros((21, 51, 3), np.uint8)] * len(fields)
    originals[level] = cv2.imread(str(CHARACTER_INFO / f"{background}_level.png"))
    results = [("1", 1.0)] * len(fields)
    results[level] = reader([vision.foreground(originals[level])])[0]
    confirmed = vision._retry_uncertain_overview(reader, results, originals)
    values = {}
    vision._parse_overview_field("stat.level", *results[level], values, confirmed="stat.level" in confirmed)
    assert values["stat.level"]["value"] == "290"
