"""Offline equipment metadata and per-tier line tables from the source calculator."""

import copy
import math
from functools import lru_cache
from itertools import combinations
from typing import Any

from utils.payload_data import read_payload_json


def normalize(name):
    return " ".join(name.split()).casefold()


@lru_cache(maxsize=1)
def database():
    data = read_payload_json("src/flaming_data/items.json")
    ids = [item["id"] for item in data["items"]]
    if data["version"] != 1 or len(ids) != len(set(ids)):
        raise ValueError("Invalid equipment database")
    return data


@lru_cache(maxsize=1)
def name_index():
    result = {}
    for item in database()["items"]:
        for name in [item["name"], *item["aliases"]]:
            result.setdefault(normalize(name), {})[item["id"]] = item
    return result


def lookup(name, slot=None):
    if not isinstance(name, str) or not name.strip():
        return None
    matches = list(name_index().get(normalize(name), {}).values())
    if slot:
        slot = slot.split("_")[0]
        matches = [item for item in matches if item["slot"] == slot]
    # Xenon's one weapon is listed in both the Thief and Pirate class catalogs.
    # Resolve only exact duplicate records (including source ID and all flame
    # data); different attack, tier eligibility, or identity stays ambiguous.
    if len(matches) > 1 and all(
        item.get("source_id")
        and item.get("slot") == "weapon"
        and item.get("source_classes") == ["xenon"]
        and item.get("job_group") in {"thief", "pirate"}
        for item in matches
    ):
        records = [{k: v for k, v in item.items() if k not in {"id", "job_group"}} for item in matches]
        if all(record == records[0] for record in records[1:]):
            matches = [min(matches, key=lambda item: item["id"])]
    # Never select an arbitrary record for an ambiguous/OCR-misspelled name.
    return copy.deepcopy(matches[0]) if len(matches) == 1 else None


def metadata(name, slot=None):
    item = lookup(name, slot)
    if item is None:
        return None
    fields = (
        "id",
        "name",
        "level",
        "flameable",
        "flame_advantaged",
        "flame_category",
        "base_attack",
        "base_magic_attack",
        "flame_models",
        "metadata_status",
        "rollable_line_pool",
    )
    return {k: item[k] for k in fields}


@lru_cache(maxsize=1)
def rules():
    return read_payload_json("src/flaming_data/flame_rules.json")


def tier_distribution(item, model="brf"):
    if not item["flameable"]:
        return {}
    if model not in item["flame_models"]:
        raise ValueError("Unknown/unverified flame model")
    return rules()["models"][model][item["flame_category"]]


def _weapon_base_attack(item):
    base = item["base_magic_attack"] if item["job_group"] == "magician" else item["base_attack"]
    # Zero's Lazuli retains its own physical attack metadata, but flames
    # are calculated from Lapis. Verified supplemental records carry this.
    base = item.get("flame_base_attack", base)
    if not isinstance(base, (int, float)) or not 0 < base <= 1000:
        raise ValueError("Base weapon attack needs verification")
    return base


def _flame_attack_formula(item, base, mixed):
    def attack(t):
        factor = rules()["normal_weapon_factors"][t - 1] if not item["flame_advantaged"] else t * 1.1 ** (t - 3)
        return math.ceil(base / 100 * mixed * factor)

    return attack


def line_table(item, model="brf") -> list[dict[str, Any]]:
    """19 distinct rollable lines with stat values at every eligible tier.

    Mirrors the calculator's level brackets. Weapon ATT/MATT tables use its
    selected class's base attack, as the source calculator does. Level/attack
    outside that calculator's domain remains unsupported rather than guessed.
    """
    tiers = tier_distribution(item, model)
    if not tiers:
        return []
    level = item["level"]
    if type(level) is not int or not 0 < level <= 300:
        raise ValueError("Item level needs verification")
    level = 10 * (level // 10)
    pure = 12 if level >= 250 else level // 20 + 1
    mixed = level // 40 + 1
    hp = 233.333333 if level >= 250 else level
    weapon = item["slot"] == "weapon"
    base = _weapon_base_attack(item) if weapon else None
    lines = []

    def add(names, formula, percent=False):
        lines.append({"stats": names, "percent": percent, "tiers": {t: formula(int(t)) for t in tiers}})

    for stat in ("STR", "DEX", "INT", "LUK"):
        add([stat], lambda t: t * pure)
    for pair in combinations(("STR", "DEX", "INT", "LUK"), 2):
        add(list(pair), lambda t: t * mixed)
    for stat in ("Max HP", "Max MP"):
        add([stat], lambda t: math.floor(t * hp * 3 + 0.5))
    add(["Defense"], lambda t: t * pure)
    add(["All Stats"], lambda t: t, True)
    add(["Reduced level requirement"], lambda t: -5 * t)
    attack = _flame_attack_formula(item, base, mixed) if weapon else None
    for stat in ("Attack Power", "Magic Attack"):
        add([stat], attack if weapon else lambda t: t)
    if weapon:
        add(["Boss Damage"], lambda t: 2 * t, True)
        add(["Damage"], lambda t: t, True)
    else:
        add(["Speed"], lambda t: t)
        add(["Jump"], lambda t: t)
    return lines
