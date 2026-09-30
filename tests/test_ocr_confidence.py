from unittest.mock import Mock

import numpy as np
import pytest

from ocr_confidence import verify
from scouter import vision


@pytest.mark.parametrize("first,second,accepted", [
    (("18%", .97), None, True),
    (("18%", .90), ("18%", .90), True),
    (("18%", .96), ("18 %", .94), True),
    (("18%", .899), ("18%", .96), False),
    (("18%", .96), ("18%", .899), False),
    (("18%", .96), ("78%", .99), False),
    (("1.8%", .96), ("18%", .99), False),
    (("18%", .96), ("18", .99), False),
    (("18%", .96), ("-18%", .99), False),
    (("?", .80), ("18%", .99), True),
    (("?", .80), ("18%", .96), False),
])
def test_numeric_agreement_requires_fresh_valid_matching_read(first, second, accepted):
    crop = np.full((15, 50, 3), 180, dtype=np.uint8)
    reader = Mock(return_value=[second])
    reading, confirmed = verify(reader, crop, first)
    assert confirmed is accepted
    if second is None:
        reader.assert_not_called()
    else:
        assert reader.call_args.kwargs == {"use_cache": False}
        retry_crop = reader.call_args.args[0][0]
        assert retry_crop.shape == (31, 66, 3)
    if accepted and second is not None and second[1] < .97:
        assert reading[1] == min(first[1], second[1])


def test_overview_agreement_accepts_lower_score():
    originals = [np.zeros((21, 52, 3), dtype=np.uint8)] * len(vision.OVERVIEW_FIELDS)
    results = [("1", 1.0)] * len(originals)
    index = list(vision.OVERVIEW_FIELDS).index("stat.ignoreDef")
    results[index] = ("96.91%", .965)
    confirmed = vision._retry_uncertain_overview(Mock(return_value=[("96.91%", .92)]), results, originals)
    values = {}
    vision._parse_overview_field("stat.ignoreDef", *results[index], values, confirmed="stat.ignoreDef" in confirmed)
    assert values["stat.ignoreDef"]["value"] == "96.91"
    assert values["stat.ignoreDef"]["confidence"] == .92


@pytest.mark.parametrize("retry,accepted", [("5sec / 6%", True), ("5sec / 8%", False)])
def test_cooldown_agreement_checks_both_values(retry, accepted):
    originals = [np.zeros((21, 80, 3), dtype=np.uint8)] * len(vision.OVERVIEW_FIELDS)
    results = [("1", 1.0)] * len(originals)
    index = list(vision.OVERVIEW_FIELDS).index("cooldown")
    results[index] = ("5sec / 6%", .93)
    confirmed = vision._retry_uncertain_overview(Mock(return_value=[(retry, .94)]), results, originals)
    assert ("cooldown" in confirmed) is accepted


@pytest.mark.parametrize("retry,accepted", [("Base Value: 3185", True), ("Base Value: 3785", False)])
def test_tooltip_agreement_preserves_numbers(monkeypatch, retry, accepted):
    monkeypatch.setattr(vision, "anchor", lambda *args, **kwargs: (10, 10))
    reader = Mock(side_effect=[
        [("Base Value: 3185", .93), ("% Value: 51%", .99), ("% Value Not Applied: 10", .99)],
        [(retry, .92)],
    ])
    if accepted:
        result = vision.tooltip(np.zeros((200, 300, 3), dtype=np.uint8), reader)
        assert result["values"]["base"] == {"value": "3185", "confidence": .92, "text": retry}
    else:
        with pytest.raises(vision.ReadError):
            vision.tooltip(np.zeros((200, 300, 3), dtype=np.uint8), reader)


def test_uncertain_unaffected_stat_never_becomes_zero(monkeypatch):
    monkeypatch.setattr(vision, "anchor", lambda *args, **kwargs: (10, 10))
    reader = Mock(side_effect=[
        [("Base Value: 3185", .99), ("% Value: 51%", .99), ("% Value Not Applied: 10", .93)],
        [("% Value Not Applied: 70", .99)],
        [("Base Value", .99)],
    ])
    with pytest.raises(vision.ReadError, match="unaffected"):
        vision.tooltip(np.zeros((200, 300, 3), dtype=np.uint8), reader)
    assert reader.call_count == 2


@pytest.mark.parametrize("retry,accepted", [
    ("Required Level Lv 125 (150 - 25)", True),
    ("Required Level Lv 130 (150 - 20)", False),
    ("Required Level Lv 125 (160 - 35)", False),
    ("Required Level Lv 125 (150)", False),
])
def test_required_level_retry_ignores_optional_period_only(retry, accepted):
    from equipment_scan import _scan_stat_rows

    image = np.zeros((40, 330, 3), dtype=np.uint8)
    reader = Mock(return_value=[(retry, .95)])
    result = {}
    args = (image, 0, reader, [(0, 20)], [("Hat", 1), ("Required Level Lv. 125 (150 - 25)", .96)], result)
    if accepted:
        _scan_stat_rows(*args)
        assert result["required_level"] == 150
    else:
        with pytest.raises(vision.ReadError, match="Required level"):
            _scan_stat_rows(*args)
