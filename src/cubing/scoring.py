"""Display equivalent totals using the same line parsing and weights as cost estimates."""

from typing import Any

from cubing.lines import parse_line
from cubing.probability import family
from cubing.targets import validate_spec
from flaming.profiles import classes
from flaming.vision import ReadError


def _weighted_value(metric, config, parsed):
    factors = family(metric, config)
    return sum(amount * factors.get(category, 0) for category, amount in parsed)


def _parse_potential_lines(potential):
    """Parsed (category, amount) pairs for a scanned potential, or an unavailable reason."""
    if not isinstance(potential, dict) or potential.get("status") != "scanned":
        return None, "Scan this item’s potential to see its equivalent total."
    lines = potential.get("lines")
    if (
        not isinstance(lines, list)
        or not 2 <= len(lines) <= 3
        or any(not isinstance(line, str) for line in lines)
    ):
        return None, "The saved potential is incomplete. Scan this item again."
    try:
        return [parse_line(line) for line in lines], None
    except ReadError:
        return None, "A saved potential line could not be read. Scan this item again."


def _formula_text(wse, role, weights, attack):
    if wse:
        return f"{role['att']}% + Boss Damage% ÷ {attack['boss_per_attack']}; IED is separate."
    if "stat_weights" in weights:
        parts = " + ".join(f"{stat}% x {weight:.4f}" for stat, weight in weights["stat_weights"].items())
        return parts + f" + All Stat% x {weights['all_stat_weight']:.4f}."
    return f"Primary stat% + secondary stat% × {weights['secondary_weight']} + All Stat% × {weights['all_stat_weight']}."


def _supplemental_rules(slot, character_class, config, parsed, metric, value):
    """Crit Damage and cooldown are the only rolls that supplement the equivalent score;
    drop, mesos and IED are not part of this valuation."""
    from cubing.targets import allowed_metrics

    rules = [{"metric": metric, "unit": "percent", "value": value}] if value > 0 else []
    for special, unit in [("CRIT_DAMAGE", "percent"), ("COOLDOWN", "seconds")]:
        if special not in allowed_metrics(slot, character_class):
            continue
        amount = _weighted_value(special, config, parsed)
        if amount > 0:
            rules.append({"metric": special, "unit": unit, "value": amount})
    return rules


def _current_cost(slot, character_class, potential, config, item_level, rules):
    from cubing.probability import estimate
    from cubing.targets import RANKS

    if potential.get("rank") not in RANKS:
        return {"unavailable": "No supported current roll or rank to estimate."}
    spec = {**config, "item_level": item_level, "rank": potential["rank"], "rules": rules}
    try:
        return {
            **estimate(slot, spec, character_class),
            "spec": spec,
            "description": "Match current equivalent score or better, retaining Crit Damage and cooldown. Drop, mesos and IED excluded. Tier-up and reveal fees excluded.",
        }
    except ValueError as exc:
        return {"unavailable": str(exc)}


def current_score(
    slot, character_class, potential, score=None, attack_score=None, item_level=None
) -> dict[str, Any]:
    role = classes().get(character_class)
    if role is None:
        raise ValueError("Choose a supported character class")
    wse = slot in ("weapon", "secondary", "emblem")
    metric = role["att"] + "_EQ" if wse else "MAIN_EQ"
    label = role["att"] + " equivalent" if wse else "Main stat equivalent"
    from cubing import profiles

    weights = score if score is not None else profiles.score(character_class)
    attack = attack_score if attack_score is not None else profiles.attack_score(character_class)
    config = {"attack_score": attack} if wse else {"score": weights}
    validate_spec(slot, {**config, "rank": "Rare", "item_level": None, "rules": []}, character_class)
    response = {"metric": metric, "label": label, "unit": "percent"}
    parsed, unavailable = _parse_potential_lines(potential)
    if unavailable:
        return {**response, "unavailable": unavailable}
    value = _weighted_value(metric, config, parsed)
    response.update(value=value, formula=_formula_text(wse, role, weights, attack))
    rules = _supplemental_rules(slot, character_class, config, parsed, metric, value)
    response["current_cost"] = _current_cost(slot, character_class, potential, config, item_level, rules)
    return response
