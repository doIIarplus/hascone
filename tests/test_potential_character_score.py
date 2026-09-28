import json

import pytest
from test_character_score import saved

from cubing.character_score import scoring
from cubing.scoring import current_score
from scouter import profiles as scouter


def prepare(saved):
    profile, data, path = saved
    profile["potential_weight_source"] = "scouter"
    data["history"][-1]["damage"]["calculatedData"]["specEfficiency"].update(
        mainStatPereff1=.001, subStatPereff1=.0002, ssubStatPereff1=.0001,
        allStatEff=.0013, atkPereff1=.006, dmgeff1=.0015)
    path.write_text(json.dumps(data))
    return profile, data, path


def test_percentage_weights_and_cost_use_same_weights(saved):
    profile, data, path = prepare(saved)
    score, attack, info = scoring(profile)
    assert info["effective_source"] == "scouter"
    assert score["stat_weights"] == pytest.approx({"LUK":1,"DEX":.2,"STR":.1})
    assert score["all_stat_weight"] == pytest.approx(1.3)
    assert attack["boss_per_attack"] == pytest.approx(4)
    pot = {"status":"scanned","rank":"Legendary","lines":["All Stats: +10%","LUK: +13%","DEX: +10%"]}
    result = current_score("hat", "Shadower", pot, score, attack, 200)
    assert result["value"] == pytest.approx(28)
    assert result["current_cost"]["spec"]["score"] == score
    pot["lines"] = ["ATT: +13%", "Boss Damage: +40%", "ATT: +10%"]
    result = current_score("weapon", "Shadower", pot, score, attack, 200)
    assert result["value"] == pytest.approx(33)
    assert result["current_cost"]["spec"]["attack_score"] == attack


@pytest.mark.parametrize("job", ["Hero","Bishop","DualBlade","Xenon","DemonAvenger"])
def test_class_mapping(saved, job):
    profile, data, path = prepare(saved)
    key = scouter.class_info(job)["key"]
    data["class_key"] = data["history"][-1]["input"]["stat"]["myClass"] = key
    path.write_text(json.dumps(data))
    assert scoring({**profile,"class":job})[2]["effective_source"] == "scouter"


@pytest.mark.parametrize("bad", [0, -1, True, None, "NaN", "Infinity"])
def test_invalid_result_falls_back(saved, bad):
    profile, data, path = prepare(saved)
    data["history"][-1]["damage"]["calculatedData"]["specEfficiency"]["mainStatPereff1"] = bad
    path.write_text(json.dumps(data))
    score, attack, info = scoring(profile)
    assert info["effective_source"] == "default"
    assert score["secondary_weight"] == .125
    assert info["scouter_weights"] is None


def test_opt_in_and_latest_result(saved):
    profile, data, path = prepare(saved)
    assert scoring({**profile,"potential_weight_source":"default"})[0]["secondary_weight"] == .125
    data["history"][-1]["damage"]["calculatedData"]["specEfficiency"]["allStatEff"] = .0018
    path.write_text(json.dumps(data))
    assert scoring(profile)[0]["all_stat_weight"] == pytest.approx(1.8)
    path.unlink()
    assert scoring(profile)[2]["effective_source"] == "default"
