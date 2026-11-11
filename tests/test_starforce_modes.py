import pytest
from test_app import ID, client, get, post  # noqa: F401

from flaming import characters
from starforce import cost, stats
from starforce.suggestions import suggestions

SAFE = {"mode_15_17": "safeguard", "mode_18_21": 4}
FULL = {"15": "safeguard", "16": "safeguard", "17": "safeguard", "18": 4, "19": 4, "20": 4, "21": 4}


def test_item_modes_validation():
    assert cost.item_modes(None) is None
    # Older saves chose one mode per range; they expand to every star.
    assert cost.item_modes(SAFE) == FULL
    mixed = {**FULL, "17": 1, "18": 1, "19": 1}
    assert cost.item_modes(mixed) == mixed
    assert cost.mode_summary(mixed) == "15–16★ Safeguard, 17–19★ Mode 1, 20–21★ Mode 4"
    for bad in ({"mode_15_17": 1}, {"mode_15_17": 5, "mode_18_21": 1}, {"mode_15_17": 1, "mode_18_21": "safeguard"}, "x",
                {**FULL, "15": 4}, {**FULL, "18": "safeguard"}, {k: v for k, v in FULL.items() if k != "21"}):
        with pytest.raises(ValueError):
            cost.item_modes(bad)


def test_each_star_uses_its_own_mode():
    modes = cost.item_modes({**FULL, "18": 1, "19": 1})
    plan = cost.optimize(200, 15, 22, modes=modes)["starforce_plan"]
    assert [(s["star"], s["mode"]) for s in plan if s["star"] >= 15] == [
        (15, "safeguard"), (16, "safeguard"), (17, "safeguard"), (18, 1), (19, 1), (20, 4), (21, 4)
    ]


def test_mode_table_lists_each_attempt_with_its_odds_and_cost():
    # Level 200, no events: matches the in-game panel and other GMS planners.
    table = cost.mode_table(200)
    assert [row["star"] for row in table] == [15, 16, 17, 18, 19, 20, 21]
    first, last = table[0]["choices"], table[-1]["choices"]
    assert [c["mode"] for c in first] == [1, 2, 3, "safeguard"] and [c["mode"] for c in last] == [1, 2, 3, 4]
    assert (first[0]["success"], first[0]["boom"], first[0]["cost"]) == (0.315, 0.02055, 71_316_500)
    assert (last[0]["boom"], last[0]["cost"], last[3]["boom"]) == (0.126375, 269_601_800, 0)
    assert first[3]["boom"] == 0 and first[3]["cost"] > first[0]["cost"]
    # Items below 22★ only list the attempts they can make.
    assert [row["star"] for row in cost.mode_table(130, cap=20)] == [15, 16, 17, 18, 19]

def test_fixed_modes_are_used_at_every_star_and_avoid_booms():
    fixed = cost.optimize(150, 15, 22, modes=cost.item_modes(SAFE))
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


def test_zero_swords_use_weapon_star_force_from_their_own_base_attack():
    # Live Lazuli/Lapis Type 9 tooltips at 16 stars: STR/DEX +55, Max HP +255, ATT +122/+125.
    for name, attack in (("Lazuli Type 9", 122), ("Lapis Type 9", 125)):
        meta = stats.metadata("weapon", {"name": name, "required_level": 200})
        assert stats.gains(meta, 0, 16) == {"STR": 55, "DEX": 55, "Max HP": 255, "Attack Power": attack}
    for name, level in (("Genesis Lazuli", 200), ("Destiny Lazuli", 250)):
        with pytest.raises(ValueError, match="Fixed Genesis"):
            stats.metadata("weapon", {"name": name, "required_level": level})


def test_modes_route_saves_and_clears(client):
    p = characters.load(ID)
    p["equipment"]["hat"] = {"name": "Hat", "starforce": {"status": "scanned", "stars": 17, "max_stars": 30}}
    characters.write(p)
    path = f"/api/characters/{ID}/equipment/hat/starforce-modes"
    assert post(client, path, {"modes": SAFE}).status_code == 200
    assert characters.load(ID)["equipment"]["hat"]["starforce_modes"] == FULL
    assert post(client, path, {"modes": {"mode_15_17": 9, "mode_18_21": 1}}).status_code == 400
    assert post(client, path, {"modes": None}).status_code == 200
    assert "starforce_modes" not in characters.load(ID)["equipment"]["hat"]
    assert post(client, f"/api/characters/{ID}/equipment/top/starforce-modes", {"modes": SAFE}).status_code == 400


HAT = {"name": "Royal Dunwitch Hat", "required_level": 150, "starforce": {"status": "scanned", "stars": 19, "max_stars": 30}}
HAT_GEAR = {"class": "Shadower", "equipment": {"hat": HAT}}
ALL = {"LUK": 1, "DEX": 1, "STR": 1, "INT": 1, "Attack Power": 1, "Magic Attack": 1, "Max HP": 1}


def test_target_validation():
    assert cost.item_target(None) is None
    assert cost.item_target(22) == 22
    for bad in (0, 31, 21.0, True, "22"):
        with pytest.raises(ValueError):
            cost.item_target(bad)


def test_no_target_or_reached_target_ranks_only_the_next_star():
    plain = suggestions("hat", HAT, ALL, HAT_GEAR)
    assert [(r["current_stars"], r["target_stars"], r["step"], r["steps"]) for r in plain] == [(19, 20, 1, 1)] * 2
    assert all(r["requires"] is None and r["fd_per_billion"] == r["raw_fd_per_billion"] for r in plain)
    for reached in (19, 12):
        assert suggestions("hat", {**HAT, "starforce_target": reached}, ALL, HAT_GEAR) == plain


def test_target_ranks_every_star_and_steps_add_up_to_the_whole_climb():
    rows = suggestions("hat", {**HAT, "starforce_target": 22}, ALL, HAT_GEAR)
    for strategy in ("mesos", "booms"):
        chain = [r for r in rows if r["strategy"] == strategy]
        assert [(r["current_stars"], r["target_stars"], r["step"]) for r in chain] == [(19, 20, 1), (20, 21, 2), (21, 22, 3)]
        assert [r["requires"] for r in chain] == [None, "19→20", "20→21"]
        assert all(r["steps"] == 3 and r["chain_target"] == 22 for r in chain)
        whole = cost.optimize(150, 19, 22, objective=strategy)
        for key in ("expected_mesos", "expected_rolls", "expected_booms"):
            assert sum(r[key] for r in chain) == pytest.approx(whole[key])
        # A later star never outranks the one it depends on.
        scores = [r["fd_per_billion"] for r in chain]
        assert scores == sorted(scores, reverse=True)
        assert all(r["fd_per_billion"] <= r["raw_fd_per_billion"] for r in chain)
        assert chain[0]["fd_per_billion"] == chain[0]["raw_fd_per_billion"]


def test_capped_step_keeps_its_predecessors_score_and_cost_rank():
    # Valuing only attack, 20→21 is cheaper per FD than 19→20, yet it must be done after it.
    rows = suggestions("hat", {**HAT, "starforce_target": 21}, {"Attack Power": 1}, HAT_GEAR)
    for strategy in ("mesos", "booms"):
        first, second = [r for r in rows if r["strategy"] == strategy]
        assert second["raw_fd_per_billion"] > first["fd_per_billion"]
        assert second["fd_per_billion"] == first["fd_per_billion"]
        assert second["rank_mesos"] == first["rank_mesos"] == first["expected_mesos"]
        assert any(n.startswith("Ranked no higher") for n in second["notes"])
        assert not any(n.startswith("Ranked no higher") for n in first["notes"])


def test_target_above_the_items_limit_is_clamped():
    item = {"name": "Royal Dunwitch Hat", "required_level": 130,
            "starforce": {"status": "scanned", "stars": 18, "max_stars": 20}, "starforce_target": 25}
    rows = suggestions("hat", item, ALL, {"class": "Shadower", "equipment": {"hat": item}})
    assert sorted({r["target_stars"] for r in rows}) == [19, 20]
    assert all(r["clamped_from"] == 25 and r["chain_target"] == 20 for r in rows)


def test_chain_stops_at_a_star_with_no_modeled_gain():
    item = {**HAT, "starforce": {**HAT["starforce"], "stars": 21}, "starforce_target": 24}
    rows = suggestions("hat", item, {"LUK": 1}, HAT_GEAR)
    assert {(r["current_stars"], r["target_stars"]) for r in rows} == {(21, 22)}
    assert all(r["steps"] == 1 and any(n.startswith("Stops at 22★") for n in r["notes"]) for r in rows)
    with pytest.raises(ValueError, match="next star"):
        suggestions("hat", {**item, "starforce": {**HAT["starforce"], "stars": 22}}, {"LUK": 1}, HAT_GEAR)


def test_target_route_saves_and_clears(client):
    p = characters.load(ID)
    p["equipment"]["hat"] = {"name": "Hat", "starforce": {"status": "scanned", "stars": 17, "max_stars": 30}}
    characters.write(p)
    path = f"/api/characters/{ID}/equipment/hat/starforce-target"
    assert post(client, path, {"target": 22}).status_code == 200
    assert characters.load(ID)["equipment"]["hat"]["starforce_target"] == 22
    for bad in (0, 31, "22", 21.5):
        assert post(client, path, {"target": bad}).status_code == 400
    assert characters.load(ID)["equipment"]["hat"]["starforce_target"] == 22
    assert post(client, path, {"target": None}).status_code == 200
    assert "starforce_target" not in characters.load(ID)["equipment"]["hat"]
    assert post(client, f"/api/characters/{ID}/equipment/top/starforce-target", {"target": 22}).status_code == 400


def test_target_route_lowers_a_target_above_the_items_limit(client):
    path = f"/api/characters/{ID}/equipment/hat/starforce-target"
    p = characters.load(ID)
    # Scanned limit: 20 stars.
    p["equipment"]["hat"] = {"name": "Hat", "starforce": {"status": "scanned", "stars": 17, "max_stars": 20}}
    characters.write(p)
    assert post(client, path, {"target": 25}).status_code == 200
    assert characters.load(ID)["equipment"]["hat"]["starforce_target"] == 20
    # Level limit: a level 130 item stops at 20 stars even when the scan reads 30.
    p = characters.load(ID)
    p["equipment"]["hat"] = {"name": "Royal Dunwitch Hat", "required_level": 130,
                             "starforce": {"status": "scanned", "stars": 17, "max_stars": 30}}
    characters.write(p)
    assert post(client, path, {"target": 28}).status_code == 200
    assert characters.load(ID)["equipment"]["hat"]["starforce_target"] == 20
    assert post(client, path, {"target": 19}).status_code == 200
    assert characters.load(ID)["equipment"]["hat"]["starforce_target"] == 19
