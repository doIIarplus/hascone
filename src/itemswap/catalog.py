"""Canonical Item swap catalog: base stats, upgrade flags and class visibility per item."""

import re
from functools import lru_cache

from utils.payload_data import read_payload_json

PATH = "src/itemswap/data/items.json"
SLOTS = {"ring", "belt", "face", "eye", "earring", "pendant", "pocket", "secondary", "emblem", "medal", "heart", "badge",
         "hat", "top", "bottom", "shoulder", "cape", "gloves", "shoes"}
JOBS = {"common", "warrior", "magician", "archer", "thief", "pirate"}
BASE_KEYS = {"str", "dex", "int", "luk", "att", "matt", "bossDmg", "ignoreGuard", "criDmg", "finalDmg"}
ADDON_KEYS = {"allstat", "att", "finalDmg"}
# Weapon and Android have no listed items, so they are never swappable.
UNSWAPPABLE = {"weapon", "android"}

# Scouter class slug -> catalog job groups and class key. Names differ between MapleScouter,
# the whackybeanz catalog and the wiki (Dawn Warrior / Soul Master, Shade / Eunwol, ...).
CLASSES = {
    "hero": ("warrior", "hero"), "paladin": ("warrior", "paladin"), "dark_knight": ("warrior", "dk"),
    "dawn_warrior": ("warrior", "sm"), "mihile": ("warrior", "mihile"), "aran": ("warrior", "aran"),
    "blaster": ("warrior", "blaster"), "demon_slayer": ("warrior", "ds"), "demon_avenger": ("warrior", "da"),
    "kaiser": ("warrior", "kaiser"), "zero": ("warrior", "zero"), "adele": ("warrior", "adele"),
    "hayato": ("warrior", "hayato"),
    "fire_poison": ("magician", "fp"), "ice_lightning": ("magician", "il"), "bishop": ("magician", "bs"),
    "blaze_wizard": ("magician", "fw"), "evan": ("magician", "evan"), "luminous": ("magician", "lumi"),
    "battle_mage": ("magician", "bam"), "kinesis": ("magician", "kinesis"), "illium": ("magician", "illium"),
    "lara": ("magician", "lara"), "kanna": ("magician", "kanna"), "lynn": ("magician", "lynn"),
    "sia_astelle": ("magician", "sia"),
    "bowmaster": ("archer", "bm"), "marksman": ("archer", "xbm"), "pathfinder": ("archer", "pf"),
    "wind_archer": ("archer", "wb"), "mercedes": ("archer", "merc"), "wild_hunter": ("archer", "wh"),
    "kain": ("archer", "kain"),
    "night_lord": ("thief", "nl"), "shadower": ("thief", "sdw"), "dual_blade": ("thief", "db"),
    "night_walker": ("thief", "nw"), "phantom": ("thief", "phantom"), "cadena": ("thief", "cadena"),
    "khali": ("thief", "khali"), "hoyoung": ("thief", "hy"),
    "buccaneer": ("pirate", "viper"), "corsair": ("pirate", "captain"), "cannoneer": ("pirate", "cm"),
    "thunder_breaker": ("pirate", "striker"), "shade": ("pirate", "eunwol"), "mechanic": ("pirate", "mech"),
    "angelic_buster": ("pirate", "ab"), "ark": ("pirate", "ark"), "mo_xuan": ("pirate", "mx"),
    # Xenon is in both the Thief and Pirate catalogs and may wear either job's armor.
    "xenon": (("thief", "pirate"), "xenon"),
    # Ren and Erel Light are not catalog classes: only common items and their own secondaries.
    "ren": ((), "ren"), "erel_light": ((), "erel_light"), "lethe": ((), "lethe"),
}


def normalize(name):
    return re.sub(r"[^a-z0-9]", "", str(name or "").casefold().replace("’", "'"))


def validate(data):
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("items"), list):
        raise ValueError("Invalid Item swap catalog")
    ids = set()
    for item in data["items"]:
        where = f"Item swap catalog entry {item.get('id')!r}"
        for key in ("id", "name", "aliases", "slot", "level", "job", "classes", "base", "flame", "potential",
                    "starforce"):
            if key not in item:
                raise ValueError(f"{where} is missing {key}")
        if item["id"] in ids:
            raise ValueError(f"{where} is duplicated")
        ids.add(item["id"])
        if item["slot"] not in SLOTS:
            raise ValueError(f"{where} has unknown slot {item['slot']}")
        if item["job"] not in JOBS:
            raise ValueError(f"{where} has unknown job group {item['job']}")
        known = {slug for _, slug in CLASSES.values()} | {"len", "da"}
        if not set(item["classes"]) <= known:
            raise ValueError(f"{where} has unknown classes {item['classes']}")
        for base in [item["base"], *(v["base"] for v in item.get("variants", []))]:
            if not set(base) <= BASE_KEYS or not all(type(v) is int for v in base.values()):
                raise ValueError(f"{where} has invalid base stats")
        if item["starforce"] and not (type(item["level"]) is int and 1 <= item["level"] <= 300):
            raise ValueError(f"{where} needs a level 1-300 for Star Force")
        for addon in item.get("addons", []):
            if (set(addon) != {"id", "label", "max", "per"} or type(addon["max"]) is not int or addon["max"] < 1
                    or not set(addon["per"]) <= ADDON_KEYS):
                raise ValueError(f"{where} has an invalid add-on")
        for variant in item.get("variants", []):
            if set(variant) != {"stage", "version", "label", "base", "max_stars"} or not 1 <= variant["max_stars"] <= 30:
                raise ValueError(f"{where} has an invalid stage")
    return data


@lru_cache(maxsize=1)
def database():
    return validate(read_payload_json(PATH))


def by_id():
    return {item["id"]: item for item in database()["items"]}


def class_key(class_info):
    jobs, slug = CLASSES.get(class_info.get("slug"), ((), None))
    return ((jobs,) if isinstance(jobs, str) else tuple(jobs)), slug


def visible(item, class_info):
    jobs, slug = class_key(class_info)
    if item["classes"]:
        return slug in item["classes"]
    return item["job"] == "common" or item["job"] in jobs


def for_class(class_info):
    return [item for item in database()["items"] if visible(item, class_info)]


def match(name, slot, class_info):
    """Exact (normalized) name or alias match among the class's items for this slot, never a guess."""
    key = normalize(name)
    if not key:
        return None
    part = slot.split("_")[0]
    found = [
        item for item in for_class(class_info)
        if item["slot"] == part and key in {normalize(n) for n in [item["name"], *item["aliases"]]}
    ]
    return found[0] if len(found) == 1 else None
