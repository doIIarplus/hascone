import numpy as np
import pytest

from scouter import hexa_scan


@pytest.mark.parametrize("levels,accepted", [([6, 6], True), ([6, 7], False)])
def test_paired_mastery_tooltip_levels(monkeypatch, levels, accepted):
    monkeypatch.setattr(hexa_scan, "matrix_origin", lambda frame: (0, 0))
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    x, y = hexa_scan.NODES["masteryCore2"]
    frame[y+50:y+60, x+70:x+150] = 255
    frame[y+90:y+100, x+70:x+150] = 255
    def reader(crops):
        return [(f"[Level {level}]", .99) for level in levels]
    if accepted:
        assert hexa_scan.read_hover(frame, reader, "masteryCore2")["values"]["hexa.masteryCore2"]["value"] == "6"
    else:
        with pytest.raises(hexa_scan.ReadError):
            hexa_scan.read_hover(frame, reader, "masteryCore2")


def test_pending_unlearned_node_recovers_from_badge(monkeypatch):
    monkeypatch.setattr(hexa_scan, "matrix_origin", lambda frame: (0, 0))
    monkeypatch.setattr(hexa_scan, "locked", lambda *args: False)
    monkeypatch.setattr(hexa_scan, "badge_level", lambda *args: 0)
    result = hexa_scan.read_hover(None, lambda crops: pytest.fail("No tooltip needed"), "generalCore2")
    assert result["values"]["hexa.generalCore2"]["value"] == "0"
