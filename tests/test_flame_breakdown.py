from collections import defaultdict

from test_equipment_scan import frame, replay

from equipment_scan import hover
from flaming.breakdown import breakdown, legacy


def test_tier_breakdowns_reconstruct_actual_saved_totals():
    for slot in ("hat", "gloves", "weapon"):
        item = hover(frame(slot), replay, slot)
        item["name"] = item["item"]
        result = breakdown(item, slot)
        assert result["options"], (slot, result)
        expected = {s["name"]: s["value"] for s in item["stats"] if s["value"]}
        for lines in result["options"]:
            summed = defaultdict(int)
            for line in lines:
                for stat in line["stats"]:
                    summed[stat] += line["value"]
            assert dict(summed) == expected
            assert len(lines) == 4


def test_unknown_item_has_no_invented_tiers():
    assert breakdown({"name": "Unknown item", "stats": []}, "hat")["options"] == []


def test_transposed_flame_above_current_tiers_is_legacy():
    # Live transposed Sweetwater Pendant: its totals need tier-6 lines, but it rolls tier 5 at most now.
    stats = [("STR", 84, False), ("INT", 30, False), ("All Stats", 5, True)]
    item = {"name": "Sweetwater Pendant", "stats": [{"name": n, "value": v, "percent": p} for n, v, p in stats]}
    result = breakdown(item, "pendant_1")
    assert result["legacy"]
    assert [line["tier"] for line in result["options"][0]] == [6, 6, 5]
    assert legacy(item, "pendant_1") == result["message"]
    ordinary = {"name": "Sweetwater Pendant", "stats": [{"name": "STR", "value": 45, "percent": False}]}
    assert legacy(ordinary, "pendant_1") is None
