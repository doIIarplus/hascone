"""Item swap tab data: catalog with scan prefill, and the no-network preview."""

from itemswap import catalog, prefill, swap
from itemswap.contribution import resolve, uses_magic


def _gear(identifier):
    from flaming import characters

    try:
        return characters.load(identifier)
    except (OSError, ValueError, KeyError):
        return {}


def catalog_payload(identifier):
    from scouter import profiles
    from utils.payload_data import read_payload_json

    info = profiles.load(identifier)["class_info"]
    gear = _gear(identifier)
    equipment = gear.get("equipment") or {}
    current, notes = {}, {}
    for slot in swap.swappable_slots():
        current[slot], notes[slot] = prefill.side(slot, equipment.get(slot), info)
    items = []
    for item in catalog.for_class(info):
        # The editor's Stars box needs the cap the server enforces (level-based unless listed).
        _, _, _, cap, _ = resolve({"item": item["id"]}, item["slot"])
        items.append({**item, "star_cap": cap})
    return {
        "items": items,
        "layout": read_payload_json("src/flaming_data/equipment_layout.json")["slots"],
        # Only what the slot grid needs to show icons; the gear itself stays on the gear endpoint.
        "equipment": {k: {"name": v.get("name"), "occupied": v.get("occupied"), "updated": v.get("updated")}
                      for k, v in equipment.items()},
        "captured": gear.get("equipment_captured"),
        "slots": swap.swappable_slots(),
        "unswappable": sorted(catalog.UNSWAPPABLE),
        "current": current,
        "notes": notes,
        "blocked": swap.blocked(info),
        "class": {"main": info["main"], "sub": info["sub"], "sub2": info["sub2"], "magic": uses_magic(info)},
    }


def preview(identifier, config):
    from scouter import profiles

    return swap.compute(profiles.load(identifier)["class_info"], config)
