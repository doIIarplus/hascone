"""What one equipped item adds to the Simulator's stat fields."""

import math

from itemswap import catalog
from scouter.simulator import fields as simulator_fields
from starforce import stats as starforce

FLAME_KEYS = ("str", "dex", "int", "luk", "att", "matt", "allStatPer")
POTENTIAL_KEYS = ("mainStatPer", "subStatPer", "ssubStatPer", "allStatPer", "atkPer", "bossDmg", "damage",
                  "ignoreGuard", "criDmg", "coolTimeReduce")
CUSTOM_KEYS = ("str", "dex", "int", "luk", "att", "bossDmg", "ignoreGuard", "criDmg")
STATS = ("str", "dex", "int", "luk")
ROLES = (("main", "mainStat"), ("sub", "subStat"), ("sub2", "ssubStat"))
# Each IED or final damage value is one source; sources multiply instead of adding up.
STACKED = ("ignoreGuard", "finalDmg")


def number(value, label):
    if value is None or value == "":
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{label} must be a number")
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a number")
    return result


def uses_magic(class_info):
    return class_info.get("main") == "INT"


def stat_field(stat, class_info):
    """STR/DEX/INT/LUK -> mainStat/subStat/ssubStat by class role; stats the class does not use give None."""
    for role, field in ROLES:
        if (class_info.get(role) or "").casefold() == stat:
            return field
    return None


def _scale(key, value):
    """IED: the share of enemy defense left. Final damage: the damage multiplier."""
    if key == "ignoreGuard":
        if value >= 100:
            raise ValueError("IED must be below 100%")
        return 1 - value / 100
    if value <= -100:
        raise ValueError("Final damage must be above -100%")
    return 1 + value / 100


def _percent(key, scale):
    return (1 - scale) * 100 if key == "ignoreGuard" else (scale - 1) * 100


def stack(key, total, value):
    """Add a stat to a running total: two 40% IED sources give 64%, not 80%."""
    if key in STACKED:
        return _percent(key, _scale(key, total) * _scale(key, value))
    return total + value


def replace(key, old, new):
    """The change that turns `old` into `new`: 10% -> 15% IED is one extra 5.556% source, and
    removing x1.10 final damage is -9.091%."""
    if key in STACKED:
        return _percent(key, _scale(key, new) / _scale(key, old))
    return new - old


def remove(key, value):
    """The change that takes away a source worth `value`."""
    return replace(key, value, 0.0)


def _add(result, field, value):
    if field and value:
        result[field] = stack(field, result.get(field, 0.0), value)


def _add_stats(result, flat, class_info):
    """Flat {str, dex, int, luk, att, matt} -> Simulator fields for this class."""
    for stat in STATS:
        _add(result, stat_field(stat, class_info), flat.get(stat, 0))
    _add(result, "atk", flat.get("matt" if uses_magic(class_info) else "att", 0))


def resolve(side, slot):
    """Return (record or None, base, level, cap, weapon_like) for one side of a slot."""
    part = slot.split("_")[0]
    item_id = side.get("item")
    if item_id == "custom":
        base = {k: number(side.get("custom_base", {}).get(k), f"Custom {k}") for k in CUSTOM_KEYS}
        level = side.get("custom_level")
        level = int(number(level, "Custom item level")) if level not in (None, "") else None
        if level is not None and not 1 <= level <= 300:
            raise ValueError("Custom item level must be 1-300")
        cap = _level_cap(level) if level and part not in starforce.EXCLUDED_SLOTS else 0
        return None, base, level, cap, False
    if not item_id:
        return None, {}, None, 0, False
    record = catalog.by_id().get(item_id)
    if record is None or record["slot"] != part:
        raise ValueError(f"Unknown item for {slot}: {item_id}")
    base, cap = dict(record["base"]), record.get("max_stars")
    if record.get("variants"):
        wanted = side.get("variant") or {}
        variant = next(
            (v for v in record["variants"]
             if v["stage"] == wanted.get("stage") and v["version"] == wanted.get("version", 1)),
            None,
        ) if wanted else max(record["variants"], key=lambda v: (v["stage"], -v["version"]))
        if variant is None:
            raise ValueError(f"{record['name']} has no such stage")
        base, cap = dict(variant["base"]), variant["max_stars"]
    if cap is None:
        cap = _level_cap(record["level"]) if record["starforce"] else 0
    if not record["starforce"]:
        cap = 0
    return record, base, record["level"], cap, bool(record.get("weapon_like"))


def _level_cap(level):
    return next(cap for high, cap in starforce.database()["level_caps"] if level <= high)


def _starforce(record, base, level, cap, weapon_like, slot, stars, class_info):
    if stars <= 0:
        return {}
    if stars > cap:
        name = record["name"] if record else "This item"
        raise ValueError(f"{name} can have at most {cap} stars")
    data = starforce.database()
    band = next((b for b in data["bands"] if b["min_level"] <= level <= b["max_level"]), None)
    if band is None:
        raise ValueError("Star Force stat table is unavailable for this item level")
    part = slot.split("_")[0]
    if record is None or part in starforce.SHARED_SLOTS or record["job"] == "common":
        job = "all"
    elif record["classes"] == ["xenon"]:
        # Xenon-only items gain all of Xenon's stats per star.
        job = "all"
    else:
        job = record["job"]
    meta = {
        "level": level,
        "band": band,
        "job": job,
        "kind": "weapon" if weapon_like else "armor",
        "slot": part,
        "base_attack": base.get("att") or None,
        "base_magic_attack": base.get("matt") or None,
        "cap": cap,
    }
    return starforce.gains(meta, 0, stars)


def contribution(class_info, slot, side, parts=None):
    """Simulator-field totals for one item configuration. Upgrades the item cannot have are ignored.

    Pass a dict as `parts` to also receive the totals per source (base, starforce, flame, ...)."""
    record, base, level, cap, weapon_like = resolve(side, slot)
    parts = {} if parts is None else parts
    for name in ("base", "starforce", "flame", "potential", "addons", "other"):
        parts[name] = {}
    flat = {k: base.get(k, 0) for k in ("str", "dex", "int", "luk", "att", "matt")}
    if record is None and side.get("item") == "custom":
        # A custom item's attack box is the class's own ATT or MATT.
        flat["matt" if uses_magic(class_info) else "att"] = base.get("att", 0)
        flat["att" if uses_magic(class_info) else "matt"] = 0
    _add_stats(parts["base"], flat, class_info)
    for key in ("bossDmg", "ignoreGuard", "criDmg", "finalDmg"):
        _add(parts["base"], key, base.get(key, 0))
    if not (record and record.get("unmodifiable")):
        _upgrades(parts, record, base, level, cap, weapon_like, class_info, slot, side)
    result = {}
    for name, values in list(parts.items()):
        parts[name] = _clean(values)
        for key, value in values.items():
            _add(result, key, value)
    return _clean(result)


def _upgrades(parts, record, base, level, cap, weapon_like, class_info, slot, side):
    flame_ok = record["flame"] if record else side.get("item") == "custom"
    potential_ok = record["potential"] if record else side.get("item") == "custom"
    flame = side.get("flame") or {}
    if flame_ok:
        _add_stats(parts["flame"], {k: number(flame.get(k), f"Flame {k.upper()}") for k in STATS + ("att", "matt")},
                   class_info)
        _add(parts["flame"], "allStatPer", number(flame.get("allStatPer"), "Flame all stats %"))
    potential = side.get("potential") or {}
    if potential_ok:
        for key in POTENTIAL_KEYS:
            value = number(potential.get(key), f"Potential {key}")
            _add(parts["potential"], "bossDmg" if key == "damage" else key, value)
    stars = number(side.get("stars"), "Stars")
    if stars != int(stars) or stars < 0:
        raise ValueError("Stars must be a whole number of 0 or more")
    stars = int(stars)
    if stars and record is None and not level:
        raise ValueError("Enter the custom item's level to count its Star Force")
    if stars and not cap:
        raise ValueError(f"{record['name'] if record else 'This item'} cannot be Star Forced")
    if stars:
        gains = _starforce(record, base, level, cap, weapon_like, slot, stars, class_info)
        _add_stats(parts["starforce"], {
            "str": gains.get("STR", 0), "dex": gains.get("DEX", 0), "int": gains.get("INT", 0),
            "luk": gains.get("LUK", 0), "att": gains.get("Attack Power", 0), "matt": gains.get("Magic Attack", 0),
        }, class_info)
    for addon in (record or {}).get("addons", []):
        count = number((side.get("addons") or {}).get(addon["id"]), addon["label"])
        if count != int(count) or not 0 <= count <= addon["max"]:
            raise ValueError(f"{addon['label']} must be a whole number from 0 to {addon['max']}")
        allstat = addon["per"].get("allstat", 0) * count
        attack = addon["per"].get("att", 0) * count
        _add_stats(parts["addons"], {**dict.fromkeys(STATS, allstat), "att": attack, "matt": attack}, class_info)
        for _ in range(int(count)):
            _add(parts["addons"], "finalDmg", addon["per"].get("finalDmg", 0))
    allowed = {f["key"]: f for f in simulator_fields()}
    for key, value in (side.get("other") or {}).items():
        if key not in allowed:
            raise ValueError(f"Unsupported bonus field: {key}")
        _add(parts["other"], key, number(value, allowed[key]["label"]))


def _clean(result):
    return {k: round(v, 6) for k, v in result.items() if round(v, 6)}
