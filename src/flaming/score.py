"""Configurable flame score, computed with exact decimal arithmetic."""

from decimal import Decimal, InvalidOperation
from typing import Any


def decimal_value(value, label, maximum):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{label} must be a nonnegative number")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{label} must be a nonnegative number") from None
    exponent = number.as_tuple().exponent
    if not number.is_finite() or not 0 <= number <= maximum or not isinstance(exponent, int) or exponent < -6:
        raise ValueError(f"{label} must be between 0 and {maximum}, with at most six decimal places")
    return number


def normalize_score(config=None) -> dict[str, Any]:
    if config is None:
        config = {}
    if not isinstance(config, dict) or set(config) - {"class", "weights"}:
        raise ValueError("Invalid Flame Score configuration")
    from flaming.profiles import STATS, stat_weights

    class_name = config.get("class", "Shadower")
    defaults = stat_weights(class_name)
    weights = config.get("weights", {})
    if not isinstance(weights, dict) or set(weights) - set(STATS):
        raise ValueError("Unknown Flame Score stat weight")
    return {
        "class": class_name,
        "weights": {
            name: str(decimal_value(weights.get(name, default), f"{name} weight", 1000000))
            for name, default in defaults.items()
        },
    }


def flame_score(stats, config):
    # OCR Total Value already combines flat lines; percent values are percentage
    # points (7% = 7), not fractions. No all-stat multiplier on the flat bonuses.
    return sum(
        (Decimal(config["weights"].get(stat.name, "0")) * stat.value for stat in stats), Decimal(0)
    )
