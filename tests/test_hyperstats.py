import copy
import itertools
import json
from pathlib import Path

import pytest

from hyperstats import optimizer as hyper
from scouter import profiles

CASE = json.loads((Path(__file__).parent / "fixtures/boss_cuts.json").read_text(encoding="utf-8"))["cases"][0]
SHADOWER = profiles.class_info("Shadower")
TABLE = hyper.stats()
SPREAD = dict(
    luk=10, crit_rate=5, crit_damage=10, ied=10, damage=10, boss_damage=10, attack=10, status_resistance=5
)


def levels(**set_levels):
    return {key: set_levels.get(key, 0) for key in TABLE}


def request(info=SHADOWER, keep=None, combat_crit=100, defense="380", **set_levels):
    return {
        "levels": levels(**set_levels),
        "keep": hyper.default_keep(info) if keep is None else keep,
        "crit_rate": combat_crit,
        "defense": defense,
    }


def run(info=SHADOWER, user=None, **kwargs):
    return hyper.optimize(info, user or CASE["user"], CASE["calculated"], request(info, **kwargs))


def at_level(level):
    user = copy.deepcopy(CASE["user"])
    user["stat"]["level"] = str(level)
    return user


def test_points_follow_the_wiki_totals_and_the_in_game_reset():
    assert [hyper.total_points(lv) for lv in (139, 140, 149, 150, 202, 205, 280, 300)] == [
        0,
        3,
        30,
        34,
        357,
        384,
        1347,
        1699,
    ]
    assert sum(hyper.table()["costs"]) == 550


def test_stats_are_listed_in_the_in_game_window_order():
    assert [s["label"] for s in hyper.table()["stats"]] == [
        "STR",
        "DEX",
        "INT",
        "LUK",
        "HP",
        "MP",
        "DF/TF",
        "Critical Rate",
        "Critical Damage",
        "Ignore Defense",
        "Damage",
        "Boss Damage",
        "Normal Damage",
        "Status Resistance",
        "Attack Power & Magic ATT",
        "EXP Obtained",
        "Arcane Power",
    ]
    assert len(TABLE["df_tf"]["values"]) == 10
    assert all(len(s["values"]) == 15 for k, s in TABLE.items() if k != "df_tf")


def test_pools_reproduce_scouter_efficiencies():
    co = hyper.coefficients(SHADOWER, CASE["calculated"])
    eff = CASE["calculated"]["specEfficiency"]
    base = levels()
    assert hyper.fd_percent(co, base, levels(boss_damage=1), "380") == pytest.approx(eff["dmgeff1"] * 3 * 100)
    assert hyper.fd_percent(co, base, levels(attack=1), "380") == pytest.approx(eff["atkeff1"] * 3 * 100)
    assert hyper.fd_percent(co, base, levels(luk=1), "380") == pytest.approx(
        eff["mainStatAbseff1"] * 30 * 100
    )
    # A +1% IED line is Scouter's own IED efficiency, and the defense term matches Scouter's.
    for defense, key in (("300", "igreff1"), ("380", "igreff1_380")):
        assert co["ied"][defense] == pytest.approx(CASE["calculated"][f"ignoreDefConst_{defense}"], abs=1e-12)
        assert hyper._ied(co["ied"][defense], 0, 1) - 1 == pytest.approx(eff[key])


def test_newer_scouter_results_without_ignore_def_const_still_work():
    calculated = {
        k: v for k, v in CASE["calculated"].items() if k not in ("ignoreDefConst_300", "ignoreDefConst_380")
    }
    result = hyper.optimize(SHADOWER, CASE["user"], calculated, request(**SPREAD))
    assert result["fd_percent"]["380"] == pytest.approx(run(**SPREAD)["fd_percent"]["380"])


def test_search_matches_brute_force_on_a_tight_budget():
    free = ("crit_damage", "ied", "damage", "boss_damage")
    current = dict.fromkeys(free, 5)
    keep = [k for k in TABLE if k not in free]
    result = run(user=at_level(169), keep=keep, **current)  # 120 points; current costs 100
    co = hyper.coefficients(SHADOWER, CASE["calculated"])
    base = levels(**current)
    best = max(
        hyper.fd_percent(co, base, {**base, **dict(zip(free, combo))}, "380")
        for combo in itertools.product(range(16), repeat=4)
        if hyper.spent(dict(zip(free, combo))) <= 120
    )
    assert result["fd_percent"]["380"] == pytest.approx(best) and best > 0
    assert result["suggested"]["cost"] <= 120


def test_kept_stats_never_move_and_points_stay_within_budget():
    keep = ["crit_rate", "status_resistance", "exp"]
    result = run(keep=keep, exp=3, **SPREAD)
    suggested = result["suggested"]["levels"]
    assert [suggested[k] for k in keep] == [5, 5, 3]
    assert result["suggested"]["cost"] <= result["budget"] == 1347
    assert result["fd_percent"]["380"] > 0 and not result["already_optimized"]


def test_running_on_the_suggestion_reports_already_optimized():
    first = run(**SPREAD)
    again = run(**first["suggested"]["levels"])
    assert again["already_optimized"] and again["suggested"]["levels"] == again["current"]["levels"]
    assert again["fd_percent"] == {"300": 0, "380": 0}


def test_crit_floor_picks_the_lowest_level_reaching_100_percent():
    # 120% with level 5 (+5%) is 115% without hyper crit: level 0 is enough.
    assert run(keep=[], combat_crit=120, crit_rate=5)["suggested"]["levels"]["crit_rate"] == 0
    # 95% with level 5 is 90% without; level 8 (+11%) is the first to reach 100%.
    assert run(keep=[], combat_crit=95, crit_rate=5)["suggested"]["levels"]["crit_rate"] == 8


def test_kept_crit_rate_is_never_overridden_by_the_floor():
    for combat_crit in (95, 140):
        result = run(keep=["crit_rate"], combat_crit=combat_crit, crit_rate=10)
        assert result["suggested"]["levels"]["crit_rate"] == 10
    # The in-combat rate isn't needed when Critical Rate is kept.
    assert hyper.clean({"levels": {}, "keep": ["crit_rate"]})["crit_rate"] is None


def test_unreachable_crit_floor_warns_at_max_level():
    result = run(keep=[], combat_crit=60)
    assert result["suggested"]["levels"]["crit_rate"] == 15
    assert "under 100%" in result["warnings"][0]


def test_only_critical_rate_is_kept_by_default_for_every_class():
    for name in ("Shadower", "Bowmaster", "Xenon", "Kanna"):
        assert hyper.default_keep(profiles.class_info(name)) == ["crit_rate"]


def test_unkept_unscored_stats_are_freed():
    result = run(
        int=5,
        hp=3,
        status_resistance=5,
        exp=2,
        **{k: v for k, v in SPREAD.items() if k != "status_resistance"},
    )
    suggested = result["suggested"]["levels"]
    assert [suggested[k] for k in ("int", "hp", "status_resistance", "exp")] == [0, 0, 0, 0]


def test_xenon_scores_str_dex_and_luk_as_percent_not_applied_stats():
    xenon = profiles.class_info("Xenon")
    assert hyper.stat_fields(xenon) == {"str": "mainStatAbs", "dex": "subStatAbs", "luk": "ssubStatAbs"}


def test_demon_avenger_is_blocked():
    avenger = profiles.class_info("Demon Avenger")
    assert hyper.blocked(avenger)
    with pytest.raises(ValueError, match="HP is the main stat"):
        run(info=avenger)


def test_levels_from_another_preset_are_blocked():
    user = copy.deepcopy(CASE["user"])
    user["stat"]["dmg"] = "30"
    result = run(user=user, damage=15)
    assert "Hyper Damage (+45)" in result["blockers"][0] and "suggested" not in result
    assert "preset you scanned" in result["blockers"][-1]


def test_allocations_over_the_level_budget_are_blocked():
    result = run(user=at_level(200), **SPREAD)
    assert "a level 200 character has 339" in result["blockers"][0]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"luk": 16}, "LUK must be a whole number from 0 to 15"),
        ({"df_tf": 11}, "0 to 10"),
        ({"ied": 1.5}, "whole"),
        ({"ied": True}, "whole"),
        ({"speed": 1}, "Unsupported"),
    ],
)
def test_invalid_levels_are_rejected(raw, message):
    with pytest.raises(ValueError, match=message):
        hyper.clean({"levels": raw, "keep": ["crit_rate"]})


def test_unkept_crit_rate_needs_the_in_combat_rate():
    with pytest.raises(ValueError, match="in-combat Critical Rate"):
        hyper.clean({"levels": {}, "keep": []})


def test_apply_swaps_hyper_stats_in_the_scouter_input():
    current = levels(luk=10, ied=10, damage=10, crit_rate=5)
    suggested = levels(luk=4, ied=12, damage=13, crit_rate=0)
    user = hyper.apply(SHADOWER, CASE["user"], current, suggested)
    stat = user["stat"]
    assert stat["mainStatAbs"] == str(20000 - 300 + 120)
    assert stat["dmg"] == str(80 - 30 + 39)
    assert stat["critical"] == str(100 - 5)
    # 95% total with 30% from hyper: the rest is 1 - 0.05 / 0.7; then add 36%.
    assert float(stat["ignoreDef"]) == pytest.approx(100 - 5 / 0.7 * 0.64)
    assert stat["bossDmg"] == CASE["user"]["stat"]["bossDmg"]
    assert CASE["user"]["stat"]["mainStatAbs"] == "20000"
