import json
from decimal import Decimal

import pytest
from test_app import client

from flaming import characters
from flaming.character_score import character_score, scoring
from flaming.score import normalize_score
from scouter import profiles as scouter


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(characters, "PROFILE_DIR", tmp_path / "gear")
    monkeypatch.setattr(scouter, "DIRECTORY", tmp_path / "scouter")
    characters.PROFILE_DIR.mkdir()
    scouter.DIRECTORY.mkdir()
    job = scouter.class_info("Shadower")["key"]
    record = {
        "created": "2026-09-26T00:00:00Z",
        "input": {"stat": {"myClass": job}},
        "damage": {
            "calculatedData": {
                "specEfficiency": {
                    "mainStateff1": 0.0001,
                    "subStateff1": 0.000013,
                    "ssubStateff1": 0.000014,
                    "atkeff1": 0.0003,
                    "allStatEff": 0.0014,
                    "dmgeff1": 0.0012,
                }
            }
        },
    }
    data = {"class_key": job, "history": [record]}
    path = scouter.DIRECTORY / "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.json"
    path.write_text(json.dumps(data))
    profile = {
        "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "name": "Test",
        "class": "Shadower",
        "flame_all_stat_source": "scouter",
        "equipment": {
            "hat": {
                "name": "Highness Assassin Bonnet",
                "status": "scanned",
                "flame_score": "130",
                "stats": [
                    {"name": "LUK", "value": 80, "percent": False},
                    {"name": "All Stats", "value": 5, "percent": True},
                ],
            }
        },
    }
    (characters.PROFILE_DIR / "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.json").write_text(json.dumps(profile))
    return profile, data, path


def test_scouter_efficiencies_set_all_flame_weights(saved):
    profile, data, path = saved
    score, info = scoring(profile)
    assert score["weights"]["All Stats"] == "14.000000"
    assert info["effective_source"] == "scouter"
    assert info["calculated_at"] == data["history"][-1]["created"]
    expected = normalize_score({"class": "Shadower"})
    expected["weights"].update(
        {
            "LUK": "1.000000",
            "DEX": "0.130000",
            "STR": "0.140000",
            "Attack Power": "3.000000",
            "All Stats": "14.000000",
            "Damage": "12.000000",
            "Boss Damage": "12.000000",
        }
    )
    assert info["scouter_weights"] == expected["weights"]
    assert info["stat_order"] == ["LUK", "DEX", "STR", "Attack Power", "All Stats", "Damage", "Boss Damage"]
    assert score == expected
    default = character_score({**profile, "flame_all_stat_source": "default"})
    assert default["weights"]["All Stats"] == "10"
    data["history"][-1]["damage"]["calculatedData"]["specEfficiency"]["allStatEff"] = 0.0015
    path.write_text(json.dumps(data))
    assert character_score(profile)["weights"]["All Stats"] == "15.000000"
    assert score["weights"]["All Stats"] == "14.000000"


@pytest.mark.parametrize("bad", [0, -1, True, None, "NaN", "Infinity", "bad"])
def test_invalid_efficiencies_fall_back_without_breaking_scan(saved, bad):
    profile, data, path = saved
    data["history"][-1]["damage"]["calculatedData"]["specEfficiency"]["mainStateff1"] = bad
    path.write_text(json.dumps(data))
    score, info = scoring(profile)
    assert score["weights"]["All Stats"] == "10"
    assert info["scouter_weight"] is None and info["effective_source"] == "default"


def test_missing_result_and_other_character_class_are_unavailable(saved):
    profile, _, path = saved
    assert scoring({**profile, "class": "Mercedes"})[1]["scouter_weight"] is None
    assert scoring({**profile, "id": "another"})[1]["scouter_weight"] is None
    path.unlink()
    assert character_score(profile)["weights"]["All Stats"] == "10"


@pytest.mark.parametrize(
    "job,expected",
    [
        ("Hero", {"STR": 1, "DEX": 0.13, "Attack Power": 3, "Magic Attack": 0, "LUK": 0}),
        ("Bishop", {"INT": 1, "LUK": 0.13, "Magic Attack": 3, "Attack Power": 0, "STR": 0}),
        ("DualBlade", {"LUK": 1, "DEX": 0.13, "STR": 0.14, "Attack Power": 3}),
        ("Xenon", {"STR": 1, "DEX": 0.13, "LUK": 0.14, "Attack Power": 3}),
        ("DemonAvenger", {"Max HP": 1, "STR": 0.13, "DEX": 0, "Attack Power": 3}),
    ],
)
def test_scouter_stat_mapping_and_correct_attack_type(saved, job, expected):
    profile, data, path = saved
    key = scouter.class_info(job)["key"]
    data["class_key"] = data["history"][-1]["input"]["stat"]["myClass"] = key
    path.write_text(json.dumps(data))
    score, info = scoring({**profile, "class": job})
    assert info["effective_source"] == "scouter"
    for stat, weight in expected.items():
        assert Decimal(score["weights"][stat]) == Decimal(str(weight))


def test_incomplete_result_falls_back_as_a_whole_but_zero_efficiency_is_valid(saved):
    profile, data, path = saved
    eff = data["history"][-1]["damage"]["calculatedData"]["specEfficiency"]
    eff["subStateff1"] = 0
    path.write_text(json.dumps(data))
    assert character_score(profile)["weights"]["DEX"] == "0.000000"
    del eff["atkeff1"]
    path.write_text(json.dumps(data))
    score, info = scoring(profile)
    assert info["scouter_weights"] is None
    assert score == normalize_score({"class": "Shadower"})


def test_primary_score_scale_and_legacy_preference(saved, monkeypatch):
    from flaming import profiles

    profile, _, _ = saved
    original = profiles.role_weights
    monkeypatch.setattr(profiles, "role_weights", lambda *args, **kwargs: {**original(*args, **kwargs), "primary": "2"})
    weights = character_score(profile)["weights"]
    assert Decimal(weights["LUK"]) == 2
    assert Decimal(weights["DEX"]) == Decimal(".26")
    assert Decimal(weights["Attack Power"]) == 6
    assert Decimal(weights["All Stats"]) == 28
    assert Decimal(weights["Boss Damage"]) == 24
    # A new explicit choice takes precedence over the old All Stat preference.
    assert character_score({**profile, "flame_weight_source": "default"})["weights"]["Attack Power"] == "4"




def test_standalone_toggle_revalues_grid_and_costs(client, monkeypatch):
    from test_app import ID, post

    import enhancement_analysis
    from enhancement_analysis import snapshot
    from scouter import profiles as scouter

    profile = characters.load(ID)
    profile["equipment"] = {"hat": {"name": "Highness Assassin Bonnet", "status": "scanned", "cubeable": False,
        "stats": [{"name": "LUK", "value": 80, "percent": False}, {"name": "All Stats", "value": 5, "percent": True}]}}
    characters.write(profile)
    assert post(client, f"/api/characters/{ID}/scoring", {"source": "scouter"}).status_code == 400
    data = scouter.load(ID)
    data["history"] = [{"created": "2026-09-26T00:00:00Z", "input": {"stat": {"myClass": data["class_key"]}},
        "damage": {"calculatedData": {"specEfficiency": {"mainStateff1": 1, "subStateff1": .13,
        "ssubStateff1": .14, "atkeff1": 3, "allStatEff": 14, "dmgeff1": 12}}}}]
    scouter.write(ID, data)
    response = post(client, f"/api/characters/{ID}/scoring", {"source": "scouter"})
    assert response.status_code == 200
    assert response.json["equipment"]["hat"]["flame_score"] == 150
    assert characters.load(ID)["flame_weight_source"] == "scouter"
    seen=[]
    def estimate(catalog, baseline, score, **kwargs):
        seen.append((baseline, score["weights"]["All Stats"]))
        return {"probability": .5, "expected_rolls": 2, "expected_mesos": 6000000}
    monkeypatch.setattr(enhancement_analysis, "improvement", estimate)
    assert snapshot(characters.load(ID))["items"]["hat"]["flame_score"] == 150
    assert seen and all(value == (Decimal(150), "14.000000") for value in seen)
    assert post(client, f"/api/characters/{ID}/scoring", {"source": "default"}).json["equipment"]["hat"]["flame_score"] == 130
    assert post(client, f"/api/characters/{ID}/scoring", {"source": "other"}).status_code == 400

