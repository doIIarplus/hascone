"""Potential cost specs for Bright/Glowing estimates of a scanned roll.

Useful line families follow MathBro's calculator (retrieved 2026-09-13):
https://brendonmay.github.io/cubingCalculator/updateDesiredStatsOptions.js
"""

import math

RANKS = ["Rare", "Epic", "Unique", "Legendary"]
SLOTS = {
    **dict.fromkeys(
        ["ring_1", "ring_2", "ring_3", "ring_4", "face", "eye", "earring", "pendant_1", "pendant_2"],
        "accessory",
    ),
    **{slot: slot for slot in ["hat", "gloves", "weapon", "secondary", "emblem"]},
    **dict.fromkeys(["belt", "cape", "top", "bottom", "shoes", "shoulder", "heart", "badge"], "armor"),
}
# Each rule is a minimum total of one weighted line family.
UNITS = {"MAIN_EQ": "percent", "ATT_EQ": "percent", "MATT_EQ": "percent", "CRIT_DAMAGE": "percent", "COOLDOWN": "seconds"}
MAXIMUM = {"percent": 1000, "seconds": 6}


def allowed_metrics(slot, character_class):
    from flaming.profiles import classes

    roles = classes()
    if character_class not in roles:
        raise ValueError("Unknown character class for potential estimates")
    if slot in ("weapon", "secondary", "emblem"):
        return [roles[character_class]["att"] + "_EQ"]
    return ["MAIN_EQ", *(["CRIT_DAMAGE"] if slot == "gloves" else []), *(["COOLDOWN"] if slot == "hat" else [])]


def _validate_shape(spec):
    if not isinstance(spec, dict) or not {"rank", "item_level", "rules"} <= set(spec) or set(spec) - {
        "rank",
        "item_level",
        "rules",
        "score",
        "attack_score",
    }:
        raise ValueError("Invalid potential estimate fields")
    if spec["rank"] not in RANKS:
        raise ValueError("Invalid potential rank")
    level = spec["item_level"]
    if level is not None and (type(level) is not int or not 1 <= level <= 300):
        raise ValueError("Item level must be between 1 and 300, or blank if unknown")


def _validate_attack_score(spec):
    if "attack_score" not in spec:
        return
    attack_score = spec["attack_score"]
    if not isinstance(attack_score, dict) or set(attack_score) != {"boss_per_attack"}:
        raise ValueError("Configure the Boss Damage per ATT/MATT ratio")
    ratio = attack_score["boss_per_attack"]
    if type(ratio) not in (int, float) or not math.isfinite(ratio) or not 0.000001 <= ratio <= 1000:
        raise ValueError("Boss Damage per 1% ATT/MATT must be between 0.000001 and 1000")


def _validate_score_weights(score):
    for key in ("secondary_weight", "all_stat_weight"):
        weight = score[key]
        if type(weight) not in (int, float) or not math.isfinite(weight) or not 0 <= weight <= 10:
            raise ValueError("Stat weights must be between 0 and 10 main-stat percent")


def _validate_scouter_stat_weights(score):
    if "stat_weights" not in score:
        return
    weights = score["stat_weights"]
    from scouter.profiles import class_info

    role = class_info(score["class"])
    allowed_stats = {"Max HP" if role[k] == "HP" else role[k] for k in ("main", "sub", "sub2") if role.get(k)}
    if not isinstance(weights, dict) or set(weights) - allowed_stats:
        raise ValueError("Scouter stat weights must match the character class")
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 10 for v in weights.values()):
        raise ValueError("Scouter stat weights must be finite and between 0 and 10")


def _validate_score(spec, character_class):
    score = spec.get("score")
    if score is None:
        return None
    from flaming.profiles import classes

    if (
        not isinstance(score, dict)
        or set(score)
        not in (
            {"class", "secondary_weight", "all_stat_weight"},
            {"class", "secondary_weight", "all_stat_weight", "stat_weights"},
        )
        or not isinstance(score["class"], str)
        or score["class"] not in classes()
    ):
        raise ValueError("Choose a supported character class for the equivalent score")
    _validate_score_weights(score)
    _validate_scouter_stat_weights(score)
    if score["class"] != character_class:
        raise ValueError("Potential weights belong to a different class")
    return score


def _validate_rules(spec, allowed):
    rules = spec["rules"]
    if not isinstance(rules, list) or len(rules) > len(allowed):
        raise ValueError("Invalid potential rules")
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {"metric", "unit", "value"} or rule["metric"] not in allowed:
            raise ValueError("Invalid potential rule")
        unit, value = rule["unit"], rule["value"]
        if unit != UNITS[rule["metric"]] or type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Invalid potential rule value")
        if not 0 < value <= MAXIMUM[unit]:
            raise ValueError(f"Invalid potential rule value for {unit}")
        if rule["metric"] == "MAIN_EQ" and "score" not in spec or rule["metric"].endswith("ATT_EQ") and "attack_score" not in spec:
            raise ValueError("Potential weights are missing")


def validate_spec(slot, spec, character_class):
    if slot not in SLOTS:
        raise ValueError("This equipment slot does not support potential estimates")
    _validate_shape(spec)
    _validate_attack_score(spec)
    _validate_score(spec, character_class)
    _validate_rules(spec, allowed_metrics(slot, character_class))
    return spec
