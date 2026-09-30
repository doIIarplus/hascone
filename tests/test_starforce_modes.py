import pytest
from test_app import ID, client, get, post  # noqa: F401

from flaming import characters
from starforce import cost, stats
from starforce.suggestions import suggestions

SAFE = {"mode_15_17": "safeguard", "mode_18_21": 4}


def test_item_modes_validation():
    assert cost.item_modes(None) is None
    assert cost.item_modes(SAFE) == SAFE
    for bad in ({"mode_15_17": 1}, {"mode_15_17": 5, "mode_18_21": 1}, {"mode_15_17": 1, "mode_18_21": "safeguard"}, "x"):
        with pytest.raises(ValueError):
            cost.item_modes(bad)


def test_fixed_modes_are_used_at_every_star_and_avoid_booms():
    fixed = cost.optimize(150, 15, 22, modes=SAFE)
    assert [s["mode"] for s in fixed["starforce_plan"] if 15 <= s["star"] <= 17] == ["safeguard"] * 3
    assert [s["mode"] for s in fixed["starforce_plan"] if 18 <= s["star"] <= 21] == [4] * 4
    assert fixed["expected_booms"] == 0
    assert fixed["expected_mesos"] >= cost.optimize(150, 15, 22)["expected_mesos"]


def test_upgrade_order_uses_one_row_with_the_items_modes():
    item = {"name": "Royal Dunwitch Hat", "required_level": 150, "starforce": {"status": "scanned", "stars": 16, "max_stars": 30}}
    gear = {"class": "Shadower", "equipment": {"hat": item}}
    weights = {"LUK": 1, "DEX": 1, "STR": 1, "INT": 1, "Attack Power": 1, "Magic Attack": 1, "Max HP": 1}
    assert {r["strategy"] for r in suggestions("hat", item, weights, gear)} == {"mesos", "booms"}
    rows = suggestions("hat", {**item, "starforce_modes": SAFE}, weights, gear)
    assert [r["strategy"] for r in rows] == ["custom"]
    assert rows[0]["expected_booms"] == 0
    assert rows[0]["starforce_plan"][-1]["mode"] == "safeguard"


def test_kanna_talisman_uses_weapon_star_gains():
    # Live Thousand Soul Talisman: tooltip enhancement bonus at 21 stars, then the 22nd star.
    meta = stats.metadata("secondary", {"name": "Thousand Soul Talisman", "required_level": 200})
    assert stats.gains(meta, 0, 21) == {"INT": 130, "LUK": 130, "Max HP": 255, "Magic Attack": 153}
    item = {"name": "Thousand Soul Talisman", "required_level": 200, "starforce": {"status": "scanned", "stars": 21, "max_stars": 26}}
    gear = {"class": "Kanna", "equipment": {"secondary": item}}
    weights = {"INT": 1, "LUK": 1, "Magic Attack": 1}
    assert suggestions("secondary", item, weights, gear)[0]["stat_gains"] == {"INT": 15, "LUK": 15, "Magic Attack": 17}


def test_modes_route_saves_and_clears(client):
    p = characters.load(ID)
    p["equipment"]["hat"] = {"name": "Hat", "starforce": {"status": "scanned", "stars": 17, "max_stars": 30}}
    characters.write(p)
    path = f"/api/characters/{ID}/equipment/hat/starforce-modes"
    assert post(client, path, {"modes": SAFE}).status_code == 200
    assert characters.load(ID)["equipment"]["hat"]["starforce_modes"] == SAFE
    assert post(client, path, {"modes": {"mode_15_17": 9, "mode_18_21": 1}}).status_code == 400
    assert post(client, path, {"modes": None}).status_code == 200
    assert "starforce_modes" not in characters.load(ID)["equipment"]["hat"]
    assert post(client, f"/api/characters/{ID}/equipment/top/starforce-modes", {"modes": SAFE}).status_code == 400
