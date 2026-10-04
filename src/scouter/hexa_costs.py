"""Sol Erda Fragments invested in a character's saved HEXA or Erda Link levels."""

from functools import lru_cache

from utils.payload_data import read_payload_json

# Scouter input -> cost table. Sol Janus is saved as a hunting skill.
NODES = {
    "hexa.skillCore1": "origin",
    "hexa.skillCore2": "ascent",
    "hexa.masteryCore1": "mastery",
    "hexa.masteryCore2": "mastery",
    "hexa.masteryCore3": "mastery",
    "hexa.masteryCore4": "mastery",
    "hexa.reinCore1": "enhancement",
    "hexa.reinCore2": "enhancement",
    "hexa.reinCore3": "enhancement",
    "hexa.reinCore4": "enhancement",
    "hexa.generalCore2": "common",
    "hexa.generalCore3": "third_common",
    "huntSkill.solJanus": "common",
}

# Erda Link (Sia Astelle, Erel Light) levels the same skills with stones; only
# its Origin and Ultimate Stones cost differently from the HEXA nodes.
ERDA_LINK_NODES = {**NODES, "hexa.skillCore1": "erda_origin", "hexa.masteryCore1": "ultimate", "hexa.masteryCore2": "ultimate"}
# Boost skills levelled by two 15-level half Skill Stones, whose levels add up.
HALF_STONES = {
    "sia_astelle": {"hexa.reinCore1", "hexa.reinCore3", "hexa.reinCore4"},
    "erel_light": {"hexa.reinCore2", "hexa.reinCore3", "hexa.reinCore4"},
}


@lru_cache(maxsize=1)
def tables():
    return read_payload_json("src/scouter/data/hexa_costs.json")


def spent(table, level):
    """Fragments to reach LEVEL; each table lists the cost to reach levels 1 to 30."""
    return sum(tables()["nodes"][table][:level])


def split_spent(level):
    """Fewest fragments for two half stones to reach LEVEL together. Their
    costs per level are uneven, so the cheapest split can leave both part-way."""
    level = min(level, 30)
    return min(spent("half_stone", a) + spent("half_stone", level - a) for a in range(max(0, level - 15), min(level, 15) + 1))


def fragments(values, class_info):
    """Fragments invested in the saved HEXA levels.

    VALUES are flattened Scouter inputs. Returns (total, partial, minimum):
    total is None before any level is known. partial means some nodes are
    unread. minimum means completed HEXA Stat cores count at their guaranteed
    cost, since their level-ups cost more when the main stat rolls; Erda Link
    totals are always a minimum, as Rush, Boost and SHINE Stones have no skill
    level to read and SHINE Stone enhancements can fail."""
    shine = class_info.get("shine")
    halves = HALF_STONES[class_info["slug"]] if shine else ()
    total, known, partial = 0, False, False
    for path, table in (ERDA_LINK_NODES if shine else NODES).items():
        key = path.split(".", 1)[1]
        if path.startswith("hexa.") and not (class_info["cores"].get(key) or {}).get("url"):
            continue
        value = values.get(path)
        if value is None:
            partial = True
            continue
        known = True
        level = int(float(value))
        total += split_spent(level) if path in halves else spent(table, level)
    if shine:
        return (total if known else None), partial, known
    completed = int(values.get("hexa.hexaStat") or 0)
    stat = tables()["stat"]
    total += sum(stat["unlock"][:completed]) + completed * stat["min_levels"]
    return (total if known else None), partial, completed > 0
