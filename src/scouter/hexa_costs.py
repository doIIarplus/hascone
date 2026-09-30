"""Sol Erda Fragments invested in a character's saved HEXA levels."""

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


@lru_cache(maxsize=1)
def tables():
    return read_payload_json("src/scouter/data/hexa_costs.json")


def spent(table, level):
    """Fragments to reach LEVEL; each table lists the cost to reach levels 1 to 30."""
    return sum(tables()["nodes"][table][:level])


def fragments(values, class_info):
    """Fragments invested in the saved HEXA levels.

    VALUES are flattened Scouter inputs. Returns (total, partial, minimum):
    total is None before any level is known or for Erda Link classes, whose
    SHINE Stones have no fixed cost. partial means some nodes are unread;
    minimum means completed HEXA Stat cores count at their guaranteed cost,
    since their level-ups cost more when the main stat rolls."""
    if class_info.get("shine"):
        return None, False, False
    total, known, partial = 0, False, False
    for path, table in NODES.items():
        key = path.split(".", 1)[1]
        if path.startswith("hexa.") and not (class_info["cores"].get(key) or {}).get("url"):
            continue
        value = values.get(path)
        if value is None:
            partial = True
            continue
        known = True
        total += spent(table, int(float(value)))
    completed = int(values.get("hexa.hexaStat") or 0)
    stat = tables()["stat"]
    total += sum(stat["unlock"][:completed]) + completed * stat["min_levels"]
    return (total if known else None), partial, completed > 0
