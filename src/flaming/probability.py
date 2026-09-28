"""Exhaustive Black Flame score distribution, without Monte Carlo sampling.

Choose distinct lines uniformly from 19, then independently roll each tier.
Scores use integer millionths, so strict improvements retain Decimal semantics.
"""

import math
from decimal import Decimal
from functools import lru_cache
from itertools import combinations, product

import numpy as np

from flaming import item_database as db

SCALE = 1_000_000


@lru_cache(maxsize=64)
def _distribution(values, tier_chances, counts, required=None):
    values = np.asarray(values, dtype=np.int64)
    scores, probabilities = [], []
    for count, count_chance in counts:
        tiers = np.asarray(list(product(range(len(tier_chances)), repeat=count)))
        chance = np.prod(np.asarray(tier_chances)[tiers], axis=1)
        chance *= count_chance / math.comb(len(values), count)
        for lines in combinations(range(len(values)), count):
            if required is not None:
                if required[0] not in lines:
                    continue
                keep = tiers[:, lines.index(required[0])] == required[1]
                scores.append(values[np.asarray(lines)[None, :], tiers[keep]].sum(axis=1))
                probabilities.append(chance[keep])
            else:
                scores.append(values[np.asarray(lines)[None, :], tiers].sum(axis=1))
                probabilities.append(chance)
    scores = np.concatenate(scores)
    probabilities = np.concatenate(probabilities)
    order = np.argsort(scores)
    scores, probabilities = scores[order], probabilities[order]
    unique, starts = np.unique(scores, return_index=True)
    mass = np.add.reduceat(probabilities, starts)
    # Sum from the high end to avoid subtracting tiny probabilities from 1.
    tail = np.cumsum(mass[::-1])[::-1]
    unique.flags.writeable = False
    tail.flags.writeable = False
    return unique, tail


def improvement(item, baseline, score, *, inclusive=False):
    table = db.line_table(item)
    if not table:
        raise ValueError("This item cannot be flamed")
    tiers = db.tier_distribution(item)
    weights = score["weights"]
    values = tuple(
        tuple(
            int(
                sum((Decimal(weights.get(s, "0")) for s in line["stats"]), Decimal(0))
                * line["tiers"][tier]
                * SCALE
            )
            for tier in tiers
        )
        for line in table
    )
    counts = tuple((int(n), p) for n, p in db.rules()["line_counts"][item["flame_category"]].items())
    scores, tail = _distribution(values, tuple(tiers.values()), counts)
    threshold = Decimal(str(baseline)) * SCALE
    if not threshold.is_finite():
        raise ValueError("Invalid baseline score")
    # Integer scores greater than a possibly fractional threshold.
    index = (
        np.searchsorted(scores, int(threshold.to_integral_value(rounding="ROUND_CEILING")), side="left")
        if inclusive
        else np.searchsorted(scores, int(threshold.to_integral_value(rounding="ROUND_FLOOR")), side="right")
    )
    probability = float(tail[index]) if index < len(tail) else 0.0
    probability = min(1.0, max(0.0, probability))
    return {
        "probability": probability,
        "expected_rolls": 1 / probability if probability else None,
        "expected_mesos": 3_000_000 / probability if probability else None,
        "max_score": str(Decimal(int(scores[-1])) / SCALE),
    }
