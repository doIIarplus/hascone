"""Check boss estimates against the website's original JavaScript output."""

import copy
import json
from pathlib import Path

import pytest

from scouter import boss_cuts, profiles, service

FIXTURE = json.loads((Path(__file__).parent / "fixtures/boss_cuts.json").read_text(encoding="utf-8"))


def api_calculated(case):
    """Current API schema with synthetic values from the public JS fixture.

    Deliberately excludes legacy splines, defense constants, and potion stats.
    No user's inputs or returned calculation are retained in this fixture.
    """
    labels = {label: key for key, label in boss_cuts.catalog()["labels"].items()}
    return {"bossCutsOpts": {"bossTime": 20}, "bossCuts": [
        {"boss": boss["boss"], "difficulty": boss["difficulty"], "clearRate": expected["percent"] / 100,
         "bossStat": expected["boss_hexa_score"], "analytics": labels[expected["category"]],
         "isPartyBoss": bool(boss.get("partyBossCut")), "isPartyLimit": boss.get("partyLimit") or 6,
         "bossPower": 1000, "bossNewbie": 100}
        for boss, expected in zip(boss_cuts.catalog()["bosses"], case["expected"], strict=True)
    ]}


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda c: c["name"])
def test_matches_public_client(case):
    actual = boss_cuts.calculate(case["user"], case["calculated"])
    assert len(actual["bosses"]) == len(case["expected"]) == 55
    for row, expected in zip(actual["bosses"], case["expected"], strict=True):
        assert row["percent"] == pytest.approx(expected["percent"], rel=1e-8)
        for key in ("id", "category", "display_percent", "boss_hexa_score", "relevant"):
            assert row[key] == expected[key]
    destiny = [b for b in actual["bosses"] if b["difficulty"] == "Destiny"]
    assert len(destiny) == 6
    assert all(b["reference"] == "solo" and b["party_limit"] == 1 for b in destiny)
    assert all(Path("src/scouter/data/icons", b["icon"]).is_file() for b in actual["bosses"])


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda c: c["name"])
def test_api_cards_work_without_removed_damage_model_fields(case):
    calculated = api_calculated(case)
    actual = boss_cuts.calculate(case["user"], calculated)
    assert actual["source"] == "maplescouter_api"
    assert actual["available"]
    assert len(actual["bosses"]) == 55
    for row, expected in zip(actual["bosses"], case["expected"], strict=True):
        assert row["percent"] == pytest.approx(expected["percent"])
        for key in ("id", "category", "display_percent", "boss_hexa_score", "relevant"):
            assert row[key] == expected[key]
    assert len([b for b in actual["bosses"] if b["difficulty"] == "Destiny"]) == 6
    assert len([b for b in actual["bosses"] if b["difficulty"] == "Champion"]) == 5


def test_failed_saved_api_result_recovers_while_preserving_raw_result():
    case = FIXTURE["cases"][0]
    record = {"input": case["user"], "damage": {"calculatedData": api_calculated(case)},
              "boss_cuts": {"available": False, "reason": "Calculate again", "bosses": []}}
    original = copy.deepcopy(record)
    assert boss_cuts.with_boss_cuts(record)["boss_cuts"]["available"]
    assert record == original


def test_api_rows_match_identity_after_reordering_and_support_new_bosses():
    case = FIXTURE["cases"][0]
    calculated = api_calculated(case)
    calculated["bossCuts"].reverse()
    calculated["bossCuts"].append({**calculated["bossCuts"][0], "boss": "New boss"})
    cards = boss_cuts.calculate(case["user"], calculated)["bosses"]
    assert cards[0]["id"] == "damien_normal"
    assert cards[-2]["id"] == "jupiter_hard"
    assert cards[-1]["boss"] == "New boss"
    assert cards[-1]["icon"] is None
    assert cards[-1]["entry_level"] is None


def test_api_view_and_quest_filters_do_not_require_recalculation():
    case = FIXTURE["cases"][0]
    cards = boss_cuts.calculate(case["user"], api_calculated(case), view="relevant", include_quests=False)["bosses"]
    assert cards
    assert all(b["relevant"] and b["difficulty"] not in {"Destiny", "Champion"} for b in cards)


@pytest.mark.parametrize("field,value", [("clearRate", float("nan")), ("clearRate", -1),
                                        ("clearRate", True), ("bossStat", None), ("isPartyLimit", 0)])
def test_invalid_api_cards_do_not_produce_misleading_estimates(field, value):
    case = FIXTURE["cases"][0]
    calculated = api_calculated(case)
    calculated["bossCuts"][0][field] = value
    record = {"input": case["user"], "damage": {"calculatedData": calculated}}
    assert boss_cuts.with_boss_cuts(record)["boss_cuts"]["available"] is False


def test_api_cards_cannot_silently_use_different_manual_settings():
    case = FIXTURE["cases"][0]
    with pytest.raises(ValueError, match="different boss settings"):
        boss_cuts.calculate(case["user"], api_calculated(case), minutes=10)


def test_legacy_history_uses_saved_input_not_current_profile(monkeypatch):
    case = FIXTURE["cases"][0]
    record = {"id": "old", "input": case["user"], "damage": {"calculatedData": case["calculated"]}}
    profile = {
        "class_info": profiles.class_info("Shadower"),
        "scanned": {},
        "inputs": {"stat.level": "200"},
        "history": [record],
    }
    monkeypatch.setattr(profiles, "load", lambda _: copy.deepcopy(profile))
    result = profiles.snapshot("test")
    assert result["values"]["stat"]["level"] == "200"
    assert result["history"][0]["boss_cuts"] == boss_cuts.calculate(case["user"], case["calculated"])
    assert "input" not in result["history"][0]
    assert "boss_cuts" not in record


def test_saved_catalog_and_results_are_not_silently_recalculated():
    record = {"boss_cuts": {"snapshot": "old", "bosses": [{"percent": 42}]}}
    assert boss_cuts.with_boss_cuts(record) is record


def test_missing_boss_data_keeps_successful_score():
    record = {"damage": {"calculatedData": {"boss380_hexaStat": 82440}}}
    enriched = boss_cuts.with_boss_cuts(record)
    assert enriched["damage"] == record["damage"]
    assert not enriched["boss_cuts"]["available"]
    assert "Calculate again" in enriched["boss_cuts"]["reason"]


def test_previously_failed_estimate_recovers_from_saved_data_without_changing_record():
    case = FIXTURE["cases"][0]
    record = {"input": case["user"], "damage": {"calculatedData": case["calculated"]},
              "boss_cuts": {"available": False, "reason": "Previous failure", "bosses": []}}
    original = copy.deepcopy(record)
    enriched = boss_cuts.with_boss_cuts(record)
    assert enriched["boss_cuts"]["available"]
    assert len(enriched["boss_cuts"]["bosses"]) == 55
    assert record == original


def test_response_port_failure_retains_diagnostics_and_does_not_claim_the_result_is_old():
    case = FIXTURE["cases"][0]
    record = {"input": case["user"], "damage": {"calculatedData": copy.deepcopy(case["calculated"])}}
    del record["damage"]["calculatedData"]["spline_380"]
    cuts = boss_cuts.with_boss_cuts(record)["boss_cuts"]
    assert cuts["available"] is False
    assert cuts["error"] == {"type": "KeyError", "field": "spline_380"}
    assert "Calculate again" not in cuts["reason"]
    assert "HEXA score" in cuts["reason"]


@pytest.mark.parametrize("usable", [False, True])
def test_calculate_refreshes_failed_cached_data_but_reuses_locally_recoverable_result(monkeypatch, usable):
    from unittest.mock import Mock

    case = FIXTURE["cases"][0]
    record = {"id": "saved", "fingerprint": "same-inputs", "input": case["user"],
              "damage": {"calculatedData": copy.deepcopy(case["calculated"])}, "order": {"class_hexa": []},
              "boss_cuts": {"available": False, "reason": "Previous failure", "bosses": []}}
    if not usable:
        del record["damage"]["calculatedData"]["spline_380"]
    monkeypatch.setattr(profiles, "load", lambda _: {"history": [record]})
    monkeypatch.setattr(profiles, "payload", lambda _: case["user"])
    monkeypatch.setattr(profiles, "effective", lambda _: case["user"])
    monkeypatch.setattr(profiles, "fingerprint", lambda _: "same-inputs")
    monkeypatch.setattr(service, "_job", {"active": False})
    monkeypatch.setattr(service, "_cancelled", service.threading.Event())
    thread = Mock()
    monkeypatch.setattr(service.threading, "Thread", thread)
    result = service.start("character")
    if usable:
        assert not result["active"]
        assert result["result_id"] == "saved"
        thread.assert_not_called()
    else:
        assert result["active"]
        thread.return_value.start.assert_called_once()


def test_rounding_does_not_promote_a_below_minimum_roll():
    assert boss_cuts.display_percent(0.89999, False) == "90.00%"
    assert boss_cuts.classify(0.89999, False, 6) == "파티격 가능"
    assert boss_cuts.classify(0.90, False, 6) == "솔플 최소컷"
    assert boss_cuts.classify(0.90, True, 3) == "3인 최소컷"
