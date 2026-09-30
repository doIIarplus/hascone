"""Exact mean tap cost for GMS enhancement modes, including destruction recovery."""

import math
from functools import lru_cache

from utils.payload_data import read_payload_json

DEFAULTS = {"mode_15_17": 1, "mode_18_21": 1, "discount": False, "boom_reduction": False}
MODE_STARS = range(15, 22)


@lru_cache(maxsize=1)
def rules():
    return read_payload_json("src/starforce/data/rules.json")


def options(value=None):
    if value is None:
        return dict(DEFAULTS)
    if not isinstance(value, dict) or set(value) - (DEFAULTS.keys() | {"safeguard"}):
        raise ValueError("Invalid Star Force mode options")
    cleaned = dict(value)
    # Preserve older profiles without silently enabling protection above 17★.
    if "safeguard" in cleaned:
        legacy = cleaned.pop("safeguard")
        if type(legacy) is not bool:
            raise ValueError("Safeguard must be a checkbox")
        cleaned.setdefault("mode_15_17", "safeguard" if legacy else 1)
    cfg = {**DEFAULTS, **cleaned}
    for key in ("discount", "boom_reduction"):
        if type(cfg[key]) is not bool:
            raise ValueError(f"{key} must be a checkbox")
    for key, maximum in (("mode_15_17", 3), ("mode_18_21", 4)):
        value = cfg[key]
        if key == "mode_15_17" and value == "safeguard":
            continue
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f"{key} is not an available enhancement mode")
    return cfg


def item_modes(value):
    """An item's chosen mode at each star from 15★ to 21★, or None to optimize every star.

    Older saves chose one mode for 15–17★ and one for 18–21★; they expand to each star."""
    if value is None:
        return None
    if isinstance(value, dict) and set(value) == {"mode_15_17", "mode_18_21"}:
        options(value)
        value = {str(star): value["mode_15_17"] if star <= 17 else value["mode_18_21"] for star in MODE_STARS}
    if not isinstance(value, dict) or set(value) != {str(star) for star in MODE_STARS}:
        raise ValueError("Choose a mode for each star from 15★ to 21★")
    for star in MODE_STARS:
        mode = value[str(star)]
        # Safeguard is the no-destruction choice at 15–17★; Mode 4 is at 18–21★.
        if not (star <= 17 and mode == "safeguard") and (type(mode) is not int or not 1 <= mode <= (3 if star <= 17 else 4)):
            raise ValueError(f"{star}★ is not an available enhancement mode")
    return {str(star): value[str(star)] for star in MODE_STARS}


def mode_summary(modes):
    """Item modes as runs of stars, e.g. "15–16★ Safeguard, 17–19★ Mode 1, 20–21★ Mode 4"."""
    runs = []
    for star in MODE_STARS:
        mode = modes[str(star)]
        if runs and runs[-1][2] == mode:
            runs[-1][1] = star
        else:
            runs.append([star, star, mode])
    name = {"safeguard": "Safeguard"}
    return ", ".join(
        f"{first}{'–' + str(last) if last != first else ''}★ {name.get(mode, f'Mode {mode}')}" for first, last, mode in runs
    )


def selection(star, cfg):
    if type(star) is not int or not 0 <= star < 30:
        raise ValueError("Invalid Star Force star")
    return cfg["mode_15_17"] if 15 <= star <= 17 else cfg["mode_18_21"] if 18 <= star <= 21 else None


def transition(star, settings=None):
    cfg, data = options(settings), rules()
    selected = selection(star, cfg)
    if type(selected) is int:
        entry = data["modes"][str(star)][selected - 1]
        success, boom = entry["success"], entry["boom"]
    else:
        success, _, boom = data["rates"][str(star)]
        if selected == "safeguard":
            boom = 0.0
    if cfg["boom_reduction"] and star <= data["boom_reduction_max_star"]:
        boom *= 1 - data["boom_reduction"]
    # Published probabilities already include the former starcatch bonus.
    return success, 1 - success - boom, boom


def tap_cost(level, star, settings=None):
    cfg, data = options(settings), rules()
    selected = selection(star, cfg)
    if type(level) is not int or not 1 <= level <= 300:
        raise ValueError("Invalid Star Force item level")
    coefficient = data["cost_coefficients"][str(star)]
    raw = (
        coefficient["mult"]
        * (level // 10 * 10) ** 3
        * (star + 1) ** coefficient["expo"]
        / coefficient["divisor"]
    )
    base = 100 * math.floor(raw + 10 + 0.5)
    multiplier = data["modes"][str(star)][selected - 1]["mult"] if type(selected) is int else 1
    if cfg["discount"]:
        multiplier *= 1 - data["discount"]
    if selected == "safeguard":
        multiplier += data["safeguard_surcharge"]
    return math.floor(base * multiplier + 0.5)


def expectations(level, current, target, settings=None):
    if type(current) is not int or type(target) is not int or not 0 <= current < target <= 30:
        raise ValueError("Target stars must exceed current stars, up to 30")
    costs, attempts, booms = [], [], []
    for star in range(target):
        success, _, boom = transition(star, settings)
        reset = rules()["boom_recovery_stars"][star]
        # One successful increment includes every return journey after a boom.
        costs.append((tap_cost(level, star, settings) + boom * sum(costs[reset:star])) / success)
        attempts.append((1 + boom * sum(attempts[reset:star])) / success)
        booms.append(boom * (1 + sum(booms[reset:star])) / success)
    return {
        "expected_mesos": sum(costs[current:target]),
        "expected_rolls": sum(attempts[current:target]),
        "expected_booms": sum(booms[current:target]),
    }


def optimize(level, current, target, settings=None, *, objective="mesos", modes=None):
    """Choose a mode at each visited star, with exact expected recovery costs.

    MODES (from item_modes) fixes the mode at each star from 15★ to 21★ instead.

    Each increment depends monotonically on the already optimized increments
    below it. Minimizing these in star order considers every possible policy
    without enumerating all 4**7 combinations of enhancement modes.
    """
    if objective not in {"mesos", "booms"}:
        raise ValueError("Unknown Star Force optimization objective")
    if type(current) is not int or type(target) is not int or not 0 <= current < target <= 30:
        raise ValueError("Target stars must exceed current stars, up to 30")
    cfg = options(settings)
    costs, attempts, booms, plan = [], [], [], []
    for star in range(target):
        choices = [1, 2, 3, "safeguard"] if 15 <= star <= 17 else [1, 2, 3, 4] if 18 <= star <= 21 else [None]
        if modes and 15 <= star <= 21:
            choices = [modes[str(star)]]
        candidates = []
        for mode in choices:
            settings = {**cfg}
            if 15 <= star <= 17:
                settings["mode_15_17"] = mode
            elif 18 <= star <= 21:
                settings["mode_18_21"] = mode
            success, _, boom = transition(star, settings)
            tap = tap_cost(level, star, settings)
            reset = rules()["boom_recovery_stars"][star]
            c = (tap + boom * sum(costs[reset:star])) / success
            a = (1 + boom * sum(attempts[reset:star])) / success
            b = boom * (1 + sum(booms[reset:star])) / success
            candidates.append(
                (
                    c,
                    a,
                    b,
                    {
                        "star": star,
                        "mode": mode,
                        "success": success,
                        "boom": boom,
                        "tap_cost": tap,
                        "recovery": star < current,
                    },
                )
            )
        c, a, b, step = min(candidates, key=lambda r: (r[0], r[2]) if objective == "mesos" else (r[2], r[0]))
        costs.append(c)
        attempts.append(a)
        booms.append(b)
        plan.append(step)
    floor = current
    while True:
        reachable = min(
            [
                floor,
                *[rules()["boom_recovery_stars"][step["star"]] for step in plan[floor:] if step["boom"] > 0],
            ]
        )
        if reachable == floor:
            break
        floor = reachable
    return {
        "expected_mesos": sum(costs[current:target]),
        "expected_rolls": sum(attempts[current:target]),
        "expected_booms": sum(booms[current:target]),
        "starforce_plan": plan[floor:],
    }
