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
