import copy

import pytest

from scouter import cooldown
from scouter.score_curve import damage_at_score, score_from_damage


def curve(factor=1):
    return {"x": [0, 1000], "y": [0, 1000 * factor], "m": [factor, factor]}


def record():
    return {
        "id": "baseline",
        "input": {
            "stat": {"myClass": "Shadower", "coolTimeReduce": "4", "coolTimeReducePercent": "6"},
            "hexa": {"masteryCore1": 30},
        },
        "damage": {"calculatedData": {"calculatedHexaDamage_380": 100, "spline_380": curve()}},
    }


def test_cooldown_gain_uses_common_damage_scale_not_score_percentage():
    r = record()
    # Nonlinear baseline: doubling score is not doubling damage.
    r["damage"]["calculatedData"]["spline_380"] = {"x": [0, 10, 20], "y": [0, 100, 400], "m": [0, 20, 40]}
    calls = []

    def fetch(user):
        calls.append(user)
        return {"calculatedData": {"spline_380": curve(8)}}

    m = cooldown.HatModel(r, 4, {}, fetch, lambda: None, lambda _: None)
    assert len(calls) == 6
    assert all(
        u["stat"]["myClass"] == "Shadower"
        and u["stat"]["coolTimeReducePercent"] == "6"
        and u["hexa"] == r["input"]["hexa"]
        for u in calls
    )
    # Candidate's damage 100 => score 12.5 => baseline-equivalent damage 156.25.
    assert m.gain(6, 0) == pytest.approx(56.25)
    assert m.gain(4, -0.00001) == -0.00001
    assert r["input"]["stat"]["coolTimeReduce"] == "4"


def test_curve_inverse_does_not_round_small_changes():
    assert score_from_damage(curve(), 12.49) == 12
    assert score_from_damage(curve(), 12.49, rounded=False) == pytest.approx(12.49)
    assert damage_at_score(curve(), score_from_damage(curve(), 12.49, rounded=False)) == pytest.approx(12.49)


def test_cache_is_bound_to_class_hexa_and_baseline():
    r = record()
    cache = {}
    calls = []

    def fetch(user):
        calls.append(copy.deepcopy(user))
        # Two classes can have entirely different cooldown benefits.
        return {
            "calculatedData": {"spline_380": curve(0.8 if user["stat"]["myClass"] == "Shadower" else 0.95)}
        }

    def model():
        return cooldown.HatModel(r, 4, cache, fetch, lambda: None, lambda _: None)

    first = model()
    assert first.gain(6, 0) == pytest.approx(25)
    assert len(calls) == 6
    model()
    assert len(calls) == 6
    r["input"]["stat"]["myClass"] = "Hero"
    assert model().gain(6, 0) == pytest.approx(100 / 0.95 - 100)
    assert len(calls) == 12
    r["input"]["hexa"]["masteryCore1"] = 1
    model()
    assert len(calls) == 18
    r["id"] = "new-calculation"
    model()
    assert len(calls) == 24


def test_other_cooldown_seconds_are_preserved_and_mismatch_rejected():
    r = record()
    r["input"]["stat"]["coolTimeReduce"] = "5"
    calls = []

    def fetch(user):
        calls.append(float(user["stat"]["coolTimeReduce"]))
        return {"calculatedData": {"spline_380": curve()}}

    cooldown.HatModel(r, 4, {}, fetch, lambda: None, lambda _: None)
    assert calls == [1, 2, 3, 4, 6, 7]
    with pytest.raises(ValueError, match="Rescan"):
        cooldown.HatModel(r, 6, {}, fetch, lambda: None, lambda _: None)


def test_unavailable_api_is_not_treated_as_zero_cooldown_value():
    with pytest.raises(ValueError, match="connected"):
        cooldown.HatModel(record(), 4, {}, None, lambda: None, lambda _: None)
    with pytest.raises(ValueError, match="unavailable"):
        cooldown.HatModel(record(), 4, {}, lambda _: {}, lambda: None, lambda _: None)


def test_cancel_checked_after_request():
    stop = False

    def fetch(_):
        nonlocal stop
        stop = True
        return {"calculatedData": {"spline_380": curve()}}

    def checkpoint():
        if stop:
            raise InterruptedError("cancelled")

    with pytest.raises(InterruptedError):
        cooldown.HatModel(record(), 4, {}, fetch, checkpoint, lambda _: None)


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        {},
        {"x": [0, 1], "y": [0, 1], "m": [1]},
        {"x": [0, 1], "y": [1, 0], "m": [1, 1]},
        {"x": [0, 1], "y": [0, 1], "m": [1, float("nan")]},
    ],
)
def test_invalid_curves_fail_explicitly(invalid):
    with pytest.raises(ValueError):
        cooldown.validate_curve(invalid)


def test_shadower_mixed_rolls_match_full_api_comparisons():
    import json
    from pathlib import Path

    from scouter import profiles

    fixture = json.loads((Path(__file__).parent / "fixtures/cooldown.json").read_text(encoding="utf-8"))
    r = record()
    r["damage"]["calculatedData"].update(
        calculatedHexaDamage_380=fixture["damage"], spline_380=fixture["curves"]["4"]
    )
    cache = {
        "baseline_id": r["id"],
        "fingerprint": profiles.fingerprint(r["input"]),
        "curves": fixture["curves"],
    }
    m = cooldown.HatModel(r, 4, cache, None, lambda: None, lambda _: None)
    gains = []
    for case in fixture["cases"]:
        delta = (
            case["luk"] * fixture["weights"]["LUK %"]
            + (case["all_stat"] - 7) * fixture["weights"]["All Stats %"]
        )
        gain = m.gain(case["seconds"], delta)
        score = score_from_damage(m.base_curve, m.damage * (1 + gain / 100))
        # Marginal stat approximation is within three score points of full API runs.
        assert abs(score - case["api_score"]) <= 3
        gains.append(gain)
    assert gains[4] > gains[2] > gains[3] > gains[1] > gains[0] > gains[5] > gains[6]
