from collections import defaultdict

from test_equipment_scan import frame, replay

from equipment_scan import hover
from flaming.breakdown import breakdown


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
