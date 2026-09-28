"""Shared potential-equivalent weights. All Stat is derived from class roles."""

import copy
import hashlib
import json
import math
import os
import tempfile
import threading
from pathlib import Path

from flaming.profiles import classes
from utils.payload_data import read_payload_json

SETTINGS_PATH = Path("configs/cube_weights.json")
_lock = threading.RLock()
FIELDS = {"secondary_weight", "boss_per_attack"}


def validate(data):
    if (
        not isinstance(data, dict)
        or set(data) != {"version", "defaults", "overrides"}
        or type(data["version"]) is not int
        or data["version"] != 1
    ):
        raise ValueError("Provide global defaults and optional class overrides")
    roles = classes()
    if (
        not isinstance(data["defaults"], dict)
        or set(data["defaults"]) != FIELDS
        or not isinstance(data["overrides"], dict)
        or set(data["overrides"]) - roles.keys()
    ):
        raise ValueError("Invalid class scoring settings")
    for group in [data["defaults"], *data["overrides"].values()]:
        if not isinstance(group, dict) or set(group) - FIELDS:
            raise ValueError(
                "Edit secondary weight and Boss Damage ratio; All Stat is calculated"
            )
        for key, value in group.items():
            low, high = (0, 10) if key == "secondary_weight" else (0.000001, 1000)
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{key} must be between {low} and {high}")
    for job, role in roles.items():
        if _effective(job, role, data)["all_stat_weight"] > 10:
            raise ValueError(f"Derived All Stat weight for {job} must be at most 10")
    return copy.deepcopy(data)


def settings():
    with _lock:
        return validate(
            json.loads(SETTINGS_PATH.read_text())
            if SETTINGS_PATH.exists()
            else read_payload_json("src/cubing/data/weights.json")
        )


def effective(job, data=None):
    roles = classes()
    if not isinstance(job, str) or job not in roles:
        raise ValueError("Choose a supported character class")
    data = settings() if data is None else data
    return _effective(job, roles[job], data)


def _effective(job, role, data):
    values = {**data["defaults"], **data["overrides"].get(job, {})}
    all_stat = round(
        sum(s != "Max HP" for s in role["main_stats"])
        + values["secondary_weight"] * sum(s != "Max HP" for s in role["secondary_stats"]),
        10,
    )
    return {**values, "all_stat_weight": all_stat}


def score(job, data=None):
    values = effective(job, data)
    return {
        "class": job,
        "secondary_weight": values["secondary_weight"],
        "all_stat_weight": values["all_stat_weight"],
    }


def attack_score(job, data=None):
    return {"boss_per_attack": effective(job, data)["boss_per_attack"]}


def revision(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def catalog():
    data = settings()
    return {
        **data,
        "revision": revision(data),
        "effective": {job: _effective(job, role, data) for job, role in classes().items()},
    }


def save(data, expected_revision):
    clean = validate(data)
    with _lock:
        if expected_revision != revision(settings()):
            raise ValueError("Class settings changed. Reload before saving.")
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".cube-weights-", dir=SETTINGS_PATH.parent)
        try:
            with os.fdopen(fd, "w") as out:
                json.dump(clean, out, indent=2)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, SETTINGS_PATH)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return catalog()
