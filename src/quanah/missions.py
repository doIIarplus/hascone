"""Dimensional mission progress: which missions are complete, their points and the grade.

One global list, like the Quanah pieces. Missions sit in ordered chains (inspector
levels, Battlesim floors, each boss's difficulties, star force levels): completing a
mission completes every one before it in its chain, and undoing one undoes every
one after it, so a chain never has gaps. Round missions reset when the character
dies; permanent missions are kept.
"""

import json
import os
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

from utils.payload_data import read_payload_json

PATH = Path("configs/quanah_missions.json")


def _backup_path():
    """Where a damaged save is kept; follows PATH, which tests move."""
    return PATH.with_suffix(".damaged.json")

lock = threading.RLock()


@lru_cache(maxsize=1)
def catalog():
    return read_payload_json("src/quanah/data/missions.json")


@lru_cache(maxsize=1)
def _index():
    """Each mission id -> (group type, its chain's ids in order, its place in the chain)."""
    index = {}
    for group in catalog()["groups"]:
        for chain in group["chains"]:
            ids = [m["id"] for m in chain["missions"]]
            for place, identifier in enumerate(ids):
                index[identifier] = (group["type"], ids, place)
    return index


def _points():
    return {m["id"]: m["points"] for g in catalog()["groups"] for c in g["chains"] for m in c["missions"]}


def read():
    """The ids of completed missions, in catalog order; unknown ids are dropped."""
    with lock:
        if not PATH.exists():
            return []
        # A file that can't be opened right now (e.g. held by antivirus) raises, so the request
        # fails rather than saving over real progress.
        text = PATH.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if not (isinstance(data, dict) and isinstance(data.get("done"), list)):
            # Damaged: keep a copy to recover from, then start over instead of failing every request.
            _backup_path().write_text(text, encoding="utf-8")
            PATH.unlink()
            return []
        done = {i for i in data["done"] if isinstance(i, str)}
        return [i for i in _index() if i in done]


def _write(done):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=PATH.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"done": done}, stream)
        os.replace(name, PATH)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def cascade(done, identifier, complete):
    """DONE (a set of ids) after marking IDENTIFIER complete or not, cascading along its chain."""
    if identifier not in _index():
        raise ValueError("Unknown mission")
    _, ids, place = _index()[identifier]
    return set(done) | set(ids[: place + 1]) if complete else set(done) - set(ids[place:])


def set_done(identifier, complete):
    if not isinstance(complete, bool):
        raise ValueError("done must be true or false")
    with lock:
        done = cascade(read(), identifier, complete)
        _write([i for i in _index() if i in done])
        return payload()


def reset_round():
    """Clear every round mission, as when the character dies; permanent missions stay."""
    with lock:
        _write([i for i in read() if _index()[i][0] != "round"])
        return payload()


def summary(done):
    points, index = _points(), _index()
    total = sum(points[i] for i in done)
    permanent = sum(points[i] for i in done if index[i][0] == "permanent")
    grades = catalog()["grades"]
    grade = max((g for g in grades if total >= g["points"]), key=lambda g: g["points"])
    upcoming = [g for g in grades if g["points"] > total]
    return {
        "points": total,
        "permanent": permanent,
        "round": total - permanent,
        "grade": grade["grade"],
        "next": upcoming[0] if upcoming else None,
        "completed": len(done),
        "total": len(index),
        "max_points": sum(points.values()),
    }


def payload():
    done = read()
    return {"catalog": catalog(), "done": done, "summary": summary(done)}
