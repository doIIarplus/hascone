"""Cube equipment levels: shared flame catalog plus verified non-flame gear."""

import copy
from functools import lru_cache

from flaming.item_database import lookup as flame_lookup
from flaming.item_database import normalize
from utils.payload_data import read_payload_json


@lru_cache(maxsize=1)
def supplements():
    return read_payload_json("src/cubing/data/equipment_levels.json")["items"]


def metadata(name, slot):
    if not isinstance(name, str):
        return None
    item = flame_lookup(name, slot)
    if item:
        return {key: item[key] for key in ("name", "level", "slot")}
    found = [
        row
        for row in supplements()
        if row["slot"] == slot.split("_")[0]
        and normalize(name) in [normalize(n) for n in [row["name"], *row["aliases"]]]
    ]
    return copy.deepcopy(found[0]) if len(found) == 1 else None


def item_metadata(slot, item):
    catalog = metadata(item.get("name"), slot)
    level = item.get("required_level")
    if type(level) is int and 1 <= level <= 300:
        return {**(catalog or {}), "name": item.get("name"), "slot": slot.split("_")[0], "level": level}
    return catalog

