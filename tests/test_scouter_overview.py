import pytest

from scouter import vision


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
    readings = iter([("NameTest", .99), ("other", .99)])
    vision._retry_uncertain_identity(lambda crops, **kwargs: [next(readings)], results, originals)
    assert results[index] == ("HameTest", .91)
