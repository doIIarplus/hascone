import copy
import json
import threading

import numpy as np
import pytest

from flaming import characters
from flaming.probability import _distribution
from scouter import profiles, service
from scouter import suggestions as s


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(characters, "PROFILE_DIR", tmp_path / "equipment")
    characters.PROFILE_DIR.mkdir()
    gear = {"name": "Example", "class": "Shadower", "equipment": {"eye": {"name": "Magic Eyepatch"}}}
    (characters.PROFILE_DIR / "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.json").write_text(json.dumps(gear))
    monkeypatch.setattr(profiles, "DIRECTORY", tmp_path / "scouter")
    data = profiles.load("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    eff = dict.fromkeys(
        [
            "mainStateff1",
            "subStateff1",
            "ssubStateff1",
            "mainStatPereff1",
            "subStatPereff1",
            "ssubStatPereff1",
            "allStatEff",
            "dmgeff1",
            "atkeff1",
            "atkPereff1",
            "cridmgeff1",
            "igreff1_380",
        ],
        0.001,
    )
    data["history"] = [
        {
            "id": "baseline",
            "created": profiles.now(),
            "fingerprint": profiles.fingerprint(profiles.effective(data)),
            "damage": {"calculatedData": {"specEfficiency": eff}},
        }
    ]
    profiles.write("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", data)
    return data, gear


def test_efficiencies_are_percent_fd_and_use_both_secondary_stats(saved):
    data, _ = saved
    flat, pot, ied, attack = s.coefficients(data["history"][0], data["class_info"])
    assert attack == "ATT"
    assert flat["LUK"] == flat["DEX"] == flat["STR"] == 0.1
    assert "INT" not in flat and "MATT %" not in pot
    assert pot["All Stats %"] == 0.1 and ied == 0.1
    data["history"][0]["damage"]["calculatedData"]["specEfficiency"]["atkeff1"] = float("nan")
    with pytest.raises(ValueError, match="unavailable"):
        s.coefficients(data["history"][0], data["class_info"])


def test_expectation_is_conditional_gain_divided_by_geometric_cost():
    result = s.summary(0.1, 0.02, 3_000_000)
    assert result["expected_fd"] == pytest.approx(0.2)
    assert result["expected_mesos"] == 30_000_000
    assert result["fd_per_billion"] == pytest.approx(6.6666666667)
    assert result["cost_90"] == 22 * 3_000_000
    with pytest.raises(ValueError):
        s.summary(0, 0, 3_000_000)


def test_weapon_tier_filter_keeps_unconditional_probability():
    values = ((1, 2), (10, 20), (100, 200))
    _, all_tail = _distribution(values, (0.75, 0.25), ((2, 1.0),))
    scores, tail = _distribution(values, (0.75, 0.25), ((2, 1.0),), (0, 1))
    assert all_tail[0] == pytest.approx(1)
    assert tail[0] == pytest.approx(2 / 3 * 0.25)
    mass = np.subtract(tail, np.r_[tail[1:], 0])
    assert np.dot(scores, mass) == pytest.approx((12 * 0.75 + 22 * 0.25 + 102 * 0.75 + 202 * 0.25) / 3 * 0.25)


@pytest.fixture
def cube_table(monkeypatch):
    def install(lines, current, slot="eye"):
        raw = dict(zip(["first_line", "second_line", "third_line"], lines, strict=True))
        kind = "ring" if slot == "eye" else slot
        monkeypatch.setattr(
            s.cubes, "database", lambda: {"rates": {kind: {c: {"legendary": raw} for c in ("black", "red")}}}
        )
        monkeypatch.setattr(s, "item_metadata", lambda *args: {"level": 120})
        return {"name": "Test", "potential": {"status": "scanned", "rank": "Legendary", "lines": current}}

    return install


def test_cube_gain_mass_and_costs(cube_table):
    item = cube_table(
        [
            [("LUK %", 10, 50), ("LUK %", 20, 50)],
            [("Junk", 0, 100)],
            [("Junk", 0, 100)],
        ],
        ["LUK +10%", "DEF +9%", "DEF +9%"],
    )
    rows = s.cube_suggestions("eye", item, "Shadower", {"LUK %": 0.01}, 0.01, lambda: None)
    assert [r["method"] for r in rows] == ["Bright", "Glowing"]
    assert all(r["probability"] == 0.5 for r in rows)
    assert all(r["expected_fd"] == pytest.approx(0.1) for r in rows)
    assert [r["expected_mesos"] for r in rows] == [44_000_000, 24_000_000]


def test_ied_replacement_uses_complements_not_percentage_subtraction(cube_table):
    item = cube_table(
        [
            [("Ignore Enemy Defense %", 40, 100)],
            [("Junk", 0, 100)],
            [("Junk", 0, 100)],
        ],
        ["Ignore Enemy Defense +30%", "DEF +9%", "DEF +9%"],
        "weapon",
    )
    row = s.cube_suggestions("weapon", item, "Shadower", {}, 0.01, lambda: None)[0]
    assert row["expected_fd"] == pytest.approx(1 - 0.6 / 0.7)
    assert row["expected_fd"] != pytest.approx(0.1)


def test_preserves_utility_even_when_losing_it_has_more_fd(cube_table):
    item = cube_table(
        [
            [("LUK %", 20, 100)],
            [("Item Drop Rate %", 20, 50), ("LUK %", 20, 50)],
            [("Junk", 0, 100)],
        ],
        ["Item Drop Rate +20%", "LUK +10%", "DEF +9%"],
    )
    row = s.cube_suggestions("eye", item, "Shadower", {"LUK %": 0.01}, 0.01, lambda: None)[0]
    assert row["probability"] == 0.5
    assert row["expected_fd"] == pytest.approx(0.1)
    assert row["protected"] == ["Item Drop Rate %: 20"]


def test_current_baseline_required_and_unavailable_items_skipped(saved, monkeypatch):
    data, gear = saved
    def unavailable(*args, **kwargs):
        raise ValueError("No scanned, flameable item.")

    monkeypatch.setattr(s, "flame_suggestion", unavailable)
    monkeypatch.setattr(s, "cube_suggestions", unavailable)
    result = s.build(data, gear)
    assert not result["rows"]
    assert len(result["skipped"]) == 2
    data["inputs"]["stat.level"] = "280"
    with pytest.raises(ValueError, match="current inputs"):
        s.build(data, gear)


def test_ranking_prefers_fd_per_meso_over_chance(saved, monkeypatch):
    data, gear = saved
    monkeypatch.setattr(
        s, "flame_suggestion", lambda *args: {"method": "Black Flame", **s.summary(0.5, 0.01, 3_000_000)}
    )
    monkeypatch.setattr(
        s, "cube_suggestions", lambda *args: [{"method": "Bright", **s.summary(0.1, 1, 22_000_000)}]
    )
    result = s.build(data, gear)
    assert [r["method"] for r in result["rows"]] == ["Bright", "Black Flame"]
    assert (
        result["gear_fingerprint"]
        == profiles.snapshot("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")["gear_fingerprint"]
    )
    gear["equipment"]["eye"]["name"] = "Different Eye"
    assert s.signature(gear) != result["gear_fingerprint"]


def test_cancel_does_not_write_suggestions(saved, monkeypatch):
    data, gear = saved
    cancelled = threading.Event()
    monkeypatch.setattr(service, "_job", {"active": True})

    def build(*args):
        cancelled.set()
        return {"rows": []}

    monkeypatch.setattr(s, "build", build)
    service._run_suggestions("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", data, gear, cancelled)
    assert service.state()["status"] == "stopped"
    assert not service.state()["active"]
    assert "suggestions" not in profiles.load("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")


def test_comparison_save_preserves_concurrent_inputs(saved, monkeypatch):
    data, gear = saved
    monkeypatch.setattr(service, "_job", {"active": True})

    def build(*args):
        profiles.save_inputs(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", {"revision": 0, "changes": {"stat.level": "280"}}
        )
        return {"rows": [], "fingerprint": data["history"][0]["fingerprint"]}

    monkeypatch.setattr(s, "build", build)
    service._run_suggestions("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", data, gear, threading.Event())
    updated = profiles.snapshot("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert updated["values"]["stat"]["level"] == "280"
    assert updated["suggestions"]["fingerprint"] != updated["fingerprint"]


def test_hat_mixed_rolls_group_costs_and_reject_losing_cooldown_roll(cube_table):
    item = cube_table(
        [
            [("Skill Cooldown Reduction", 2, 100)],
            [("Skill Cooldown Reduction", 2, 100)],
            [
                ("LUK %", 10, 40),
                ("LUK %", 13, 10),
                ("All Stats %", 10, 10),
                ("Skill Cooldown Reduction", 1, 20),
                ("Skill Cooldown Reduction", 2, 20),
            ],
        ],
        ["Skill Cooldowns -2 sec", "Skill Cooldowns -2 sec", "All Stats +7%"],
        "hat",
    )

    class Hat:
        def gain(self, seconds, stat_fd):
            return stat_fd + {4: 0, 5: 0.05, 6: 0.15}[seconds]

    rows = s.cube_suggestions(
        "hat", item, "Shadower", {"LUK %": 0.01, "All Stats %": 0.0125}, 0, lambda: None, lambda _: Hat()
    )
    assert {(r["method"], r["cooldown_seconds"]) for r in rows} == {
        ("Bright", 4),
        ("Bright", 6),
        ("Glowing", 4),
        ("Glowing", 6),
    }
    mixed = next(r for r in rows if r["method"] == "Bright" and r["cooldown_seconds"] == 4)
    assert mixed["probability"] == pytest.approx(0.6)
    assert mixed["expected_mesos"] == pytest.approx(22_000_000 / 0.6)
    assert mixed["expected_fd"] == pytest.approx((0.4 * 0.0125 + 0.1 * 0.0425 + 0.1 * 0.0375) / 0.6)
    assert mixed["examples"] == ["Cooldown: -2s", "Cooldown: -2s", "LUK: +10%"]
    assert not mixed["protected"]
    six = next(r for r in rows if r["method"] == "Bright" and r["cooldown_seconds"] == 6)
    assert six["expected_fd"] == pytest.approx(0.0625)
    assert six["expected_mesos"] == pytest.approx(110_000_000)


def test_hat_api_failure_keeps_other_items_ranked(saved, monkeypatch):
    data, gear = saved
    gear["equipment"]["hat"] = {
        "name": "Test Hat",
        "potential": {"status": "scanned", "rank": "Legendary", "lines": ["LUK +12%", "LUK +9%", "LUK +9%"]},
    }
    monkeypatch.setattr(s, "item_metadata", lambda *args: {"level": 150})
    monkeypatch.setattr(
        s, "flame_suggestion", lambda *args: {"method": "Black Flame", **s.summary(0.5, 0.01, 3_000_000)}
    )

    def fail(*args):
        raise ValueError("MapleScouter returned HTTP 503. Please try again later.")

    monkeypatch.setattr(s.cooldown, "HatModel", fail)
    result = s.build(data, gear)
    assert result["rows"]
    assert any(r["slot"] == "hat" and r["kind"] == "cube" and "503" in r["reason"] for r in result["skipped"])


def test_starforce_profile_options_preserve_input_revision(saved, monkeypatch):
    data, gear = saved
    result = profiles.save_starforce_options("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", {"discount": True})
    assert result["starforce_options"] == {
        "mode_15_17": 1,
        "mode_18_21": 1,
        "discount": True,
        "boom_reduction": False,
    }
    loaded = profiles.load("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert loaded["inputs"] == data["inputs"]
    assert loaded["history"] == data["history"]
    assert loaded["revision"] == data["revision"]
    gear["equipment"]["eye"].update(
        starforce={"status": "scanned", "stars": 23, "max_stars": 30},
    )
    def unavailable(*args, **kwargs):
        raise ValueError("No scanned, flameable item.")

    monkeypatch.setattr(s, "flame_suggestion", unavailable)
    monkeypatch.setattr(s, "cube_suggestions", unavailable)
    built = s.build(loaded, gear)
    assert built["model_version"] == 5
    assert built["starforce_options"]["discount"] is True
    assert {r["kind"] for r in built["rows"]} == {"starforce"}
    assert {r["target_stars"] for r in built["rows"]} == {24}
    assert {r["strategy"] for r in built["rows"]} == {"mesos", "booms"}
    assert len(built["rows"]) == 2
    assert built["rows"] == sorted(
        built["rows"], key=lambda r: (-r["fd_per_billion"], r["expected_mesos"], r["slot"], r["method"])
    )


def test_flame_examples_are_real_qualifying_rolls_and_do_not_change_mean_cost():
    weights = {"LUK": 0.002, "DEX": 0.00025, "STR": 0.00025, "All Stats": 0.04, "Attack Power": 0.006}
    item = {
        "name": "Magic Eyepatch",
        "status": "scanned",
        "stats": [
            {"name": "LUK", "value": 100, "percent": False},
            {"name": "All Stats", "value": 6, "percent": True},
        ],
    }
    row = s.flame_suggestion("eye", item, weights, "ATT")
    assert row["flame_examples"]
    assert row["expected_mesos"] == pytest.approx(3_000_000 / row["probability"])
    baseline = 0.002 * 100 + 0.04 * 6
    for sample in row["flame_examples"]:
        lines = sample["lines"]
        assert len(lines) == 4
        assert len({tuple(line["stats"]) for line in lines}) == 4
        assert all(line["tier"] in {"4", "5", "6", "7"} for line in lines)
        actual = (
            sum(sum(weights.get(k, 0) for k in line["stats"]) * line["value"] for line in lines) - baseline
        )
        assert actual > 0
        assert sample["fd_gain"] == pytest.approx(actual, abs=4e-6)
    assert "not the cost of a specific example" in row["notes"][0]
    assert any("average gain across all qualifying" in note for note in row["notes"])


def test_legacy_hover_flame_used_by_suggestions_and_fingerprint(saved):
    identifier = "a" * 32
    data, gear = saved
    gear["equipment"] = {"face": {
        "name": "Twilight Mark", "hover_scanned": True, "flameable": True,
        "stats": [{"name": "LUK", "value": 80, "percent": False},
                  {"name": "All Stats", "value": 6, "percent": True}],
    }}
    path = characters.PROFILE_DIR / (identifier + ".json")
    path.write_text(json.dumps(gear), encoding="utf-8")
    loaded = s.equipment(identifier)
    assert loaded["equipment"]["face"]["status"] == "scanned"
    assert profiles.snapshot(identifier)["gear_fingerprint"] == s.signature(loaded)
    result = s.build(data, loaded)
    assert any(r["slot"] == "face" and r["kind"] == "flame" for r in result["rows"])
    assert not any(r["slot"] == "face" and r["kind"] == "flame" for r in result["skipped"])
    assert "status" not in json.loads(path.read_text(encoding="utf-8"))["equipment"]["face"]


def test_potential_upgrade_weights_follow_the_scouter_toggle(saved,monkeypatch):
    from cubing import profiles as cube_profiles
    data,gear=saved
    gear['equipment']={'heart':{'name':'Total Control'}}
    seen=[]
    monkeypatch.setattr(s,'cube_suggestions',lambda slot,item,job,weights,*args:seen.append(dict(weights)) or [])
    gear['potential_weight_source']='scouter'
    scouter_result=s.build(data,gear)
    assert scouter_result['potential_weights']=='scouter'
    assert seen[0]['All Stats %']==pytest.approx(data['history'][0]['damage']['calculatedData']['specEfficiency']['allStatEff']*100)
    gear['potential_weight_source']='default'
    manual_result=s.build(data,gear)
    assert manual_result['potential_weights']=='manual'
    info=data['class_info']
    main=seen[0][info['main']+' %']
    score=cube_profiles.score(gear['class'])
    attack='MATT' if info['main']=='INT' else 'ATT'
    assert seen[1][info['main']+' %']==pytest.approx(main)
    assert seen[1]['All Stats %']==pytest.approx(main*score['all_stat_weight'])
    assert seen[1]['Boss Damage']==pytest.approx(seen[0][attack+' %']/cube_profiles.attack_score(gear['class'])['boss_per_attack'])
    assert seen[1]['Critical Damage %']==seen[0]['Critical Damage %']
    assert manual_result['gear_fingerprint']!=scouter_result['gear_fingerprint']