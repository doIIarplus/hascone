"""Pick one event piece per slot to fill a build's skill-line targets.

A port of the community 3L, GanDi (Hybrid) and EU set solvers: a DP over capped line
counts, one layer per slot. Lines above a target are wasted; a slot with no
eligible piece is left empty.

A piece marked "transfer" needs an orb: its lines count once moved onto the piece
worn in that slot (marked "worn"), or onto any on-class piece of the slot when none
is worn. Among equally good sets, the one needing the fewest transfers wins.

A piece marked "preferred" is locked into its slot: the rest of the set is solved
around it, even when another piece there would score more.
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


def _layers(plan, by_slot, locked, skip=None, edges=True):
    """One (slot, states) layer per slot. Each state keeps its combo count, "costs" (a bitmask:
    bit N is set when some path reaches it with N transfers) and, with EDGES, the
    (previous state, piece) pairs reaching it."""
    current = {tuple(0 for _ in plan.keys): {"ways": 1, "costs": 1}}
    layers = []
    for slot in slot_keys():
        if slot == skip:
            continue
        options = by_slot.get(slot) or []
        # Orbing costs a transfer, so a slot with a piece needing one may also stay as it is,
        # unless a worn piece fills it anyway.
        if not options or (slot not in locked and any(item.get("transfer") for item in options)
                           and not any(item.get("worn") for item in options)):
            options = options + [None]
        costs = [bool(item and item.get("transfer")) for item in options]
        optional = options[-1] is None
        following = {}
        for state, info in current.items():
            idle = False  # Whether a kept piece adds nothing here, making the empty option no extra combo.
            for item, cost in zip(options, costs, strict=True):
                nxt = plan.add(state, item["lines"]) if item else state
                # Never orb a piece that adds nothing, and leaving the slot empty is no extra
                # combo when one of its pieces adds nothing anyway.
                if nxt == state:
                    if (cost and slot not in locked) or (item is None and idle):
                        continue
                    idle = optional
                reach = info["costs"] << cost
                entry = following.get(nxt)
                if entry is None:
                    entry = following[nxt] = {"ways": info["ways"], "costs": reach, "edges": []}
                else:
                    entry["ways"] += info["ways"]
                    entry["costs"] |= reach
                if edges:
                    entry["edges"].append((state, item))
        layers.append((slot, following))
        current = following
    return layers


def _combos(layers, finals, limit):
    """Up to LIMIT (final state, {slot: piece}) paths into FINALS, fewest transfers first.

    Within a transfer count the first path found comes first, so the first combo is the
    one the community sites pick when no piece needs a transfer.
    """
    found = []

    def walk(depth, state, budget, picks):
        if len(found) >= limit:
            return
        if depth < 0:
            if not budget:
                found.append(dict(picks))
            return
        slot, layer = layers[depth]
        for prev, item in layer[state]["edges"]:
            left = budget - bool(item and item.get("transfer"))
            # Only follow an edge whose previous state is reachable with exactly LEFT
            # transfers, so every step leads to a combo and no path is walked in vain.
            before = layers[depth - 1][1][prev]["costs"] if depth else 1
            if left >= 0 and before >> left & 1:
                picks[slot] = item
                walk(depth - 1, prev, left, picks)

    final = layers[-1][1]
    for orbs in range(len(layers) + 1):
        for state in finals:
            if final[state]["costs"] >> orbs & 1:
                start = len(found)
                walk(len(layers) - 1, state, orbs, {})
                found[start:] = [(state, picks) for picks in found[start:]]
    return found


def _used(plan, picks):
    """Which lines of the chosen pieces count toward the goal, in slot order."""
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
    return used


def _orbs(picks):
    return sum(bool(item and item.get("transfer")) for item in picks.values())


def _ids(picks):
    return {slot: (picks[slot]["id"] if picks.get(slot) else None) for slot in slot_keys()}


COMBO_LIMIT = 100


def solve(items, targets, jobs=None):
    """Best set for ITEMS (dicts with id, slot, lines, optional transfer and preferred)
    under TARGETS and an optional job rule.

    A complete set also lists its winning combos (at most COMBO_LIMIT), fewest transfers first.
    """
    plan = _Plan(targets, jobs)
    by_slot = {}
    for item in items:
        by_slot.setdefault(item["slot"], []).append(item)
    locked = set()
    for slot, pieces in by_slot.items():
        preferred = [item for item in pieces if item.get("preferred")]
        if preferred:
            by_slot[slot] = preferred[:1]
            locked.add(slot)
    layers = _layers(plan, by_slot, locked)
    final = layers[-1][1]
    best = max(plan.score(state) for state in final)
    finals = [state for state in final if plan.score(state) == best]
    done = best >= plan.goal
    combos = _combos(layers, finals, COMBO_LIMIT if done else 1)
    best_state, picks = combos[0]
    return {
        "score": best,
        "goal": plan.goal,
        "counts": dict(zip(plan.keys, best_state, strict=True)),
        "picks": _ids(picks),
        "used": _used(plan, picks),
        "ways": sum(final[state]["ways"] for state in finals),
        "orbs": _orbs(picks),
        "combos": [{"picks": _ids(p), "used": _used(plan, p), "orbs": _orbs(p)} for _, p in combos]
        if done else [],
        "missing": plan.needs(best_state)[0] if not done else [],
        "hunt": _hunt(plan, by_slot, locked) if not done else [],
    }


def _hunt(plan, by_slot, locked):
    """Pieces that would finish the set in one drop: (slot, lines) with no repeated line.

    Orb cost is not considered; the page notes that a drop for a slot with a worn piece needs one.
    """
    limit = catalog()["max_lines"]
    found, seen = [], set()
    for slot in slot_keys():
        if slot in locked:
            continue  # A drop there would not be used.
        for state in _layers(plan, by_slot, locked, skip=slot, edges=False)[-1][1]:
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
