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
