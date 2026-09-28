"""Reconstruct legal example flames close to a conditional gain distribution."""

from itertools import combinations, product
from typing import Any

import numpy as np

from flaming.probability import SCALE


def _update_best(best, targets, totals, chances, indices, line_ids, rolls):
    for n, (label, target) in enumerate(targets):
        distances = np.abs(totals[indices] / SCALE - target)
        closest = indices[np.flatnonzero(distances == distances.min())]
        index = int(closest[np.argmax(chances[closest])])
        key = (float(abs(totals[index] / SCALE - target)), -float(chances[index]))
        if best[n] is None or key < best[n][0]:
            best[n] = (key, line_ids, rolls[index].copy(), label)


def _search_best(table, tiers, tier_chances, counts, scores, baseline, targets, required, checkpoint):
    best: list[Any] = [None] * len(targets)
    for count, probability in counts:
        if probability <= 0:
            continue
        rolls = np.asarray(list(product(range(len(tiers)), repeat=count)))
        chances = np.prod(np.asarray(list(tier_chances.values()))[rolls], axis=1)
        for line_ids in combinations(range(len(table)), count):
            checkpoint()
            if required is not None and required[0] not in line_ids:
                continue
            totals = scores[np.asarray(line_ids)[None, :], rolls].sum(axis=1)
            valid = (totals / SCALE - baseline > 1e-8) & (chances > 0)
            if required is not None:
                valid &= rolls[:, line_ids.index(required[0])] == required[1]
            if not valid.any():
                continue
            indices = np.flatnonzero(valid)
            _update_best(best, targets, totals, chances, indices, line_ids, rolls)
    return best


def _candidate_result(candidate, table, tiers, values, baseline):
    _, line_ids, roll, label = candidate
    stats, lines = {}, []
    for line_id, tier_id in zip(line_ids, roll, strict=True):
        line, tier = table[line_id], tiers[int(tier_id)]
        amount = line["tiers"][tier]
        for stat in line["stats"]:
            key = (stat, line["percent"])
            stats[key] = stats.get(key, 0) + amount
        lines.append({"stats": line["stats"], "tier": tier, "value": amount, "percent": line["percent"]})
    gain = (
        sum(values[line_id][int(tier)] for line_id, tier in zip(line_ids, roll, strict=True)) / SCALE - baseline
    )
    return stats, lines, gain, label


def examples(table, tier_chances, counts, values, baseline, targets, required=None, checkpoint=lambda: None):
    tiers = list(tier_chances)
    scores = np.asarray(values, dtype=np.int64)
    best = _search_best(table, tiers, tier_chances, counts, scores, baseline, targets, required, checkpoint)
    result, seen = [], set()
    for candidate in best:
        if candidate is None:
            continue
        stats, lines, gain, label = _candidate_result(candidate, table, tiers, values, baseline)
        signature = tuple(sorted(stats.items()))
        if signature in seen:
            continue
        seen.add(signature)
        result.append(
            {
                "label": label,
                "fd_gain": gain,
                "stats": [
                    f"{name} {value:+g}{'%' if percent else ''}" for (name, percent), value in stats.items()
                ],
                "lines": lines,
            }
        )
    return result
