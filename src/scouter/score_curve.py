"""Offline score conversion recovered from MapleScouter webpack module 62509.

This requires the API's damage value and spline; it is not a complete
user-input-to-damage calculator. See README.md for provenance and limits.
"""

import math


def damage_at_score(curve, score):
    x, y, slopes = curve["x"], curve["y"], curve["m"]
    if score < x[0]:
        return y[0] + (score - x[0]) * slopes[0]
    if score > x[-1]:
        return y[-1] + (score - x[-1]) * max(slopes[-1], 1e-9)
    segment = len(x) - 2
    for i in range(len(x) - 1):
        if x[i] <= score <= x[i + 1]:
            segment = i
            break
    i = segment
    width = x[i + 1] - x[i]
    t = (score - x[i]) / width
    t2, t3 = t * t, t * t * t
    return (
        (2 * t3 - 3 * t2 + 1) * y[i]
        + (t3 - 2 * t2 + t) * width * slopes[i]
        + (-2 * t3 + 3 * t2) * y[i + 1]
        + (t3 - t2) * width * slopes[i + 1]
    )


def score_from_damage(curve, damage, iterations=40, *, rounded=True):
    x, y, slopes = curve["x"], curve["y"], curve["m"]
    if damage <= y[0]:
        value = x[0] + (damage - y[0]) / max(slopes[0], 1e-9)
    elif damage >= y[-1]:
        value = x[-1] + (damage - y[-1]) / max(slopes[-1], 1e-9)
    else:
        low, high = x[0], x[-1]
        for _ in range(iterations):
            middle = (low + high) / 2
            if damage_at_score(curve, middle) < damage:
                low = middle
            else:
                high = middle
        value = (low + high) / 2
    # Comparisons need the continuous inverse: rounding can turn tiny losses
    # into gains. Displayed scores still mirror JavaScript Math.round.
    return math.floor(value + 0.5) if rounded else value
