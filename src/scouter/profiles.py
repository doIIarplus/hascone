"""Versioned character inputs shared by manual edits and scans."""

import copy
import hashlib
import json
import math
import os
import re
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scouter.boss_cuts import with_boss_cuts
from utils.payload_data import read_payload_json

DIRECTORY = Path("configs/scouter_profiles")
lock = threading.RLock()
AUTO_STATS = [
    "level",
    "mainStatBase",
    "mainStatPer",
    "mainStatAbs",
    "subStatBase",
    "subStatPer",
    "subStatAbs",
    "ssubStatBase",
    "ssubStatPer",
    "ssubStatAbs",
    "atkBase",
    "atkPercent",
    "weaponAtk",
    "dmg",
    "bossDmg",
    "normalDmg",
    "ignoreDef",
    "critical",
    "criticalDmg",
    "coolTimeReduce",
    "coolTimeReducePercent",
    "buffDuration",
    "resetCoolDown",
    "ignoreElementalResist",
    "statusAdditionalDmg",
    "summonPersistTime",
    "arcaneForce",
    "authenticForce",
    "maple_combatPower",
]
FIXED = {"stat.myClass", "special.isReboot", "special.genesis", "isGMS", "isTMS", "isJMS", "isMSEA"}
HEXA_INPUTS = (
    "masteryCore1",
    "masteryCore2",
    "masteryCore3",
    "masteryCore4",
    "skillCore1",
    "skillCore2",
    "skillCore3",
    "reinCore1",
    "reinCore2",
    "reinCore3",
    "reinCore4",
    "generalCore2",
    "generalCore3",
)


def input_paths(info):
    """Editable numeric controls on the GMS manual form, including class conditions."""
    stats = set(AUTO_STATS) - {"weaponAtk", "normalDmg", "maple_combatPower"}
    stats.update(("atkAbs", "wildhunterUnion", "artifact_finalAttack"))
    if not info["sub2"]:
        stats.difference_update(("ssubStatBase", "ssubStatPer", "ssubStatAbs"))
    if info["name"] == "Zero":
        stats.add("classForce")
    paths = {f"stat.{key}" for key in stats}
    paths.add("hexa.hexaStat")
    paths.update(f"hexa.{key}" for key in HEXA_INPUTS if info["cores"].get(key, {}).get("url"))
    paths.update(
        f"doping.{key}"
        for key in (
            "stat",
            "championAll",
            "championAtk",
            "championBoss",
            "championCriDmg",
            "championIgnore",
            "nobless.0",
            "nobless.1",
            "nobless.2",
            "nobless.3",
        )
    )
    paths.update(
        f"linkSkill.{key}"
        for key in (
            "kadena",
            "illium",
            "ark",
            "kain",
            "magician",
            "thief",
            "angel",
            "kanna",
            "mukhyun",
            "hoyoung",
        )
    )
    if info["name"] in ("Mihile", "Kaiser"):
        paths.add(f"linkSkill.{info['name'].lower()}")
    paths.update(f"special.{key}" for key in ("restraintRing", "weaponRing", "continuosRing", "mugongSoul"))
    if info["name"] == "Demon Avenger":
        paths.add("special.epiSoul")
    paths.update(("huntSkill.erdaShower", "huntSkill.solJanus"))
    return paths


def now():
    return datetime.now(UTC).isoformat()


def flatten(value, prefix=""):
    result = {}
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            result.update(flatten(child, path))
        elif isinstance(child, list):
            result.update({f"{path}.{i}": v for i, v in enumerate(child)})
        else:
            result[path] = child
    return result


def assign(value, path, item):
    parts = path.split(".")
    for part in parts[:-1]:
        value = value[int(part)] if isinstance(value, list) else value[part]
    value[int(parts[-1]) if isinstance(value, list) else parts[-1]] = item


def class_info(name):
    normalized = re.sub("[^a-z]", "", name.lower())
    aliases = {"firepoisonmage": "firepoison", "icelightningmage": "icelightning"}
    normalized = aliases.get(normalized, normalized)
    for row in read_payload_json("src/scouter/data/classes.json"):
        if re.sub("[^a-z]", "", row["name"].lower()) == normalized:
            if row["slug"] in ("sia_astelle", "erel_light"):
                row = copy.deepcopy(row)
                row["shine"] = True
                # The bundled upstream labels still include placeholder cores
                # and Freud's Protection for SHINE. GMS uses Tree of Stars.
                for key in ("masteryCore3", "masteryCore4"):
                    row["cores"][key]["url"] = ""
                row["cores"]["generalCore3"].update(
                    english_title="SHINE Tree of Stars", url="/assets/hexaskill/SHINE_tree.png",
                )
            return row
    raise ValueError(f"MapleScouter does not have a class mapping for {name}")


def identity(identifier):
    from flaming import characters

    characters.portrait_path(identifier)
    path = characters.PROFILE_DIR / f"{identifier}.json"
    if not path.exists():
        raise ValueError("Select an existing character profile")
    source = json.loads(path.read_text(encoding="utf-8"))
    character = {"id": identifier, "name": source["name"], "class": source["class"]}
    return character


def defaults(info):
    data = read_payload_json("src/scouter/data/defaults.json")
    data["stat"]["myClass"] = info["key"]
    visible = input_paths(info)
    for key in AUTO_STATS:
        data["stat"][key] = None if f"stat.{key}" in visible else "0"
    data["entireStat"] = dict.fromkeys(data["entireStat"], "0")
    if not info["sub2"]:
        for key in ("ssubStatBase", "ssubStatPer", "ssubStatAbs"):
            data["stat"][key] = "0"
    for key, core in info["cores"].items():
        if core.get("url") and f"hexa.{key}" in visible:
            data["hexa"][key] = None
    return data


def load(identifier):
    character = identity(identifier)
    info = class_info(character["class"])
    path = DIRECTORY / f"{identifier}.json"
    with lock:
        data: dict[str, Any] = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {
                "version": 2,
                "scanned": {},
                "inputs": {},
                "scan": None,
                "history": [],
                "revision": 0,
            }
        )
    if data.get("version", 1) < 2:
        # Preserve the values users currently see, then retire the priority layer.
        data["inputs"] = {p: r["value"] for p, r in data.get("scanned", {}).items()}
        data["inputs"].update(data.pop("overrides", {}))
        data["version"] = 2
    data["character"] = character
    data["class_info"] = info
    if data.get("class_key", info["key"]) != info["key"]:
        raise ValueError("Character class changed; archive its Scouter profile before rescanning")
    data["class_key"] = info["key"]
    return data


def write(identifier, data):
    identity(identifier)
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in data.items() if k not in ("character", "class_info")}
    fd, temporary = tempfile.mkstemp(dir=DIRECTORY, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2, allow_nan=False)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, DIRECTORY / f"{identifier}.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def effective(data):
    value = defaults(data["class_info"])
    allowed = flatten(value)
    for path, item in data["inputs"].items():
        if path in allowed and path not in FIXED:
            assign(value, path, item)
    # Legacy editors could clear internal API values. Retain saved records, but
    # don't require an invisible field to calculate from the website's form.
    visible = input_paths(data["class_info"])
    for path, item in flatten(value).items():
        if item is None and path not in visible:
            assign(value, path, "0")
    if data["class_info"].get("shine"):
        # Retain old saved records, but never send the upstream placeholder
        # mastery slots as real SHINE skills.
        value["hexa"]["masteryCore3"] = value["hexa"]["masteryCore4"] = "0"
    return value


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def snapshot(identifier):
    data = load(identifier)
    values = effective(data)
    from starforce.cost import options

    data["starforce_options"] = options(data.get("starforce_options"))
    data["values"] = values
    data["defaults"] = defaults(data["class_info"])
    from scouter.simulator import fields

    data["simulator_fields"] = fields()
    data["missing"] = sorted(p for p in input_paths(data["class_info"]) if flatten(values)[p] is None)
    data["history"] = [{k: v for k, v in with_boss_cuts(r).items() if k != "input"} for r in data["history"]]
    data["fingerprint"] = fingerprint(values)
    from flaming import characters

    try:
        gear = characters.load(identifier)
        from scouter.suggestions import signature

        data["gear_fingerprint"] = signature(gear)
    except (OSError, ValueError, KeyError, TypeError):
        data["gear_fingerprint"] = None
    return data


class RevisionConflict(ValueError):
    pass


def _validate_numeric_range(path, number):
    maximum = 3 if path == "hexa.hexaStat" else 30 if path.startswith("hexa.") else 1e13
    if not math.isfinite(number) or number > maximum:
        raise ValueError(f"{path} is outside its allowed range")
    if path.startswith("hexa.") and not number.is_integer():
        raise ValueError("HEXA levels must be whole numbers")
    if path == "stat.ignoreDef" and number >= 100:
        raise ValueError("Ignore defense must be below 100%")
    if path == "stat.level" and not 1 <= number <= 300:
        raise ValueError("Character level must be 1–300")


def _clean_input_value(path, value, allowed, class_info):
    if path not in allowed or path in FIXED or path.startswith(("power.", "seedRing.")):
        raise ValueError(f"Unsupported input: {path}")
    if type(allowed[path]) is bool:
        if type(value) is not bool:
            raise ValueError(f"{path} must be a checkbox")
        return value
    if value is None:
        return None
    if path == "special.epiSoul" and value == "C" and class_info["name"] == "Demon Avenger":
        return value
    if isinstance(value, bool) or not re.fullmatch(r"\d+(?:\.\d+)?", str(value)):
        raise ValueError(f"{path} must be a nonnegative number")
    number = float(value)
    _validate_numeric_range(path, number)
    return int(number) if path == "hexa.hexaStat" else str(value)


def save_inputs(identifier, body):
    if (
        not isinstance(body, dict)
        or set(body) != {"revision", "changes"}
        or not isinstance(body["changes"], dict)
    ):
        raise ValueError("Invalid Scouter inputs")
    with lock:
        data = load(identifier)
        if body["revision"] != data["revision"]:
            raise RevisionConflict("Scouter inputs changed. Refresh before saving your edits.")
        allowed = flatten(defaults(data["class_info"]))
        cleaned: dict[str, Any] = {
            path: _clean_input_value(path, value, allowed, data["class_info"])
            for path, value in body["changes"].items()
        }
        data["inputs"].update(cleaned)
        for path in cleaned:
            data["scanned"].pop(path, None)
            data.setdefault("manual_versions", {})[path] = data["revision"] + 1
        data["revision"] += 1
        write(identifier, data)
    return snapshot(identifier)


def save_scan(identifier, readings, errors, started, *, links=None, shine=None):
    with lock:
        data = load(identifier)
        # A scan fills the fields it actually read, exactly like manual entry.
        # Unread fields stay untouched; scan errors remain visible to the user.
        allowed = flatten(defaults(data["class_info"]))
        data["scanned"] = {p: r for p, r in readings.items() if p in allowed and p not in FIXED}
        data["inputs"].update({p: r["value"] for p, r in data["scanned"].items()})
        data["scan"] = {"started": started, "finished": now(), "errors": errors, "links": links or []}
        if shine is not None:
            data["shine_levels"] = shine
        data["revision"] += 1
        write(identifier, data)


def payload(data):
    user = effective(data)
    missing = [p for p, v in flatten(user).items() if v is None]
    if missing:
        raise ValueError("Review missing inputs before calculating: " + ", ".join(missing))
    if not 1 <= float(user["stat"]["level"]) <= 300:
        raise ValueError("Enter a valid character level")
    if float(user["stat"]["ignoreDef"]) >= 100:
        raise ValueError("Ignore defense must be below 100%")
    # Mirror the public input form's ring levels in its calculated ring records.
    for source, target in {
        "restraintRing": "restraintRing",
        "weaponRing": "weaponRing",
        "continuosRing": "continuosRing",
        "ringOfSum": "ringOfSum",
        "riskTaker": "riskTakerRing",
    }.items():
        user["seedRing"][target]["level"] = user["special"][source]
    return copy.deepcopy(user)


def save_starforce_options(identifier, body):
    from starforce.cost import options

    if not isinstance(body, dict):
        raise ValueError("Expected Star Force options")
    cleaned = options(body)
    with lock:
        data = load(identifier)
        data["starforce_options"] = cleaned
        write(identifier, data)
    return snapshot(identifier)
