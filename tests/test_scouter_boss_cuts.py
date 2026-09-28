"""Check boss estimates against the website's original JavaScript output."""

import copy
import json
from pathlib import Path

import pytest

from scouter import boss_cuts, profiles

FIXTURE = json.loads((Path(__file__).parent / "fixtures/boss_cuts.json").read_text(encoding="utf-8"))


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


def test_rounding_does_not_promote_a_below_minimum_roll():
    assert boss_cuts.display_percent(0.89999, False) == "90.00%"
    assert boss_cuts.classify(0.89999, False, 6) == "파티격 가능"
    assert boss_cuts.classify(0.90, False, 6) == "솔플 최소컷"
    assert boss_cuts.classify(0.90, True, 3) == "3인 최소컷"
