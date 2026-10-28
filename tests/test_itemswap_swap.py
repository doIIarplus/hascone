import copy
import json
from pathlib import Path

import pytest

from itemswap import prefill, swap
from itemswap import service as swap_service
from scouter import client, profiles, service

HERO = profiles.class_info("Hero")
CASE = json.loads((Path(__file__).parent / "fixtures/boss_cuts.json").read_text(encoding="utf-8"))["cases"][0]


def ring_swap(enabled=True):
    return {"enabled": enabled, "current": {"item": "giant-fear"}, "candidate": {"item": "whisper-of-the-source"}}


def config(**slots):
    return {"slots": slots, "groups": []}


def test_delta_is_candidate_minus_current_over_enabled_slots_only():
    result = swap.compute(HERO, config(ring_1=ring_swap(), ring_2={**ring_swap(False)}))
    assert result["delta"] == {"mainStat": 5, "subStat": 5, "atk": 1}
    assert result["changes"] == {"mainStat": "5", "subStat": "5", "atk": "1"}
    assert result["slots"]["ring_2"]["delta"] == {"mainStat": 5, "subStat": 5, "atk": 1}
    assert result["blockers"] == []


def test_disabled_slot_keeps_its_inputs_and_toggling_restores_the_delta():
    cfg = config(ring_1=ring_swap())
    on = swap.compute(HERO, cfg)["delta"]
    cfg["slots"]["ring_1"]["enabled"] = False
    off = swap.compute(HERO, cfg)
    assert off["delta"] == {} and cfg["slots"]["ring_1"]["candidate"] == {"item": "whisper-of-the-source"}
    assert "Turn on at least one" in off["blockers"][0]
    cfg["slots"]["ring_1"]["enabled"] = True
    assert swap.compute(HERO, cfg)["delta"] == on


def test_same_item_and_inputs_on_both_sides_contribute_nothing():
    side = {"item": "warrior:eternal-warrior-hat", "stars": 22, "potential": {"mainStatPer": 30}}
    result = swap.compute(HERO, config(hat={"enabled": True, "current": side, "candidate": copy.deepcopy(side)}))
    assert result["delta"] == {} and result["changes"] == {}


def test_custom_groups_take_signed_values_and_skip_disabled_groups():
    groups = [
        {"id": "a", "name": "Pitched 3 -> 2", "enabled": True, "fields": {"bossDmg": "-10", "atk": 5}},
        {"id": "b", "name": "Brilliant 0 -> 2", "enabled": True, "fields": {"bossDmg": 10, "finalDmg": "-2.5"}},
        {"id": "c", "name": "Ignored", "enabled": False, "fields": {"mainStat": 100}},
    ]
    result = swap.compute(HERO, {"slots": {}, "groups": groups})
    assert result["delta"] == {"atk": 5, "finalDmg": -2.5}
    assert [g["delta"] for g in result["groups"]] == [{"atk": 5, "bossDmg": -10}, {"bossDmg": 10, "finalDmg": -2.5},
                                                      {"mainStat": 100}]


def test_swaps_saved_with_a_lose_mode_still_subtract():
    groups = [
        {"id": "a", "name": "Lose Pitched 3-set", "enabled": True, "mode": "lose", "fields": {"bossDmg": "10", "atk": 5}},
        {"id": "b", "name": "Gain Brilliant 2-set", "enabled": True, "mode": "gain", "fields": {"bossDmg": 10}},
        {"id": "c", "name": "Ignored", "enabled": False, "mode": "gain", "fields": {"mainStat": 100}},
    ]
    result = swap.compute(HERO, {"slots": {}, "groups": groups})
    assert result["delta"] == {"atk": -5}
    assert [g["delta"] for g in result["groups"]] == [{"atk": -5, "bossDmg": -10}, {"bossDmg": 10}, {"mainStat": 100}]
    groups[0]["fields"] = {"bossDmg": 10}
    assert swap.compute(HERO, {"slots": {}, "groups": groups})["delta"] == {}


def test_fractional_whole_number_fields_are_reported_not_rounded():
    groups = [{"id": "a", "name": "x", "enabled": True, "mode": "gain", "fields": {"mainStat": "1.5"}}]
    result = swap.compute(HERO, {"slots": {}, "groups": groups})
    assert any("whole number" in b for b in result["blockers"])
    assert result["changes"] == {}


def test_unlisted_current_item_blocks_until_base_stats_or_acknowledged():
    current = {"item": "custom", "unlisted": True, "scanned_name": "Odd Ring", "custom_base": {}}
    entry = {"enabled": True, "current": current, "candidate": {"item": "whisper-of-the-source"}}
    assert any("not in the item list" in b for b in swap.compute(HERO, config(ring_1=entry))["blockers"])
    entry["current"]["no_base"] = True
    assert swap.compute(HERO, config(ring_1=entry))["blockers"] == []
    entry["current"].update(no_base=False, custom_base={"str": 5})
    assert swap.compute(HERO, config(ring_1=entry))["blockers"] == []


def test_demon_avenger_is_blocked_with_a_reason():
    result = swap.compute(profiles.class_info("Demon Avenger"), config(ring_1=ring_swap()))
    assert result["changes"] == {} and "Demon Avenger" in result["blockers"][0]


def test_enabled_slot_needs_a_candidate_and_invalid_input_blocks():
    result = swap.compute(HERO, config(ring_1={"enabled": True, "current": {"item": "giant-fear"}, "candidate": {}}))
    assert any("Choose a candidate" in b for b in result["blockers"])
    bad = {"enabled": True, "current": {"item": "giant-fear"}, "candidate": {"item": "giant-fear", "stars": 99}}
    result = swap.compute(HERO, config(ring_1=bad))
    assert "at most 30" in result["errors"]["ring_1"] and result["blockers"]
    bad["enabled"] = False
    assert "at most 30" in swap.compute(HERO, config(ring_1=bad))["errors"]["ring_1"]


@pytest.mark.parametrize(
    "cfg",
    [None, {"slots": []}, {"slots": {"weapon": {}}}, {"slots": {"android": {}}}, {"groups": [{"mode": "maybe"}]},
     {"groups": [{"mode": "gain", "name": "x" * 81}]}, {"slots": {"hat": {"current": "Eternal"}}}],
)
def test_malformed_config_rejected(cfg):
    with pytest.raises(ValueError):
        swap.compute(HERO, cfg)


def test_duplicate_rings_warn_and_set_pieces_are_hinted():
    cfg = config(
        ring_1={"enabled": True, "current": {"item": "giant-fear"}, "candidate": {"item": "whisper-of-the-source"}},
        ring_2={"enabled": False, "current": {"item": "whisper-of-the-source"}, "candidate": {}},
    )
    result = swap.compute(HERO, cfg)
    assert "Whisper of the Source is in both ring_1 and ring_2" in result["warnings"][0]
    assert result["set_hint"] == [
        {"set": "Brilliant Boss", "before": 1, "after": 2},
        {"set": "Pitched Boss", "before": 1, "after": 0},
    ]


def test_prefill_reads_scanned_potential_flames_and_stars():
    item = {
        "name": "Eternal Knight Helm",
        "starforce": {"status": "scanned", "stars": 19, "max_stars": 30},
        "stats": [{"name": "STR", "value": 114, "percent": False}, {"name": "All Stats", "value": 5, "percent": True},
                  {"name": "Attack Power", "value": 5, "percent": False}, {"name": "Jump", "value": 5}],
        "potential": {"lines": ["Skill Cooldowns -2 sec", "DEX:+10%", "Damage +9%", "Boss Damage +30%",
                                "Enables the <Decent Combat Orders> skill", "Mystery line"]},
    }
    side, notes = prefill.side("hat", item, HERO)
    assert side["item"] == "warrior:eternal-warrior-hat" and side["stars"] == 19
    assert side["flame"] == {"str": 114, "allStatPer": 5, "att": 5}
    assert side["potential"] == {"coolTimeReduce": 2, "subStatPer": 10, "damage": 9, "bossDmg": 30}
    assert notes == ["Not counted: Mystery line"]


def test_prefill_flags_unlisted_items_and_astra_stage():
    side, notes = prefill.side("ring_4", {"name": "Ring of Restraint", "required_level": 110}, HERO)
    assert side == {"item": "custom", "scanned_name": "Ring of Restraint", "stars": 0, "unlisted": True,
                    "custom_base": {}, "custom_level": 110, "flame": {}, "potential": {}}
    assert "not in the item list" in notes[0]
    astra = {"name": "Astra Force Shield", "starforce": {"status": "scanned", "stars": 18, "max_stars": 20}}
    side, notes = prefill.side("secondary", astra, profiles.class_info("Demon Slayer"))
    assert side["variant"] == {"stage": 2, "version": 1} and side["pick_variant"]
    assert "stage 2" in notes[0]
    assert prefill.side("hat", None, HERO) == ({"item": None, "scanned_name": None}, [])


def test_preview_uses_the_saved_class(monkeypatch):
    monkeypatch.setattr(profiles, "load", lambda _: {"class_info": HERO})
    assert swap_service.preview("x", config(ring_1=ring_swap()))["changes"] == {"mainStat": "5", "subStat": "5",
                                                                                  "atk": "1"}


class InlineThread:
    def __init__(self, target, args, **_):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


def baseline():
    return {"id": "original", "input": copy.deepcopy(CASE["user"]),
            "damage": {"calculatedData": copy.deepcopy(CASE["calculated"])}, "simulations": [{"id": "old"}]}


def test_swap_simulation_makes_one_call_and_saves_the_full_config(monkeypatch):
    data = {"class_info": HERO, "history": [baseline()]}
    monkeypatch.setattr(profiles, "load", lambda _: copy.deepcopy(data))
    writes, calls = [], []
    monkeypatch.setattr(profiles, "write", lambda identifier, value: writes.append(value))
    monkeypatch.setattr(client, "simulate", lambda payload, event: calls.append(payload) or CASE["calculated"])
    monkeypatch.setattr(service.threading, "Thread", InlineThread)
    monkeypatch.setattr(service, "_job", {"active": False})
    cfg = config(ring_1=ring_swap(), ring_2=ring_swap(False),
                 hat={"enabled": True, "current": {"item": "warrior:faf-warrior-hat"},
                      "candidate": {"item": "warrior:eternal-warrior-hat"}})
    cfg["groups"] = [{"id": "g", "name": "Set", "enabled": True, "mode": "lose", "fields": {"bossDmg": 10}}]
    service.start_swap_simulation("x", {"result_id": "original", "config": cfg})
    assert len(calls) == 1
    assert calls[0]["simulator"]["bossDmg"] == "-10" and calls[0]["simulator"]["mainStat"] == "45"
    saved = writes[0]["history"][0]
    assert saved["simulations"] == [{"id": "old"}]
    run = saved["swap_runs"][0]
    assert run["config"] == cfg and run["config"]["slots"]["ring_2"]["candidate"] == {"item": "whisper-of-the-source"}
    assert run["enabled_slots"] == ["hat", "ring_1"]
    assert run["changes"] == {"atk": "9", "bossDmg": "-10", "ignoreGuard": "5", "mainStat": "45", "subStat": "45"}
    assert set(run["breakdown"]["slots"]) == {"hat", "ring_1"} and run["breakdown"]["groups"][0]["id"] == "g"
    assert run["baseline_id"] == "original" and "380" in run["scores"]
    assert service.state()["status"] == "complete"


def test_blocked_swap_never_reaches_maplescouter(monkeypatch):
    monkeypatch.setattr(profiles, "load", lambda _: {"class_info": HERO, "history": [baseline()]})
    monkeypatch.setattr(client, "simulate", lambda *_: pytest.fail("called MapleScouter"))
    monkeypatch.setattr(service, "_job", {"active": False})
    with pytest.raises(ValueError, match="Turn on at least one"):
        service.start_swap_simulation("x", {"result_id": "original", "config": config(ring_1=ring_swap(False))})
    with pytest.raises(ValueError, match="set up the item swap"):
        service.start_swap_simulation("x", {"result_id": "original", "changes": {}})


def test_deleting_a_saved_swap_keeps_the_others_and_the_calculation(monkeypatch):
    record = {**baseline(), "swap_runs": [{"id": "a"}, {"id": "b"}]}
    data = {"class_info": HERO, "history": [record, {"id": "newer"}]}
    monkeypatch.setattr(profiles, "load", lambda _: copy.deepcopy(data))
    writes = []
    monkeypatch.setattr(profiles, "write", lambda identifier, value: writes.append(value))
    service.delete_swap_run("x", "original", "a")
    saved = writes[0]["history"]
    assert saved[0]["swap_runs"] == [{"id": "b"}]
    assert saved[0]["simulations"] == [{"id": "old"}] and saved[0]["input"] == record["input"]
    assert saved[1] == {"id": "newer"}
    for missing in (("original", "a-typo"), ("gone", "b")):
        with pytest.raises(ValueError, match="not found"):
            service.delete_swap_run("x", *missing)


def test_ruin_force_shield_final_damage_adds_as_entered():
    ds = profiles.class_info("Demon Slayer")
    rfs = {"item": "warrior:ruin-force-shield"}
    astra = {"item": "warrior:astra-force-shield", "variant": {"stage": 3, "version": 1}}
    lost = swap.compute(ds, config(secondary={"enabled": True, "current": rfs, "candidate": astra}))
    assert lost["delta"]["finalDmg"] == -10 and lost["changes"]["finalDmg"] == "-10"
    infused = swap.compute(ds, config(secondary={"enabled": True, "current": rfs,
                                                 "candidate": {**astra, "addons": {"rfs_infused": 1}}}))
    assert "finalDmg" not in infused["delta"]
    groups = [{"id": "g", "name": "x", "enabled": True, "fields": {"finalDmg": 10}}]
    both = swap.compute(ds, {"slots": {"secondary": {"enabled": True, "current": astra,
                                                     "candidate": {**astra, "addons": {"rfs_infused": 1}}}},
                             "groups": groups})
    assert both["delta"] == {"finalDmg": 20}
