"""Expected incremental FD per meso, using saved Scouter marginal efficiencies.

This is a local first-order estimate, not an exact simulated finished build.
Probabilities reuse the enhancement calculators' published fixed-rank tables.
"""

import copy
import math
from decimal import Decimal

import numpy as np

from cubing import probability as cubes
from cubing.item_database import item_metadata
from cubing.lines import parse_line
from cubing.targets import SLOTS
from flaming import characters, item_database
from flaming.probability import SCALE, _distribution
from scouter import cooldown, profiles
from scouter.flame_examples import examples as flame_examples
from starforce.cost import options as starforce_options
from starforce.suggestions import suggestions as starforce_suggestions
from utils.payload_data import read_payload_json

PROTECTED = {"Critical Damage %", "Skill Cooldown Reduction", "Item Drop Rate %", "Meso Amount %"}
VALUE_METRICS = [
    "STR",
    "DEX",
    "INT",
    "LUK",
    "HP",
    "ALL_STAT",
    "ATT",
    "MATT",
    "BOSS",
    "CRIT_DAMAGE",
    "COOLDOWN",
    "DROP",
    "MESO",
    "IED",
]


def equipment(identifier):
    profiles.identity(identifier)
    return characters.load(identifier)


def potential_basis(gear):
    """Manual potential weights, or None when the character uses Scouter weights."""
    if gear.get("potential_weight_source") == "scouter":
        return None
    from cubing import profiles as cube_profiles

    return {"score": cube_profiles.score(gear["class"]), "attack": cube_profiles.attack_score(gear["class"])}


def signature(gear):
    return profiles.fingerprint(
        {"class": gear["class"], "equipment": gear["equipment"], "potential_weights": potential_basis(gear)}
    )


def manual_potential(pot, basis, info, attack):
    """Scouter FD per 1% main stat (or ATT), spread over stats by the manual weights."""
    main = ("Max HP" if info["main"] == "HP" else info["main"]) + " %"
    weights = {"Critical Damage %": pot["Critical Damage %"]}
    weights.update({cat: pot[main] * w for cat, w in cubes.family("MAIN_EQ", {"score": basis["score"]}).items()})
    weights[attack + " %"] = pot[attack + " %"]
    weights["Boss Damage"] = pot[attack + " %"] / basis["attack"]["boss_per_attack"]
    return weights


def coefficients(record, info):
    eff = record["damage"]["calculatedData"].get("specEfficiency", {})

    def value(key):
        number = eff.get(key)
        if (
            isinstance(number, bool)
            or not isinstance(number, (int, float))
            or not math.isfinite(number)
            or number < 0
        ):
            raise ValueError(f"Calculate Scouter again; {key} efficiency is unavailable.")
        return number * 100  # Percent FD per unit, rather than fraction FD.

    flat, potential = {}, {}
    for stat, prefix in [(info["main"], "main"), (info["sub"], "sub"), (info.get("sub2"), "ssub")]:
        if not stat:
            continue
        name = "Max HP" if stat == "HP" else stat
        flat[name] = value(prefix + "Stateff1")
        potential[name + " %"] = value(prefix + "StatPereff1")
    attack = "MATT" if info["main"] == "INT" else "ATT"
    flat.update(
        {
            "All Stats": value("allStatEff"),
            "Boss Damage": value("dmgeff1"),
            "Damage": value("dmgeff1"),
            "Magic Attack" if attack == "MATT" else "Attack Power": value("atkeff1"),
        }
    )
    potential.update(
        {
            "All Stats %": value("allStatEff"),
            attack + " %": value("atkPereff1"),
            "Boss Damage": value("dmgeff1"),
            "Critical Damage %": value("cridmgeff1"),
        }
    )
    return flat, potential, value("igreff1_380"), attack


def summary(probability, gain_mass, unit_cost):
    if probability <= 0 or gain_mass <= 0:
        raise ValueError("No qualifying FD improvement in the published roll table.")
    gain = gain_mass / probability
    p = min(1.0, probability)
    cost = unit_cost / p
    return {
        "probability": p,
        "expected_rolls": 1 / p,
        "expected_mesos": cost,
        "expected_fd": gain,
        "fd_per_billion": gain / cost * 1e9,
        "cost_90": unit_cost * (math.ceil(math.log(0.1) / math.log1p(-p)) if p < 1 else 1),
    }


def potential_label(category, amount):
    if not amount:
        return "Other line"
    if category == "Skill Cooldown Reduction":
        return f"Cooldown: -{amount:g}s"
    return f"{category.removesuffix(' %')}: +{amount:g}%"


def flame_suggestion(slot, item, weights, attack, checkpoint=lambda: None):
    if item.get("flameable") is False or item.get("status") != "scanned" or not item.get("stats"):
        raise ValueError("No scanned, flameable item.")
    meta = item_database.lookup(item.get("name"), slot)
    if meta is None:
        raise ValueError("Flame metadata is unavailable.")
    table = item_database.line_table(meta)
    if not table:
        raise ValueError("This item cannot be flamed.")
    tiers = item_database.tier_distribution(meta)
    # Quantize to the existing distribution's millionths of a score point.
    coefficients = {k: Decimal(str(v)) for k, v in weights.items()}
    values = tuple(
        tuple(
            int(sum(coefficients.get(s, Decimal(0)) for s in line["stats"]) * line["tiers"][tier] * SCALE)
            for tier in tiers
        )
        for line in table
    )
    counts = tuple(
        (int(n), p) for n, p in item_database.rules()["line_counts"][meta["flame_category"]].items()
    )
    required = None
    if slot == "weapon":
        if "7" not in tiers:
            raise ValueError("Weapon keep rule requires tier-7 attack, unavailable for this item.")
        stat = "Magic Attack" if attack == "MATT" else "Attack Power"
        required = (
            next(i for i, line in enumerate(table) if line["stats"] == [stat]),
            list(tiers).index("7"),
        )
    scores, tail = _distribution(values, tuple(tiers.values()), counts, required)
    baseline = sum(weights.get(s["name"], 0) * s["value"] for s in item["stats"])
    mass = np.subtract(tail, np.r_[tail[1:], 0.0])
    gains = scores / SCALE - baseline
    keep = gains > 1e-8
    expectation = summary(float(mass[keep].sum()), float(np.dot(mass[keep], gains[keep])), 3_000_000)
    cumulative = np.cumsum(mass[keep]) / mass[keep].sum()
    selected_scores = scores[keep] / SCALE
    targets = [
        ("Near average gain", baseline + expectation["expected_fd"]),
        ("Smaller gain", float(selected_scores[np.searchsorted(cumulative, 0.1)])),
        (
            "Larger gain",
            float(selected_scores[min(len(selected_scores) - 1, int(np.searchsorted(cumulative, 0.9)))]),
        ),
    ]
    samples = flame_examples(table, tiers, counts, values, baseline, targets, required, checkpoint)
    return {
        "method": "Black Flame",
        "kind": "flame",
        **expectation,
        "flame_examples": samples,
        "goal": "Any modeled FD improvement" + (f" with tier-7 {attack}" if required else ""),
        "current": [f"{s['name']} +{s['value']}{'%' if s.get('percent') else ''}" for s in item["stats"]],
        "protected": [],
        "examples": [],
        "notes": [
            "Expected cost is for the first flame with higher modeled FD than your current flame. It is not the cost of a specific example below.",
            "Displayed FD is the average gain across all qualifying flames. Each example shows its own actual modeled gain; no single roll is guaranteed to equal the average.",
            "Black Flame table; 3M per roll. Combat power can differ from this damage model.",
        ],
    }


def _scanned_roll(slot, item):
    if slot not in SLOTS:
        raise ValueError("Potential analysis is unavailable for this slot.")
    potential = item.get("potential") or {}
    rank = potential.get("rank")
    if (
        potential.get("status") != "scanned"
        or rank not in ("Unique", "Legendary")
        or len(potential.get("lines", [])) != 3
    ):
        raise ValueError(
            "Scan a three-line Unique or Legendary potential first; tier-up costs are not modeled."
        )
    level = (item_metadata(slot, item) or {}).get("level")
    if level is None:
        raise ValueError("Item level is unknown.")
    return potential, rank, level


def _scan_baseline(potential, weights):
    parsed = [parse_line(line) for line in potential["lines"]]
    old_score = sum(weights.get(cat, 0) * amount for cat, amount in parsed)
    old_ied = math.prod(1 - amount / 100 for cat, amount in parsed if cat == "Ignore Enemy Defense %")
    if old_ied <= 0:
        raise ValueError("Invalid scanned IED; scan this potential again.")
    return parsed, old_score, old_ied


def _protected_stats(parsed, model):
    protected = {
        cat: sum(v for c, v in parsed if c == cat) for cat in PROTECTED if any(c == cat for c, _ in parsed)
    }
    if model:
        protected.pop(cooldown.CATEGORY, None)
    return protected


def _record_outcome(buckets, model, protected, old_score, old_ied, ied_weight, args):
    chance, score, ied, totals, labels = args
    # Replacing an existing IED source: combine complements, never add IED percentages.
    gain = score - old_score + ied_weight * 100 * (1 - ied / old_ied)
    seconds = totals.get(cooldown.CATEGORY, 0)
    if model:
        gain = model.gain(seconds, gain)
    if gain <= 1e-8 or any(totals.get(k, 0) < v for k, v in protected.items()):
        return
    bucket = buckets.setdefault(
        seconds if model else None,
        {"probability": 0.0, "gain_mass": 0.0, "example_mass": 0.0, "example": []},
    )
    bucket["probability"] += chance
    bucket["gain_mass"] += chance * gain
    if chance > bucket["example_mass"]:
        bucket["example_mass"], bucket["example"] = chance, labels


def _cube_row(name, cost, model, protected, potential, seconds, bucket):
    return {
        "method": name,
        "kind": "cube",
        **summary(bucket["probability"], bucket["gain_mass"], cost),
        **({"cooldown_seconds": seconds} if model else {}),
        "goal": "Any modeled FD improvement",
        "protected": [f"{k}: {v:g}" for k, v in sorted(protected.items())],
        "examples": bucket["example"],
        "current": potential["lines"],
        "notes": [
            "Fixed-rank odds; reveal and tier-up fees excluded. Uses the calculator’s level-160+ approximation.",
            "Cooldown and mixed stat rolls use Scouter’s cooldown-specific score curves, converted to equivalent FD. Existing crit damage, drop and mesos are preserved."
            if model
            else "Existing cooldown, crit damage, drop and mesos are preserved.",
            *(
                [
                    f"Costs include only improving rolls with {seconds:g}s total hat cooldown."
                ]
                if model
                else []
            ),
            "Scouter FD and in-game CP can differ.",
            *(["Glowing cubes replace the current roll on every attempt."] if name == "Glowing" else []),
        ],
    }


def cube_suggestions(slot, item, character_class, weights, ied_weight, checkpoint, hat_model=None):
    potential, rank, level = _scanned_roll(slot, item)
    parsed, old_score, old_ied = _scan_baseline(potential, weights)
    model = hat_model(parsed) if slot == "hat" and hat_model else None
    protected = _protected_stats(parsed, model)
    value_rules = [{"metric": m, "unit": "percent"} for m in VALUE_METRICS]
    item_type = "ring" if SLOTS[slot] == "accessory" else "heart" if slot == "badge" else slot
    rows = []
    for cube, name, cost in [("black", "Bright", 22_000_000), ("red", "Glowing", 12_000_000)]:
        checkpoint()
        pools = cubes.pools_for(cubes.database()["rates"][item_type][cube][rank.lower()], max(120, level), value_rules)
        buckets = {}

        def visit(index, counts, chance, score, ied, totals, labels, pools=pools, buckets=buckets):
            if index == 3:
                _record_outcome(
                    buckets, model, protected, old_score, old_ied, ied_weight, (chance, score, ied, totals, labels)
                )
                return
            if index == 0:
                checkpoint()
            excluded = {cat for cat, n in counts.items() if n >= cubes.LIMITS[cat]}
            denominator = 1 - sum(p for cat, _, p in pools[index] if cat in excluded)
            for cat, contribution, p in pools[index]:
                if cat in excluded:
                    continue
                amount = max(contribution)
                next_counts = counts if cat not in cubes.LIMITS else {**counts, cat: counts.get(cat, 0) + 1}
                next_totals = {**totals, cat: totals.get(cat, 0) + amount} if cat in PROTECTED else totals
                visit(
                    index + 1,
                    next_counts,
                    chance * p / denominator,
                    score + weights.get(cat, 0) * amount,
                    ied * (1 - amount / 100) if cat == "Ignore Enemy Defense %" else ied,
                    next_totals,
                    labels + [potential_label(cat, amount)],
                )

        visit(0, {}, 1.0, 0.0, 1.0, {}, [])
        for seconds, bucket in buckets.items():
            rows.append(_cube_row(name, cost, model, protected, potential, seconds, bucket))
    if not rows:
        raise ValueError("No positive FD outcome preserves the existing lines.")
    return rows


def _item_choices(kind, slot, item, gear, data, flat, pot, ied, attack, checkpoint, hat_model):
    if kind == "flame":
        return [flame_suggestion(slot, item, flat, attack, checkpoint)]
    if kind == "cube":
        return cube_suggestions(slot, item, gear["class"], pot, ied, checkpoint, hat_model)
    return starforce_suggestions(slot, item, flat, gear, data.get("starforce_options"))


def _slot_kinds(slot, item, layout):
    for kind in ("flame", "cube", "starforce"):
        if kind == "flame" and layout.get(slot, {}).get("flameable") is False:
            continue
        if kind == "cube" and slot not in SLOTS:
            continue
        if kind == "starforce" and not item.get("starforce"):
            continue
        yield kind


def _slot_rows(slot, item, gear, data, layout, flat, pot, ied, attack, checkpoint, progress, hat_model):
    checkpoint()
    progress(f"Comparing upgrades for {item.get('name') or slot}…")
    common = {"slot": slot, "name": item.get("name") or slot, "icon": slot}  # Hascone serves captured equipment icons by slot.
    rows, skipped = [], []
    for kind in _slot_kinds(slot, item, layout):
        try:
            choices = _item_choices(kind, slot, item, gear, data, flat, pot, ied, attack, checkpoint, hat_model)
            rows.extend({**common, **row} for row in choices)
        except (ValueError, KeyError, TypeError) as exc:
            skipped.append({**common, "kind": kind, "reason": str(exc)})
    return rows, skipped


def build(data, gear, checkpoint=lambda: None, progress=lambda _: None, fetch_cooldown=None):
    digest = profiles.fingerprint(profiles.effective(data))
    record = next((r for r in reversed(data["history"]) if r.get("fingerprint") == digest), None)
    if record is None:
        raise ValueError("Calculate Scouter with your current inputs before generating suggestions.")
    if gear["class"] != data["character"]["class"]:
        raise ValueError("Equipment and Scouter character classes do not match.")
    flat, pot, ied, attack = coefficients(record, data["class_info"])
    basis = potential_basis(gear)
    if basis:
        pot = manual_potential(pot, basis, data["class_info"], attack)
    cooldown_cache = copy.deepcopy((data.get("suggestions") or {}).get("cooldown_cache") or {})

    def hat_model(parsed):
        seconds = sum(v for cat, v in parsed if cat == cooldown.CATEGORY)
        return cooldown.HatModel(record, seconds, cooldown_cache, fetch_cooldown, checkpoint, progress)

    rows, skipped = [], []
    layout = read_payload_json("src/flaming_data/equipment_layout.json")["slots"]
    for slot, item in gear["equipment"].items():
        if not isinstance(item, dict) or not item.get("name"):
            continue
        slot_rows, slot_skipped = _slot_rows(
            slot, item, gear, data, layout, flat, pot, ied, attack, checkpoint, progress, hat_model
        )
        rows.extend(slot_rows)
        skipped.extend(slot_skipped)
    rows.sort(key=lambda r: (-r["fd_per_billion"], r["expected_mesos"], r["slot"], r["method"]))
    return {
        "created": profiles.now(),
        "model_version": 5,
        "starforce_options": starforce_options(data.get("starforce_options")),
        "cooldown_cache": cooldown_cache,
        "baseline_id": record["id"],
        "baseline_created": record["created"],
        "fingerprint": digest,
        "gear_fingerprint": signature(gear),
        "potential_weights": "manual" if basis else "scouter",
        "equipment_scanned": gear.get("captured_at"),
        "potential_scanned": gear.get("potential_scanned_at"),
        "rows": rows,
        "skipped": skipped,
        "model": "Expected incremental FD at 380 DEF, using Scouter’s stat efficiencies and cooldown score curves. Gains are estimates, not exact full-build simulations.",
        "basis": "Flames/cubes: expected cost and average FD of qualifying rolls. Star Force: expected tap cost and FD at the selected star target, including recovery costs. Use the same preset for scans and Scouter.",
    }
