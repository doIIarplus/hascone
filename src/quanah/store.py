"""The saved Quanah class, build and event pieces, plus the solved best set.

One global list, independent of Hascone's characters. Pieces of another class
are kept, flagged as unwearable and left out of the solver.
"""

import json
import os
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from quanah import solver
from quanah.lines import rematch

PATH = Path("configs/quanah.json")
lock = threading.RLock()


def _default():
    gandi = next(b for b in solver.catalog()["builds"] if b["key"] == "gandi")
    return {
        "class": None,
        "build": {"preset": "skill", "job_mode": "custom", "jobs": list(gandi["jobs"]["default"]), "targets": {}},
        "items": [],
    }


def read():
    with lock:
        data = _default()
        if PATH.exists():
            saved = json.loads(PATH.read_text(encoding="utf-8"))
            data["class"] = saved.get("class")
            data["build"].update(saved.get("build") or {})
            # The Skill build was first saved as "original".
            if data["build"].get("preset") == "original":
                data["build"]["preset"] = "skill"
            # So the page shows, and later changes validate, the same targets the solver uses.
            data["build"]["targets"] = solver.trim_targets(data["build"].get("targets"))
            data["items"] = saved.get("items") or []
            # Re-match scanned pieces from the text the scanner read, so catalog fixes reach
            # pieces already saved. A piece the player edited keeps their lines.
            for item in data["items"]:
                if item.get("source") == "scan" and not item.get("edited"):
                    item["lines"] = rematch(item.get("raw")) or item["lines"]
        return data


def _write(data):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=PATH.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        os.replace(name, PATH)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _class_keys():
    return [c["key"] for c in solver.catalog()["classes"]]


def configure(class_key=None, build=None):
    """Save the player's class and/or build choice."""
    with lock:
        data = read()
        if class_key is not None:
            if class_key not in _class_keys():
                raise ValueError("Choose Warrior, Magician, Bowman, Thief or Pirate")
            data["class"] = class_key
        if build is not None:
            data["build"] = _clean_build({**data["build"], **build})
        _write(data)
        return data


def _clean_build(build):
    presets = [b["key"] for b in solver.catalog()["builds"]]
    if build.get("preset") not in presets:
        raise ValueError("Unknown build")
    if build.get("job_mode") not in ("custom", "any"):
        raise ValueError("Unknown job mode")
    jobs = build.get("jobs") or []
    if not isinstance(jobs, list) or set(jobs) - set(solver.job_keys()) or len(set(jobs)) != len(jobs) or len(jobs) > 3:
        raise ValueError("Choose up to 3 different jobs")
    targets = build.get("targets") or {}
    cap = solver.catalog()["max_per_line"]
    if not isinstance(targets, dict) or set(targets) - set(solver.line_keys()):
        raise ValueError("Unknown custom line")
    cleaned = {}
    for key, value in targets.items():
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= cap:
            raise ValueError(f"Each line target must be 0 to {cap}")
        if value:
            cleaned[key] = value
    goal = solver.catalog()["goal"]
    if sum(cleaned.values()) > goal:
        raise ValueError(f"Six pieces hold at most {goal} lines")
    return {"preset": build["preset"], "job_mode": build["job_mode"], "jobs": jobs, "targets": cleaned}


def validate_lines(lines):
    """1–3 known lines, no line twice (unrecognized "other" lines may repeat)."""
    if not isinstance(lines, list) or not 1 <= len(lines) <= solver.catalog()["max_lines"]:
        raise ValueError("A piece has 1 to 3 lines")
    if any(key not in solver.line_keys() and key != solver.OTHER for key in lines):
        raise ValueError("Unknown line")
    real = [key for key in lines if key != solver.OTHER]
    if len(set(real)) != len(real):
        raise ValueError("A piece cannot roll the same line twice")
    return list(lines)


def add_item(slot, lines, *, raw=None, name=None, item_class=None, source="manual"):
    if slot not in solver.slot_keys():
        raise ValueError("Choose a slot")
    lines = validate_lines(lines)
    if item_class is not None and item_class not in _class_keys():
        raise ValueError("Unknown item class")
    with lock:
        data = read()
        if not data["class"]:
            raise ValueError("Choose your class first")
        item = {
            "id": uuid.uuid4().hex,
            "slot": slot,
            "lines": lines,
            "raw": list(raw) if raw else None,
            "name": name,
            # A manual piece is one the player says they can wear.
            "item_class": item_class or data["class"],
            "source": source,
            "added": datetime.now(UTC).isoformat(),
        }
        data["items"].append(item)
        _write(data)
        return item


def update_item(identifier, slot, lines):
    """Correct a piece's slot and lines by hand. A scanned piece keeps what was read, marked edited."""
    if slot not in solver.slot_keys():
        raise ValueError("Choose a slot")
    lines = validate_lines(lines)
    with lock:
        data = read()
        item = next((i for i in data["items"] if i["id"] == identifier), None)
        if item is None:
            raise ValueError("That piece is already gone")
        if (item["slot"], item["lines"]) != (slot, lines):
            item.update(slot=slot, lines=lines, edited=datetime.now(UTC).isoformat())
            _write(data)
        return item


def delete_item(identifier):
    with lock:
        data = read()
        kept = [item for item in data["items"] if item["id"] != identifier]
        if len(kept) == len(data["items"]):
            raise ValueError("That piece is already gone")
        data["items"] = kept
        _write(data)


def clear_items():
    with lock:
        data = read()
        data["items"] = []
        _write(data)


def duplicates(items):
    """Ids of pieces sharing a slot and the same lines in any order."""
    groups = {}
    for item in items:
        groups.setdefault((item["slot"], tuple(sorted(item["lines"]))), []).append(item["id"])
    return {i for ids in groups.values() if len(ids) > 1 for i in ids}


def payload():
    """Everything the page needs: catalog, settings, flagged pieces and the best set."""
    data = read()
    dupes = duplicates(data["items"])
    items = [{**item, "duplicate": item["id"] in dupes,
              "wearable": bool(data["class"]) and item.get("item_class") == data["class"]}
             for item in data["items"]]
    solution = None
    if data["class"]:
        targets, jobs = solver.resolve_build(data["build"])
        solution = solver.solve([i for i in items if i["wearable"]], targets, jobs)
        solution["targets"] = targets
        solution["jobs"] = {"count": jobs[0], "keys": list(jobs[1])} if jobs else None
    return {"catalog": solver.catalog(), "class": data["class"], "build": data["build"],
            "items": items, "solution": solution}
