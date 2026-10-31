"""Hyper Stat allocation with the most boss FD, from a saved Scouter calculation.

Every hyper stat Scouter scores lands in an additive pool (stats, Damage + Boss,
ATT, Critical Damage) or in the IED defense term. A saved result's efficiencies
give each pool's size (+1 to a pool of P is 1/P more damage) and ignoreDefConst
gives the defense term, so any allocation's FD follows exactly, per pool,
without re-deriving the class formula. Critical Rate only has to reach 100%.
"""

import copy
import functools
import itertools
import math

import numpy as np

from utils.payload_data import read_payload_json

ARCHERS = {"Bowmaster", "Marksman", "Pathfinder", "Wind Archer", "Mercedes", "Wild Hunter", "Kain"}
DEFENSES = ("300", "380")
# Scouter input fields whose scanned totals already include the hyper stat.
FIELDS = {
    "crit_rate": "critical",
    "crit_damage": "criticalDmg",
    "ied": "ignoreDef",
    "damage": "dmg",
    "boss_damage": "bossDmg",
    "normal_damage": "normalDmg",
    "attack": "atkBase",
    "arcane_power": "arcaneForce",
}
# Allocations this close in log FD count as equal; the one closer to the current levels wins.
TIE = 1e-9


@functools.cache
def table():
    return read_payload_json("src/hyperstats/data/hyper_stats.json")


@functools.cache
def stats():
    return {s["key"]: s for s in table()["stats"]}


def value(stat, level):
    return stat["values"][level - 1] if level else 0


def total_points(level):
    return sum(3 + (lv - 140) // 10 for lv in range(140, min(int(float(level)), 300) + 1))


def spent(levels):
    costs = table()["costs"]
    return sum(sum(costs[:level]) for level in levels.values())


def stat_fields(info):
    """Hyper STR/DEX/INT/LUK keys the class scores, mapped to their "% not applied" input."""
    pairs = zip((info["main"], info["sub"], info["sub2"]), ("mainStatAbs", "subStatAbs", "ssubStatAbs"))
    return {name.lower(): field for name, field in pairs if name in ("STR", "DEX", "INT", "LUK")}


def fields(info):
    return {**stat_fields(info), **FIELDS}


def blocked(info):
    if info["main"] == "HP":
        return f"{info['name']} isn't supported: HP is the main stat, and the optimizer can't value Hyper HP."
    return None


def default_keep(info):
    """Only Critical Rate: crit needs (and, for Vicious Shot classes, rewards) more than the optimizer sees."""
    return ["crit_rate"]


def defaults(info, user):
    return {
        "stats": table()["stats"],
        "keep": default_keep(info),
        "crit_rate": number(user["stat"].get("critical")),
        "archer": info["name"] in ARCHERS,
        "blocked": blocked(info),
        "budget": total_points(user["stat"]["level"]),
    }


def number(raw):
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def clean(request):
    if not isinstance(request, dict):
        raise ValueError("Enter hyper stats as an object")
    table_ = stats()
    raw_levels = request.get("levels") or {}
    if not isinstance(raw_levels, dict) or set(raw_levels) - set(table_):
        raise ValueError("Unsupported hyper stat")
    levels = {}
    for key, stat in table_.items():
        raw = raw_levels.get(key, 0)
        level = None if isinstance(raw, bool) else number(raw)
        top = len(stat["values"])
        if level is None or not level.is_integer() or not 0 <= level <= top:
            raise ValueError(f"{stat['label']} must be a whole number from 0 to {top}")
        levels[key] = int(level)
    keep = request.get("keep") or []
    if not isinstance(keep, list) or set(keep) - set(table_):
        raise ValueError("Unsupported hyper stat in Keep")
    defense = str(request.get("defense", "380"))
    if defense not in DEFENSES:
        raise ValueError("Defense must be 300 or 380")
    crit = None
    if "crit_rate" not in keep:
        raw = request.get("crit_rate")
        crit = None if isinstance(raw, bool) else number(raw)
        if crit is None or not 0 <= crit <= 1000:
            raise ValueError("Enter your in-combat Critical Rate (0–1000%)")
    return {"levels": levels, "keep": set(keep), "defense": defense, "crit_rate": crit}


def coefficients(info, calculated):
    eff = calculated.get("specEfficiency") or {}

    def positive(source, key):
        number = source.get(key)
        if (
            isinstance(number, bool)
            or not isinstance(number, (int, float))
            or not math.isfinite(number)
            or number <= 0
        ):
            raise ValueError(f"Calculate Scouter again; {key} is unavailable.")
        return number

    # A +1% IED line raises the defense term k = 1 - d(1 - IED) by eff, which pins k down:
    # eff = 0.01(1 - k) / k. Newer Scouter responses no longer include ignoreDefConst itself.
    ied = {"300": positive(eff, "igreff1"), "380": positive(eff, "igreff1_380")}
    return {
        "stats": {key: positive(eff, field + "eff1") for key, field in stat_fields(info).items()},
        "damage": positive(eff, "dmgeff1"),
        "attack": positive(eff, "atkeff1"),
        "crit_damage": positive(eff, "cridmgeff1"),
        "ied": {d: 1 - e / (0.01 + e) for d, e in ied.items()},
    }


def _ied(const, old, new):
    """Scouter's defense term after swapping hyper IED old -> new (IED stacks multiplicatively)."""
    return (1 - (1 - const) * (1 - new / 100) / (1 - old / 100)) / const


def _factors(co, table_, current, defense):
    """Per pool: (hyper stats, damage ratio for their levels vs the current levels)."""

    def delta(levels, key):
        return value(table_[key], levels[key]) - value(table_[key], current[key])

    return [
        (list(co["stats"]), lambda lv: 1 + sum(co["stats"][k] * delta(lv, k) for k in co["stats"])),
        (
            ["damage", "boss_damage"],
            lambda lv: 1 + co["damage"] * (delta(lv, "damage") + delta(lv, "boss_damage")),
        ),
        (["attack"], lambda lv: 1 + co["attack"] * delta(lv, "attack")),
        (["crit_damage"], lambda lv: 1 + co["crit_damage"] * delta(lv, "crit_damage")),
        (
            ["ied"],
            lambda lv: _ied(
                co["ied"][defense], value(table_["ied"], current["ied"]), value(table_["ied"], lv["ied"])
            ),
        ),
    ]


def fd_percent(co, current, levels, defense):
    table_ = stats()
    ratio = 1.0
    for _, factor in _factors(co, table_, current, defense):
        ratio *= factor(levels)
    return (ratio - 1) * 100


def _options(keys, factor, current, table_, costs):
    """Best score at each exact point cost over every level combination of one pool."""
    cumulative = [sum(costs[:n]) for n in range(len(costs) + 1)]
    best = {}
    for combo in itertools.product(*(range(len(table_[k]["values"]) + 1) for k in keys)):
        levels = dict(zip(keys, combo))
        ratio = factor({**current, **levels})
        if ratio <= 0:
            continue
        score = math.log(ratio) + TIE * sum(levels[k] == current[k] for k in keys)
        cost = sum(cumulative[n] for n in combo)
        if cost not in best or score > best[cost][0]:
            best[cost] = (score, levels)
    return best


def _knapsack(groups, budget):
    """Exact max-score allocation over independent pools within the point budget."""
    dp = np.full(budget + 1, -np.inf)
    dp[0] = 0.0
    picks = []
    for options in groups:
        new, pick = np.full(budget + 1, -np.inf), np.full(budget + 1, -1)
        for cost, (score, _) in options.items():
            if cost > budget:
                continue
            candidate = np.full(budget + 1, -np.inf)
            candidate[cost:] = dp[: budget + 1 - cost] + score
            better = candidate > new
            new[better], pick[better] = candidate[better], cost
        dp = new
        picks.append(pick)
    remaining, chosen = int(np.argmax(dp)), {}
    for options, pick in zip(reversed(groups), reversed(picks)):
        cost = int(pick[remaining])
        chosen.update(options[cost][1])
        remaining -= cost
    return chosen


def _crit_floor(stat, current, crit_rate):
    """Lowest Critical Rate level keeping in-combat crit at 100%, or None when 15 isn't enough."""
    without = crit_rate - value(stat, current)
    return next((lv for lv in range(len(stat["values"]) + 1) if without + value(stat, lv) >= 100), None)


def _mismatches(info, user, table_, levels, crit_rate):
    problems = []
    for key, field in fields(info).items():
        scanned = number(user["stat"].get(field))
        hyper = value(table_[key], levels[key])
        if scanned is not None and hyper > scanned + 1e-9:
            problems.append(
                f"Hyper {table_[key]['label']} (+{hyper:g}) is more than your scanned {field} ({scanned:g})."
            )
    hyper = value(table_["crit_rate"], levels["crit_rate"])
    if crit_rate is not None and hyper > crit_rate:
        problems.append(
            f"Hyper Critical Rate (+{hyper:g}%) is more than your in-combat Critical Rate ({crit_rate:g}%)."
        )
    if problems:
        problems.append("Enter the levels of the hyper stat preset you scanned with.")
    return problems


def optimize(info, user, calculated, request):
    if message := blocked(info):
        raise ValueError(message)
    req = clean(request)
    table_, costs, current = stats(), table()["costs"], req["levels"]
    budget, used = total_points(user["stat"]["level"]), spent(current)
    result = {
        "budget": budget,
        "current": {"levels": current, "cost": used},
        "defense": req["defense"],
        "warnings": [],
        "blockers": [],
    }
    if used > budget:
        level = int(float(user["stat"]["level"]))
        result["blockers"].append(
            f"These levels cost {used:,} points; a level {level} character has {budget:,}."
        )
    result["blockers"] += _mismatches(info, user, table_, current, req["crit_rate"])
    if result["blockers"]:
        return result

    co = coefficients(info, calculated)
    fixed = {key: current[key] for key in req["keep"]}
    if "crit_rate" not in req["keep"]:
        floor = _crit_floor(table_["crit_rate"], current["crit_rate"], req["crit_rate"])
        if floor is None:
            floor = len(table_["crit_rate"]["values"])
            result["warnings"].append("Critical Rate stays under 100% even at the max hyper level.")
        fixed["crit_rate"] = floor
    free_budget = budget - spent(fixed)
    if free_budget < 0:
        result["blockers"].append(
            "The kept stats and the Critical Rate needed for 100% cost more points than you have."
        )
        return result

    groups = []
    for keys, factor in _factors(co, table_, current, req["defense"]):
        free = [k for k in keys if k not in fixed]
        if free:
            groups.append(_options(free, factor, current, table_, costs))
    valued = {k for keys, _ in _factors(co, table_, current, req["defense"]) for k in keys}
    for key in table_:
        if key not in fixed and key not in valued:
            groups.append(_options([key], lambda lv: 1.0, current, table_, costs))
    suggested = {**current, **fixed, **_knapsack(groups, free_budget)}

    gain = fd_percent(co, current, suggested, req["defense"])
    if suggested["crit_rate"] == current["crit_rate"] and gain <= 1e-10:
        suggested = dict(current)
    result.update(
        suggested={"levels": suggested, "cost": spent(suggested)},
        fd_percent={d: fd_percent(co, current, suggested, d) for d in DEFENSES},
        already_optimized=suggested == current,
    )
    return result


def apply(info, user, current, suggested):
    """Scouter input with the suggested hyper stats in place of the current ones."""
    user = copy.deepcopy(user)
    table_ = stats()
    for key, field in fields(info).items():
        old, new = value(table_[key], current[key]), value(table_[key], suggested[key])
        if old == new:
            continue
        scanned = float(user["stat"][field])
        if key == "ied":
            updated = 100 - (100 - scanned) * (1 - new / 100) / (1 - old / 100)
        else:
            updated = scanned + new - old
        user["stat"][field] = format(round(updated, 10), ".12g")
    return user
