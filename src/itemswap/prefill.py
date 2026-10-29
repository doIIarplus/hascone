"""Turn a scanned equipment slot into an editable Item swap configuration."""

import re

from cubing.lines import parse_line
from flaming.stats import ReadError
from itemswap import catalog
from itemswap.contribution import stack, stat_field, uses_magic

FLAME_NAMES = {"STR": "str", "DEX": "dex", "INT": "int", "LUK": "luk", "Attack Power": "att", "Magic Attack": "matt"}
ROLE_PERCENT = {"mainStat": "mainStatPer", "subStat": "subStatPer", "ssubStat": "ssubStatPer"}
# parse_line files "Damage +9%" under junk; it counts here (folded into boss damage).
DAMAGE = re.compile(r"\s*DAMAGE\s*:?\s*\+?\s*(\d+(?:\.\d+)?)\s*%\s*", re.I)


def _total(values, key, amount):
    if amount:
        values[key] = stack(key, values.get(key, 0), amount)


def potential(lines, class_info):
    """Sum scanned potential lines into the aggregate boxes. Unknown lines are reported, not guessed."""
    values, unknown = {}, []
    magic = uses_magic(class_info)
    for line in lines or []:
        damage = DAMAGE.fullmatch(line or "")
        if damage:
            _total(values, "damage", float(damage[1]))
            continue
        try:
            label, amount = parse_line(line)
        except ReadError:
            unknown.append(line)
            continue
        stat = label.removesuffix(" %").casefold()
        if label in ("STR %", "DEX %", "INT %", "LUK %"):
            field = stat_field(stat, class_info)
            if field:
                _total(values, ROLE_PERCENT[field], amount)
        elif label == "All Stats %":
            _total(values, "allStatPer", amount)
        elif label == ("MATT %" if magic else "ATT %"):
            _total(values, "atkPer", amount)
        elif label == "Boss Damage":
            _total(values, "bossDmg", amount)
        elif label == "Ignore Enemy Defense %":
            _total(values, "ignoreGuard", amount)
        elif label == "Critical Damage %":
            _total(values, "criDmg", amount)
        elif label == "Skill Cooldown Reduction":
            _total(values, "coolTimeReduce", amount)
    return {k: _number(v) for k, v in values.items()}, unknown


def flame(stats):
    values = {}
    for stat in stats or []:
        name = stat.get("name")
        if name in FLAME_NAMES and not stat.get("percent"):
            _total(values, FLAME_NAMES[name], stat.get("value") or 0)
        elif name == "All Stats" and stat.get("percent"):
            _total(values, "allStatPer", stat.get("value") or 0)
    return {k: _number(v) for k, v in values.items()}


def _number(value):
    value = round(value, 6)
    return int(value) if float(value).is_integer() else value


def side(slot, item, class_info):
    """The current-item side for one scanned slot, plus notes for the UI."""
    item = item or {}
    name = item.get("name")
    notes = []
    if not name:
        return {"item": None, "scanned_name": None}, notes
    record = catalog.match(name, slot, class_info)
    stars = (item.get("starforce") or {}).get("stars") if (item.get("starforce") or {}).get("status") == "scanned" else 0
    result = {"item": record["id"] if record else "custom", "scanned_name": name, "stars": stars or 0}
    if record is None:
        result.update(unlisted=True, custom_base={}, custom_level=item.get("required_level"))
        notes.append(f"{name} is not in the item list. Enter its base stats.")
    elif record.get("variants"):
        cap = (item.get("starforce") or {}).get("max_stars")
        first = [v for v in record["variants"] if v["version"] == 1]
        versions = {v["version"] for v in record["variants"]}
        # The star limit identifies the stage only when every stage has its own limit (Talisman: 30 for all).
        caps = [v["max_stars"] for v in first]
        stage = dict(zip(caps, (v["stage"] for v in first))).get(cap) if len(set(caps)) == len(caps) else None
        result["variant"] = {"stage": stage or 3, "version": 1}
        result["pick_variant"] = True
        notes.append("Pick the stage" + (" and version" if len(versions) > 1 else "")
                     + " of your Astra item; the scan cannot read it" + (f" (its star limit suggests stage {stage})"
                                                                          if stage else "") + ".")
    if record is None or record["flame"]:
        result["flame"] = flame(item.get("stats"))
    if record is None or record["potential"]:
        values, unknown = potential((item.get("potential") or {}).get("lines"), class_info)
        result["potential"] = values
        if unknown:
            notes.append("Not counted: " + ", ".join(unknown))
    return result, notes
