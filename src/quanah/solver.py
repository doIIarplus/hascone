"""Pick one event piece per slot to fill a build's skill-line targets.

A port of the community 3L, GanDi and EU set solvers: a DP over capped line
counts, one layer per slot. Lines above a target are wasted; a slot with no
eligible piece is left empty.
"""

from functools import lru_cache
from itertools import combinations

from utils.payload_data import read_payload_json

OTHER = "other"


@lru_cache(maxsize=1)
def catalog():
    return read_payload_json("src/quanah/data/lines.json")


def slot_keys():
    return [slot["key"] for slot in catalog()["slots"]]


def line_keys():
    return [line["key"] for line in catalog()["lines"]]


def job_keys():
    return [line["key"] for line in catalog()["lines"] if line.get("job")]


def trim_targets(saved):
    """Custom targets within the rules: known lines, 1 to 3 each, at most the goal in total.

    The store rejects anything else; a file saved before the 18-point cap is trimmed, in catalog order.
    """
    cap, room, targets = catalog()["max_per_line"], catalog()["goal"], {}
    for key in line_keys():
        value = min(int((saved or {}).get(key, 0)), cap, room)
        if value > 0:
            targets[key] = value
            room -= value
    return targets


def resolve_build(build):
    """(targets, job rule) for a saved build choice. The job rule is (count, active jobs) or None."""
    presets = {preset["key"]: preset for preset in catalog()["builds"]}
    preset = presets.get(build.get("preset"), presets["skill"])
    if preset["key"] == "custom":
        return trim_targets(build.get("targets")), None
    targets = dict(preset["targets"])
    rule = preset.get("jobs")
    if not rule:
        return targets, None
    if build.get("job_mode") == "any":
        return targets, (rule["count"], tuple(job_keys()))
    chosen = [k for k in build.get("jobs") or [] if k in job_keys()]
    if len(set(chosen)) != rule["count"]:
        chosen = rule["default"]
    return targets, (rule["count"], tuple(chosen))


class _Plan:
    def __init__(self, targets, jobs):
        self.targets = {k: v for k, v in targets.items() if v > 0}
        self.job_count, self.jobs = jobs if jobs else (0, ())
        # Job-rule lines count once each; fixed targets win if a key is both.
        self.keys = list(self.targets) + [k for k in self.jobs if k not in self.targets]
        self.caps = [self.targets.get(k, 1) for k in self.keys]
        self.index = {k: i for i, k in enumerate(self.keys)}
        self.goal = sum(self.targets.values()) + self.job_count

    def add(self, state, lines):
        state = list(state)
        for key in lines:
            i = self.index.get(key)
            if i is not None and state[i] < self.caps[i]:
                state[i] += 1
        return tuple(state)

    def score(self, state):
        fixed = sum(state[self.index[k]] for k in self.targets)
        jobs = sum(state[self.index[k]] for k in self.jobs if k not in self.targets)
        return fixed + min(self.job_count, jobs)

    def needs(self, state):
        """Every line set that would bring STATE up to the goal."""
        base = [k for k in self.targets for _ in range(state[self.index[k]], self.targets[k])]
        if not self.job_count:
            return [base]
        have = [k for k in self.jobs if k not in self.targets and state[self.index[k]]]
        open_jobs = [k for k in self.jobs if k not in self.targets and not state[self.index[k]]]
        missing = max(0, self.job_count - len(have))
        return [base + list(pick) for pick in combinations(open_jobs, missing)]


def _layers(plan, by_slot, skip=None):
    current = {tuple(0 for _ in plan.keys): {"ways": 1}}
    layers = []
    for slot in slot_keys():
        if slot == skip:
            continue
        options = by_slot.get(slot) or [None]
        following = {}
        for state, info in current.items():
            for item in options:
                nxt = plan.add(state, item["lines"]) if item else state
                entry = following.get(nxt)
                if entry:
                    entry["ways"] += info["ways"]
                else:
                    following[nxt] = {"prev": state, "item": item, "slot": slot, "ways": info["ways"]}
        layers.append(following)
        current = following
    return layers


def solve(items, targets, jobs=None):
    """Best set for ITEMS (dicts with id, slot, lines) under TARGETS and an optional job rule."""
    plan = _Plan(targets, jobs)
    by_slot = {}
    for item in items:
        by_slot.setdefault(item["slot"], []).append(item)
    layers = _layers(plan, by_slot)
    final = layers[-1]
    best_state = max(final, key=plan.score)  # max() keeps the first of equal scores, like the sites.
    best = plan.score(best_state)
    picks, state = {}, best_state
    for layer in reversed(layers):
        entry = layer[state]
        picks[entry["slot"]] = entry["item"]
        state = entry["prev"]
    # Which lines of the chosen pieces count toward the goal, in slot order.
    run, jobs_used, used = dict.fromkeys(plan.keys, 0), 0, {}
    for slot in slot_keys():
        item = picks.get(slot)
        flags = []
        for key in item["lines"] if item else []:
            if key in plan.targets:
                ok = run[key] < plan.targets[key]
            elif key in plan.jobs:
                ok = not run[key] and jobs_used < plan.job_count
                jobs_used += ok
            else:
                ok = False
            if key in run:
                run[key] += ok
            flags.append(ok)
        used[slot] = flags
    return {
        "score": best,
        "goal": plan.goal,
        "counts": dict(zip(plan.keys, best_state, strict=True)),
        "picks": {slot: (item["id"] if item else None) for slot, item in picks.items()},
        "used": used,
        "ways": final[best_state]["ways"],
        "missing": plan.needs(best_state)[0] if best < plan.goal else [],
        "hunt": _hunt(plan, by_slot) if best < plan.goal else [],
    }


def _hunt(plan, by_slot):
    """Pieces that would finish the set in one drop: (slot, lines) with no repeated line."""
    limit = catalog()["max_lines"]
    found, seen = [], set()
    for slot in slot_keys():
        for state in _layers(plan, by_slot, skip=slot)[-1]:
            if plan.goal - plan.score(state) > limit:
                continue
            for need in plan.needs(state):
                if not 0 < len(need) <= limit or len(set(need)) != len(need):
                    continue
                key = (slot, tuple(need))
                if key not in seen:
                    seen.add(key)
                    found.append({"slot": slot, "need": need})
    return found
