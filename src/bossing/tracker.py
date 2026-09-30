"""Weekly boss clears, crystal income and a drop diary for the roster.

Weekly bosses reset every Thursday at 00:00 UTC and Black Mage on the 1st of
each month. Each character sells at most 14 weekly crystals (the most valuable
count) and each world at most 180 crystals of any kind a week.
"""
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from utils.payload_data import read_payload_json

PATH = Path("configs/bossing.json")
lock = threading.RLock()

# Nexon ranking world IDs for GMS NA. Heroic worlds pay five times the crystal value.
WORLDS = {1: "Bera", 19: "Scania", 45: "Kronos", 70: "Hyperion"}
HEROIC = {"Kronos", "Hyperion"}
WEEKLY_LIMIT = 14
WORLD_LIMIT = 180
DAILY_MAX = 7
HISTORY_WEEKS = 8


@lru_cache(maxsize=1)
def catalog():
    data = read_payload_json("src/bossing/data/bosses.json")
    return data, {boss["name"]: boss for boss in data["bosses"]}


@lru_cache(maxsize=1)
def drop_items():
    items = read_payload_json("src/bossing/data/drops.json")["items"]
    return items, {item["name"]: item for item in items}


PIRATES = {"AngelicBuster", "Ark", "Buccaneer", "Cannoneer", "Corsair", "Mechanic", "MoXuan", "Shade", "ThunderBreaker"}
MAIN_STAT_BRANCH = {"STR": "warrior", "Max HP": "warrior", "INT": "magician", "DEX": "bowman", "LUK": "thief"}


def branches(job):
    """Job branches whose class-locked drops (Eternal gear, Mitra's Rage) this class can use."""
    if job == "Xenon":
        return ["thief", "pirate"]
    if job in PIRATES:
        return ["pirate"]
    stats = next((row["main_stats"] for row in read_payload_json("src/flaming_data/classes.json") if row["class"] == job), [])
    return [MAIN_STAT_BRANCH[stats[0]]] if stats else []


def week_start(now):
    """The most recent Thursday 00:00 UTC at or before NOW."""
    now = now.astimezone(UTC)
    day = now.date() - timedelta(days=(now.weekday() - 3) % 7)
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def month_start(now):
    now = now.astimezone(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC)


def _next_month(start):
    return datetime(start.year + start.month // 12, start.month % 12 + 1, 1, tzinfo=UTC)


def read():
    with lock:
        if not PATH.exists():
            return {"characters": {}, "drops": []}
        data = json.loads(PATH.read_text(encoding="utf-8"))
        data.setdefault("characters", {})
        data.setdefault("drops", [])
        by_name = catalog()[1]
        for state in data["characters"].values():
            # Early saves keyed choices by boss alone; key them by category too.
            state["bosses"] = {
                key if ":" in key or f"{choice.get('difficulty')} {key}" not in by_name else group(by_name[f"{choice['difficulty']} {key}"]): choice
                for key, choice in state.get("bosses", {}).items()
            }
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


def _character(data, identifier):
    return data["characters"].setdefault(identifier, {"world": None, "bosses": {}, "clears": {}})


def group(boss):
    """Choices are per boss and category: Zakum can be both a daily and a weekly boss."""
    return f"{boss['category']}:{boss['base']}"


def world_name(profile, state):
    """The world chosen on the Bossing page, else the one Nexon reported."""
    return state.get("world") or WORLDS.get(profile.get("world_id"))


def value(boss, party, world):
    """Mesos each party member receives for one crystal."""
    multiplier = catalog()[0]["heroic_multiplier"] if world in HEROIC or world is None else 1
    return boss["mesos"] * multiplier // party


def configure(identifier, *, world=..., bosses=...):
    """Save the character's world and enabled bosses ({"category:base": {difficulty, party}})."""
    _, by_name = catalog()
    with lock:
        data = read()
        state = _character(data, identifier)
        if world is not ...:
            if world is not None and world not in WORLDS.values():
                raise ValueError("Choose Kronos, Hyperion, Bera or Scania.")
            state["world"] = world
        if bosses is not ...:
            if not isinstance(bosses, dict):
                raise ValueError("Invalid boss selection")
            chosen = {}
            for key, choice in bosses.items():
                if not isinstance(choice, dict):
                    raise ValueError("Invalid boss selection")
                base = str(key).partition(":")[2]
                boss = by_name.get(f"{choice.get('difficulty')} {base}")
                if boss is None or group(boss) != key:
                    raise ValueError(f"Unknown boss: {choice.get('difficulty')} {base}")
                party = choice.get("party", 1)
                if type(party) is not int or not 1 <= party <= boss["party_max"]:
                    raise ValueError(f"{boss['name']} allows a party of 1 to {boss['party_max']}.")
                chosen[key] = {"difficulty": boss["difficulty"], "party": party}
            state["bosses"] = chosen
        _write(data)
        return state


def _monthly_clear_week(state, name, now):
    """The week key in which a monthly boss was cleared this month, if any."""
    start = month_start(now)
    for week, clears in state["clears"].items():
        cleared = clears.get(name, {}).get("on")
        if cleared and start <= datetime.fromisoformat(cleared) < _next_month(start):
            return week
    return None


def set_clear(identifier, name, count, profile, now=None):
    """Record how many times NAME was cleared this week (dailies up to 7)."""
    now = now or datetime.now(UTC)
    _, by_name = catalog()
    boss = by_name.get(name)
    with lock:
        data = read()
        state = _character(data, identifier)
        enabled = state["bosses"].get(group(boss)) if boss else None
        if not boss or not enabled or enabled["difficulty"] != boss["difficulty"]:
            raise ValueError("Add this boss to the character's list first.")
        limit = DAILY_MAX if boss["category"] == "daily" else 1
        if type(count) is not int or not 0 <= count <= limit:
            raise ValueError(f"{name} can be cleared 0 to {limit} times a week.")
        week = week_start(now).isoformat()
        if boss["category"] == "monthly" and count:
            earlier = _monthly_clear_week(state, name, now)
            if earlier and earlier != week:
                raise ValueError(f"{name} was already cleared this month.")
        clears = state["clears"].setdefault(week, {})
        if count:
            clears[name] = {"count": count, "mesos": value(boss, enabled["party"], world_name(profile, state)), "on": now.isoformat()}
        else:
            clears.pop(name, None)
        if not clears:
            state["clears"].pop(week)
        _write(data)


def _earned(clears, by_name):
    """Crystal values a character can sell from one week's clears."""
    weekly = sorted((c["mesos"] for name, c in clears.items() if by_name.get(name, {}).get("category") == "weekly"), reverse=True)
    crystals = weekly[:WEEKLY_LIMIT]
    for name, clear in clears.items():
        category = by_name.get(name, {}).get("category")
        if category == "daily":
            crystals += [clear["mesos"]] * clear["count"]
        elif category == "monthly":
            crystals.append(clear["mesos"])
    return crystals


def summary(profiles, now=None):
    """Everything the Bossing page shows for the current week."""
    now = now or datetime.now(UTC)
    data, by_name = catalog()
    week = week_start(now)
    stored = read()
    rows, worlds = [], {}
    for profile in profiles:
        state = stored["characters"].get(profile["id"], {"world": None, "bosses": {}, "clears": {}})
        world = world_name(profile, state)
        clears = state["clears"].get(week.isoformat(), {})
        bosses = []
        for key, choice in state["bosses"].items():
            boss = by_name.get(f"{choice['difficulty']} {key.partition(':')[2]}")
            if boss is None or group(boss) != key:
                continue
            done = clears.get(boss["name"], {}).get("count", 0)
            earlier = boss["category"] == "monthly" and not done and _monthly_clear_week(state, boss["name"], now)
            bosses.append({
                **boss,
                "party": choice["party"],
                "value": value(boss, choice["party"], world),
                "count": done,
                "limit": DAILY_MAX if boss["category"] == "daily" else 1,
                "cleared_this_month": bool(earlier),
            })
        bosses.sort(key=lambda b: ({"weekly": 0, "monthly": 1, "daily": 2}[b["category"]], -b["value"], b["name"]))
        weekly_values = sorted((b["value"] for b in bosses if b["category"] == "weekly"), reverse=True)
        possible = sum(weekly_values[:WEEKLY_LIMIT])
        possible += sum(b["value"] * DAILY_MAX for b in bosses if b["category"] == "daily")
        possible += sum(b["value"] for b in bosses if b["category"] == "monthly" and not b["cleared_this_month"])
        crystals = _earned(clears, by_name)
        worlds.setdefault(world or "Unknown", []).extend(crystals)
        rows.append({
            "id": profile["id"],
            "name": profile["name"],
            "class": profile["class"],
            "branches": branches(profile["class"]),
            "level": profile.get("level"),
            "world": world,
            "world_chosen": state.get("world") is not None,
            "bosses": bosses,
            "earned": sum(crystals),
            "possible": possible,
            "weekly_selected": len(weekly_values),
            "weekly_cleared": sum(1 for b in bosses if b["category"] == "weekly" and b["count"]),
            "done": bool(bosses) and all(b["count"] >= b["limit"] or b["cleared_this_month"] for b in bosses),
        })
    history = []
    for offset in range(HISTORY_WEEKS):
        start = week - timedelta(weeks=offset)
        total = sum(
            sum(_earned(state["clears"].get(start.isoformat(), {}), by_name))
            for state in stored["characters"].values()
        )
        history.append({"week": start.date().isoformat(), "mesos": total})
    return {
        "week": week.isoformat(),
        "reset": (week + timedelta(weeks=1)).isoformat(),
        "monthly_reset": _next_month(month_start(now)).isoformat(),
        "weekly_limit": WEEKLY_LIMIT,
        "world_limit": WORLD_LIMIT,
        "worlds": [{"world": w, "crystals": len(v), "over": max(0, len(v) - WORLD_LIMIT)} for w, v in worlds.items() if v],
        "characters": rows,
        "history": history,
        "catalog": data["bosses"],
        "heroic_multiplier": data["heroic_multiplier"],
        "world_names": list(WORLDS.values()),
        "heroic": sorted(HEROIC),
        "drops": stored["drops"],
        "drop_items": drop_items()[0],
    }


def _drop(body, roster):
    _, items = drop_items()
    character = body.get("character")
    if character not in roster:
        raise ValueError("Choose a character from your roster.")
    item = items.get(body.get("item"))
    if item is None:
        raise ValueError("Choose an item from the list.")
    try:
        on = date.fromisoformat(str(body.get("date")))
    except ValueError as exc:
        raise ValueError("Enter the date of the drop.") from exc
    note = str(body.get("note") or "").strip()
    if len(note) > 200:
        raise ValueError("Keep the note under 200 characters.")
    return {"character": character, "item": item["name"], "boss": item["boss"], "date": on.isoformat(), "note": note}


def add_drop(body, roster):
    entry = {"id": uuid.uuid4().hex, **_drop(body, roster)}
    with lock:
        data = read()
        data["drops"].append(entry)
        _write(data)
    return entry


def update_drop(identifier, body, roster):
    with lock:
        data = read()
        entry = next((d for d in data["drops"] if d["id"] == identifier), None)
        if entry is None:
            raise ValueError("That drop no longer exists.")
        entry.update(_drop(body, roster))
        _write(data)
    return entry


def delete_drop(identifier):
    if not re.fullmatch(r"[a-f0-9]{32}", identifier or ""):
        raise ValueError("Invalid drop")
    with lock:
        data = read()
        data["drops"] = [d for d in data["drops"] if d["id"] != identifier]
        _write(data)


def forget(identifier):
    """Remove a deleted character's clears, settings and drops."""
    with lock:
        data = read()
        if data["characters"].pop(identifier, None) is None and not any(d["character"] == identifier for d in data["drops"]):
            return
        data["drops"] = [d for d in data["drops"] if d["character"] != identifier]
        _write(data)
