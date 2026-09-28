"""Validated stat-change scenarios against immutable, saved API inputs."""

import copy
import math

from scouter.boss_cuts import with_boss_cuts
from utils.payload_data import read_payload_json


def fields():
    return read_payload_json("src/scouter/data/simulator.json")["fields"]


def validate(changes):
    if not isinstance(changes, dict):
        raise ValueError("Enter stat changes as an object")
    allowed = {f["key"]: f for f in fields()}
    cleaned = {}
    for key, value in changes.items():
        if key not in allowed:
            raise ValueError(f"Unsupported simulator field: {key}")
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError(f"{allowed[key]['label']} must be a number")
        try:
            number = float(value) if value != "" else 0.0
        except ValueError as exc:
            raise ValueError(f"{allowed[key]['label']} must be a number") from exc
        f = allowed[key]
        if not math.isfinite(number) or not f["min"] <= number <= f["max"]:
            raise ValueError(f"{f['label']} must be between {f['min']} and {f['max']}")
        if f["step"] == 1 and not number.is_integer():
            raise ValueError(f"{f['label']} must be a whole number")
        if number:
            cleaned[key] = format(number, ".12g")
    return cleaned


def body(user, changes):
    sim = read_payload_json("src/scouter/data/simulator.json")["defaults"]
    # These fields are absolute selections, not deltas. Preserve rings, links,
    # buffs, liberation state, and HEXA levels so only requested stats change.
    for key in sim:
        if key in user["hexa"]:
            sim[key] = str(user["hexa"][key])
    sim["dopingSimul"] = copy.deepcopy(user["doping"])
    sim["linkSimul"] = copy.deepcopy(user["linkSkill"])
    for target, source in {
        "genesis": "genesis",
        "destiny2ndSkill": "destiny2ndSkill",
        "restraintRing": "restraintRing",
        "weaponRing": "weaponRing",
        "ringofSum": "ringOfSum",
        "contiRing": "continuosRing",
        "riskTaker": "riskTaker",
    }.items():
        sim[target] = user["special"][source]
    sim["solJanus"] = user["huntSkill"]["solJanus"]
    sim["erda"] = user["huntSkill"]["erdaShower"]
    sim.update(validate(changes))
    return {"userStat": copy.deepcopy(user), "simulator": sim}


def comparison(baseline, calculated):
    before = baseline["damage"]["calculatedData"]
    scores = {}
    for defense in (300, 380):
        key = f"calculatedHexaDamage_{defense}"
        if not all(
            isinstance(v, (int, float)) and math.isfinite(v) and v > 0
            for v in (before.get(key), calculated.get(key))
        ):
            raise ValueError("Scouter returned no usable HEXA damage for this scenario")
        scores[str(defense)] = {
            "fd_percent": (calculated[key] / before[key] - 1) * 100,
            "before": before[f"boss{defense}_hexaStat"],
            "after": calculated[f"boss{defense}_hexaStat"],
        }
    boss = with_boss_cuts({"input": baseline["input"], "damage": {"calculatedData": calculated}})["boss_cuts"]
    return {"scores": scores, "boss_cuts": boss}
