"""Compare hat rolls on a common Scouter score curve, in equivalent damage.

Cooldown changes the API's damage-to-score curve, so raw damage ratios miss
its benefit. Map a candidate through its cooldown curve and back through the
baseline curve before computing FD. Stat deltas remain first-order estimates.
"""

import copy
import math
from functools import lru_cache

from scouter import profiles
from scouter.score_curve import damage_at_score, score_from_damage

CATEGORY = "Skill Cooldown Reduction"


def validate_curve(curve):
    if not isinstance(curve, dict):
        raise ValueError("Scouter cooldown score curve is unavailable; calculate Scouter again.")
    arrays = []
    for key in ("x", "y", "m"):
        values = curve.get(key)
        if not isinstance(values, list):
            raise ValueError("Scouter returned an invalid cooldown score curve.")
        arrays.append(values)
    if (
        len({len(a) for a in arrays}) != 1
        or len(arrays[0]) < 2
        or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for a in arrays
            for v in a
        )
        or any(b <= a for values in arrays[:2] for a, b in zip(values, values[1:], strict=False))
        or any(v < 0 for v in arrays[2])
    ):
        raise ValueError("Scouter returned an invalid cooldown score curve.")
    return curve


class HatModel:
    def __init__(self, record, current_seconds, cache, fetch, checkpoint, progress):
        self.checkpoint = checkpoint
        self.current_seconds = current_seconds
        user = record["input"]
        baseline = record["damage"]["calculatedData"]
        self.damage = baseline["calculatedHexaDamage_380"]
        if not isinstance(self.damage, (int, float)) or not math.isfinite(self.damage) or self.damage <= 0:
            raise ValueError("Scouter baseline damage is unavailable; calculate Scouter again.")
        self.base_curve = validate_curve(baseline.get("spline_380"))
        other_seconds = float(user["stat"]["coolTimeReduce"]) - current_seconds
        if not math.isfinite(other_seconds) or other_seconds < 0:
            raise ValueError(
                "Hat cooldown exceeds the Scouter input. Rescan stats and equipment on the same preset."
            )
        digest = profiles.fingerprint(user)
        if cache.get("fingerprint") != digest or cache.get("baseline_id") != record["id"]:
            cache.clear()
            cache.update(fingerprint=digest, baseline_id=record["id"], curves={})
        stored = cache["curves"]
        stored[format(float(user["stat"]["coolTimeReduce"]), "g")] = self.base_curve
        self.curves = {}
        for seconds in range(7):
            checkpoint()
            total = other_seconds + seconds
            key = format(total, "g")
            if key not in stored:
                if fetch is None:
                    raise ValueError(
                        "Cooldown comparison needs MapleScouter. Compare upgrades again while connected."
                    )
                progress(f"Calculating hat cooldown value: {seconds}s / 6s…")
                candidate = copy.deepcopy(user)
                candidate["stat"]["coolTimeReduce"] = key
                response = fetch(candidate)
                checkpoint()
                stored[key] = validate_curve(response.get("calculatedData", {}).get("spline_380"))
            self.curves[seconds] = validate_curve(stored[key])
        self.gain = lru_cache(maxsize=8192)(self._gain)

    def _gain(self, seconds, stat_fd):
        self.checkpoint()
        if seconds == self.current_seconds:
            return stat_fd
        if seconds not in self.curves:
            raise ValueError("Hat cooldown is outside the supported 0–6 second roll table.")
        damage = self.damage * (1 + stat_fd / 100)
        score = score_from_damage(self.curves[seconds], damage, rounded=False)
        equivalent_damage = damage_at_score(self.base_curve, score)
        return (equivalent_damage / self.damage - 1) * 100
