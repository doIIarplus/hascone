"""Class roles and global/per-class scoring weights."""

import threading
from typing import Any

from utils.payload_data import read_payload_json

CLASSES_PATH = "src/flaming_data/classes.json"
WEIGHTS_PATH = "src/flaming_data/weights.json"
ROLES = ("primary", "secondary", "attack", "all_stat", "damage_boss")
STATS = (
    "STR",
    "DEX",
    "INT",
    "LUK",
    "Max HP",
    "Attack Power",
    "Magic Attack",
    "All Stats",
    "Damage",
    "Boss Damage",
)
_lock = threading.RLock()


def classes():
    rows = read_payload_json(CLASSES_PATH)
    result = {}
    for row in rows:
        if (
            set(row) != {"class", "main_stats", "secondary_stats", "att"}
            or row["class"] in result
            or row["att"] not in ("ATT", "MATT")
            or not row["main_stats"]
        ):
            raise ValueError("Invalid Flame Score class definition")
        primary, secondary = row["main_stats"], row["secondary_stats"]
        if (
            not isinstance(primary, list)
            or not isinstance(secondary, list)
            or len(set(primary + secondary)) != len(primary + secondary)
            or set(primary + secondary) - {"STR", "DEX", "INT", "LUK", "Max HP"}
        ):
            raise ValueError("Invalid main/secondary stats in Flame Score class definition")
        result[row["class"]] = row
    return result


def validate_weights(data) -> dict[str, Any]:
    from flaming.score import decimal_value

    if not isinstance(data, dict) or set(data) != {"defaults", "overrides"}:
        raise ValueError("Provide global defaults and per-class overrides")
    defaults, overrides = data["defaults"], data["overrides"]
    if not isinstance(defaults, dict) or set(defaults) != set(ROLES) or not isinstance(overrides, dict):
        raise ValueError("Invalid Flame Score weight roles")

    def values(group):
        if not isinstance(group, dict) or set(group) - set(ROLES):
            raise ValueError("Only weight values can be overridden; class stats are fixed")
        return {key: str(decimal_value(value, key + " weight", 1000000)) for key, value in group.items()}

    if set(overrides) - classes().keys():
        raise ValueError("Unknown class override")
    return {
        "defaults": values(defaults),
        "overrides": {name: values(group) for name, group in overrides.items()},
    }


def settings():
    return validate_weights(read_payload_json(WEIGHTS_PATH))


def role_weights(class_name, data=None):
    data = settings() if data is None else data
    if not isinstance(class_name, str) or class_name not in classes():
        raise ValueError("Select a supported Flame Score class")
    return {**data["defaults"], **data["overrides"].get(class_name, {})}


def stat_weights(class_name, roles=None):
    if not isinstance(class_name, str):
        raise ValueError("Select a supported Flame Score class")
    profile = classes().get(class_name)
    if profile is None:
        raise ValueError("Select a supported Flame Score class")
    roles = role_weights(class_name) if roles is None else roles
    weights = dict.fromkeys(STATS, "0")
    for name in profile["main_stats"]:
        weights[name] = str(roles["primary"])
    for name in profile["secondary_stats"]:
        weights[name] = str(roles["secondary"])
    weights["Attack Power" if profile["att"] == "ATT" else "Magic Attack"] = str(roles["attack"])
    weights["All Stats"] = str(roles["all_stat"])
    weights["Damage"] = weights["Boss Damage"] = str(roles["damage_boss"])
    return weights
