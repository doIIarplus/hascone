import copy
import json
import threading
from pathlib import Path

import pytest

from scouter import client, service, simulator

CASE = json.loads((Path(__file__).parent / "fixtures/boss_cuts.json").read_text(encoding="utf-8"))["cases"][0]


def baseline():
    return {
        "id": "original",
        "input": copy.deepcopy(CASE["user"]),
        "damage": {"calculatedData": copy.deepcopy(CASE["calculated"])},
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"bossDmg": "nan"},
        {"atkPer": True},
        {"finalDmg": -100},
        {"finalDmg": 76},
        {"ignoreGuard": 100},
        {"genesis": False},
        {"mainStat": 1.5},
        {"atk": {}},
        None,
    ],
)
def test_invalid_scenarios_rejected(changes):
    with pytest.raises(ValueError):
        simulator.validate(changes)


def test_canonical_changes_preserve_losses_and_strip_zeros():
    assert simulator.validate({"bossDmg": "10.00", "atk": "-20", "mainStat": "", "criDmg": 0}) == {
        "bossDmg": "10",
        "atk": "-20",
    }


def test_body_preserves_absolute_settings_and_original_data():
    user = baseline()["input"]
    user["special"].update(restraintRing="6", continuosRing="4", destiny2ndSkill=True)
    user["linkSkill"].update(ark="3", thief="9")
    user["doping"]["noblessBoss"] = True
    original = copy.deepcopy(user)
    body = simulator.body(user, {"bossDmg": "10", "atkPer": "-5"})
    sim = body["simulator"]
    assert sim["restraintRing"] == "6" and sim["contiRing"] == "4"
    assert sim["linkSimul"] == user["linkSkill"] and sim["dopingSimul"] == user["doping"]
    assert sim["destiny2ndSkill"] is True
    assert sim["masteryCore1"] == user["hexa"]["masteryCore1"]
    assert sim["bossDmg"] == "10" and sim["atkPer"] == "-5"
    sim["dopingSimul"]["noblessBoss"] = False
    assert user == original


def test_fd_comparison_uses_damage_not_score_ratio():
    record = baseline()
    after = copy.deepcopy(record["damage"]["calculatedData"])
    for defense in (300, 380):
        after[f"calculatedHexaDamage_{defense}"] *= 1.1
        after[f"boss{defense}_hexaStat"] += 2000
    result = simulator.comparison(record, after)
    assert result["scores"]["380"]["fd_percent"] == pytest.approx(10)
    assert result["scores"]["380"]["after"] - result["scores"]["380"]["before"] == 2000
    assert len(result["boss_cuts"]["bosses"]) == 55


def test_unusable_api_damage_rejected():
    record = baseline()
    after = copy.deepcopy(record["damage"]["calculatedData"])
    after["calculatedHexaDamage_380"] = float("nan")
    with pytest.raises(ValueError, match="no usable"):
        simulator.comparison(record, after)


def test_simulation_saves_under_original_record_without_overwriting_live_inputs(monkeypatch):
    record = baseline()
    original = copy.deepcopy(record)
    data = {"overrides": {"stat.level": "300"}, "history": [record, {"id": "newer"}]}
    monkeypatch.setattr(service.profiles, "load", lambda _: copy.deepcopy(data))
    writes = []
    monkeypatch.setattr(service.profiles, "write", lambda identifier, value: writes.append(value))
    monkeypatch.setattr(client, "simulate", lambda payload, event: CASE["calculated"])
    monkeypatch.setattr(service, "_job", {"active": True})
    service._run_simulation(
        "test",
        original,
        {"bossDmg": "10"},
        simulator.body(original["input"], {"bossDmg": "10"}),
        threading.Event(),
    )
    assert service.state()["status"] == "complete"
    saved = writes[0]
    assert saved["overrides"] == data["overrides"] and saved["history"][1] == data["history"][1]
    assert saved["history"][0]["input"] == original["input"]
    assert saved["history"][0]["damage"] == original["damage"]
    assert saved["history"][0]["simulations"][0]["changes"] == {"bossDmg": "10"}
    assert saved["history"][0]["simulations"][0]["baseline_id"] == "original"
    assert "simulations" not in original


def test_cancelled_simulation_does_not_save(monkeypatch):
    record = baseline()
    event = threading.Event()
    event.set()
    monkeypatch.setattr(client, "simulate", lambda payload, event: CASE["calculated"])
    monkeypatch.setattr(service, "_job", {"active": True})

    def forbidden(*args):
        raise AssertionError("Cancelled simulation was saved")

    monkeypatch.setattr(service.profiles, "write", forbidden)
    service._run_simulation("test", record, {}, simulator.body(record["input"], {}), event)
    assert service.state()["status"] == "stopped"
    assert service.state()["active"] is False


def test_active_calculation_blocks_simulation(monkeypatch):
    monkeypatch.setattr(service, "_job", {"active": True})
    with pytest.raises(ValueError, match="already running"):
        service.start_simulation("test", {"result_id": "original", "changes": {}})
