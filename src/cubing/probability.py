"""Enumerate ordered line outcomes using the calculator's published rate tables.

Previous restricted categories alter the next line's denominator.
Estimates are conditional on rolling at a fixed rank, excluding tier-up costs.
"""

import json
from collections import defaultdict
from functools import lru_cache
from typing import Any

from cubing.matching import compile_matcher
from cubing.targets import SLOTS, validate_spec
from utils.payload_data import read_payload_json

LIMITS = {
    "Decent Skill": 1,
    "Increase invincibility time after being hit": 1,
    "Chance to ignore % damage when hit": 2,
    "Chance of being invincible for seconds when hit": 2,
    "Ignore Enemy Defense %": 3,
    "Boss Damage": 3,
    "Item Drop Rate %": 3,
}
STAT_CATEGORIES = {"STR %", "DEX %", "INT %", "LUK %", "All Stats %", "ATT %", "MATT %", "Max HP %"}
FAMILIES = {
    **{s: {s + " %": 1, "All Stats %": 1} for s in ["STR", "DEX", "INT", "LUK"]},
    "HP": {"Max HP %": 1},
    "ALL_STAT": {"All Stats %": 1},
    "XENON": {"All Stats %": 1, "STR %": 1 / 3, "DEX %": 1 / 3, "LUK %": 1 / 3},
    "ATT": {"ATT %": 1},
    "MATT": {"MATT %": 1},
    "BOSS": {"Boss Damage": 1},
    "IED": {"Ignore Enemy Defense %": 1},
    "CRIT_DAMAGE": {"Critical Damage %": 1},
    "COOLDOWN": {"Skill Cooldown Reduction": 1},
    "DROP": {"Item Drop Rate %": 1},
    "MESO": {"Meso Amount %": 1},
    "DROP_MESO": {"Item Drop Rate %": 1, "Meso Amount %": 1},
}
for attack in ["ATT", "MATT"]:
    for suffix, extra in [
        ("BOSS", ["Boss Damage"]),
        ("IED", ["Ignore Enemy Defense %"]),
        ("BOSS_IED", ["Boss Damage", "Ignore Enemy Defense %"]),
    ]:
        FAMILIES[attack + "_" + suffix] = dict.fromkeys([attack + " %", *extra], 1)


def family(metric, spec):
    if metric in ("ATT_EQ", "MATT_EQ"):
        return {
            metric.removesuffix("_EQ") + " %": 1,
            "Boss Damage": 1 / spec["attack_score"]["boss_per_attack"],
        }
    if metric == "MAIN_EQ":
        score = spec["score"]
        from flaming.profiles import classes

        role = classes()[score["class"]]
        if "stat_weights" in score:
            return {**{s + " %": w for s, w in score["stat_weights"].items()}, "All Stats %": score["all_stat_weight"]}
        return {
            **{s + " %": 1 for s in role["main_stats"]},
            **{s + " %": score["secondary_weight"] for s in role["secondary_stats"]},
            "All Stats %": score["all_stat_weight"],
        }
    return FAMILIES[metric]


@lru_cache(maxsize=1)
def database():
    return read_payload_json("src/cubing/data/rates.json")


def pools_for(raw, level, rules, spec=None):
    """Per-line (category, contributions, rate) pools; contributions follow RULES."""
    families = [family(r["metric"], spec) for r in rules]
    useful = set().union(*families) if families else set()
    result = []
    for line in ["first_line", "second_line", "third_line"]:
        consolidated = defaultdict(float)
        for cat, value, rate in raw[line]:
            # Irrelevant stats retain their restricted category but not their value.
            category = cat if cat in useful or cat in LIMITS else "Junk"
            amount = value + (1 if level >= 160 and cat in STAT_CATEGORIES else 0) if cat in useful else 0
            contributions = tuple(amount * weights.get(cat, 0) for weights in families)
            consolidated[(category, contributions)] += rate / 100
        result.append([(cat, values, rate) for (cat, values), rate in consolidated.items()])
    return result


@lru_cache(maxsize=256)
def _chance(item_type, cube, rank, level, encoded_spec):
    spec = json.loads(encoded_spec)
    pools = pools_for(database()["rates"][item_type][cube][rank], level, spec["rules"], spec)
    accepted = compile_matcher(spec)

    def visit(index, lines, counts):
        if index == 3:
            return float(accepted(lines))
        excluded = {cat for cat, n in counts.items() if n >= LIMITS[cat]}
        denominator = 1 - sum(rate for cat, _, rate in pools[index] if cat in excluded)
        total = 0.0
        for cat, values, rate in pools[index]:
            if cat in excluded:
                continue
            next_counts = counts if cat not in LIMITS else {**counts, cat: counts.get(cat, 0) + 1}
            total += rate / denominator * visit(index + 1, lines + (values,), next_counts)
        return total

    return min(1.0, max(0.0, visit(0, (), {})))


def _level_notes(level):
    notes = []
    if level < 120:
        notes.append(f"Level {level} gear is estimated as level 120.")
    if level > 200:
        notes.append("Above level 200, uses the same level-160+ approximation as the calculator.")
    return notes


def _rule_notes(spec):
    metrics = [r["metric"] for r in spec["rules"]]
    notes = []
    if "MAIN_EQ" in metrics:
        notes.append(
            "Uses your configured All Stat value for the main stat equivalent; it is not a damage or CP estimate."
        )
    if any(m in ("ATT_EQ", "MATT_EQ") for m in metrics):
        notes.append(
            "Attack equivalent uses your configured Boss Damage ratio; IED is separate. This is not a CP prediction."
        )
    return notes


def _cube_odds(item_type, rank, level, spec):
    encoded = json.dumps(spec, sort_keys=True)
    rows = []
    for cube, name in [("black", "Bright"), ("red", "Glowing")]:
        chance = _chance(item_type, cube, rank.lower(), level, encoded)
        rows.append({"cube": name, "probability": chance, "expected_cubes": 1 / chance if chance else None})
    return rows


def estimate(slot, spec, character_class) -> dict[str, Any]:
    """Chance per cube of rolling at least SPEC's rules at its rank."""
    validate_spec(slot, spec, character_class)
    level, rank = spec["item_level"], spec["rank"]
    response = {
        "rank": rank,
        "item_level": level,
        "source": "https://brendonmay.github.io/cubingCalculator/",
        "basis": "Chance per cube at the displayed rank; tier-up cubes are excluded.",
        "notes": ["Uses the calculator’s published 2023 line tables and level-160 stat adjustment."],
    }
    if level is None:
        return {**response, "unavailable": "Item level is unknown. Hover-scan the item to read its required level."}
    if rank not in ("Unique", "Legendary"):
        return {
            **response,
            "unavailable": f"{rank} cost unavailable — Bright/Glowing estimates support Unique and Legendary only.",
        }
    response["notes"] += _level_notes(level) + _rule_notes(spec)
    item_type = "ring" if SLOTS[slot] == "accessory" else "heart" if slot == "badge" else slot
    response["cubes"] = _cube_odds(item_type, rank, max(120, level), spec)
    return response
