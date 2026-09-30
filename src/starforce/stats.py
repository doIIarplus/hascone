"""Star Force stat deltas, using the shared equipment metadata."""

import math
from functools import lru_cache

from cubing.item_database import item_metadata
from flaming.item_database import lookup
from utils.payload_data import read_payload_json

SHARED_SLOTS = {"ring", "face", "eye", "earring", "pendant", "belt", "heart", "badge"}
EXCLUDED_SLOTS = {"pocket", "emblem", "android", "medal"}


@lru_cache(maxsize=1)
def database():
    return read_payload_json("src/starforce/data/stats.json")


def metadata(slot, item):
    data = database()
    name = item.get("name") or ""
    part = slot.split("_")[0]
    if part in EXCLUDED_SLOTS:
        raise ValueError("This equipment slot cannot be Star Forced")
    if part == "weapon" and any(
        name.casefold().startswith(p.casefold()) for p in data["fixed_weapon_prefixes"]
    ):
        raise ValueError("Fixed Genesis/Destiny weapon; additional Star Force is unavailable")
    if any(name.casefold().startswith(p.casefold()) for p in data["unsupported_prefixes"]):
        raise ValueError("Superior or special weapon Star Force rules are not yet supported")
    meta = item_metadata(slot, item)
    if not meta:
        raise ValueError("Item level is unknown; scan or enter its level first")
    level = meta["level"]
    band = next((b for b in data["bands"] if b["min_level"] <= level <= b["max_level"]), None)
    if band is None:
        raise ValueError("Star Force stat table is unavailable for this item level")
    source = lookup(name, slot) or {}
    job = (item.get("starforce") or {}).get("job") or source.get("job_group")
    if part in SHARED_SLOTS:
        job = "shared"
    if job:
        job = job.casefold()
    if part == "secondary" and "deimos shadow shield" in name.casefold():
        job = "thief"
    # Kanna's Talismans gain weapon attack per star, like a Katara.
    weapon_secondary = part == "secondary" and any(k in name.casefold() for k in ("katara", "talisman"))
    kind = "weapon" if part == "weapon" or weapon_secondary else "armor"
    return {
        "level": level,
        "band": band,
        "job": job,
        "kind": kind,
        "slot": part,
        "base_attack": source.get("base_attack"),
        "base_magic_attack": source.get("base_magic_attack"),
        "cap": next(cap for high, cap in data["level_caps"] if level <= high),
    }


def _stat_and_hp_gain(meta, data, band, current, target):
    result = {}
    stat = sum(band["stat_per_star"][current + 1 : target + 1])
    if stat:
        job_stats = data["job_stats"].get(meta["job"])
        if not job_stats:
            raise ValueError("Required Job is unknown; scan the item tooltip again")
        result.update({key: stat for key in job_stats})
    hp = sum(data["hp_per_star"][current + 1 : target + 1])
    if hp and meta["slot"] not in data["no_hp_slots"]:
        result["Max HP"] = hp
    return result


def _armor_attack_gain(meta, data, band, current, target):
    attack = sum(band["armor_attack_per_star"][current + 1 : target + 1])
    if meta["slot"] == "gloves":
        attack += sum(current < n <= target for n in data["glove_attack_stars"])
    return {"Attack Power": attack, "Magic Attack": attack} if attack else {}


def _weapon_attack_gain(meta, band, current, target):
    if target > 15 + len(band["weapon_attack_16_plus"]) and target > 15:
        raise ValueError("High-star weapon stat table is unavailable for this level")
    result = {}
    for key, base in [("Attack Power", meta["base_attack"]), ("Magic Attack", meta["base_magic_attack"])]:
        if base is None or base == 0:
            continue
        attack, increase = base, 0
        for star in range(1, target + 1):
            delta = math.floor(attack * 0.02 + 1) if star <= 15 else band["weapon_attack_16_plus"][star - 16]
            attack += delta
            if star > current:
                increase += delta
        result[key] = increase
    if not any(key in result for key in ("Attack Power", "Magic Attack")):
        raise ValueError("Clean weapon attack is unknown; Star Force attack cannot be calculated")
    return result


def gains(meta, current, target):
    if not 0 <= current < target <= meta["cap"]:
        raise ValueError("Star Force target exceeds this item’s star limit")
    data, band = database(), meta["band"]
    result = _stat_and_hp_gain(meta, data, band, current, target)
    if meta["kind"] == "armor":
        result.update(_armor_attack_gain(meta, data, band, current, target))
    else:
        result.update(_weapon_attack_gain(meta, band, current, target))
    return {key: value for key, value in result.items() if value}
