"""GMS Reboot boss percentages ported from the public result-page client."""

import math
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Any

from scouter.score_curve import damage_at_score, score_from_damage
from utils.payload_data import read_payload_json


@lru_cache(maxsize=1)
def catalog():
    return read_payload_json("src/scouter/data/boss_catalog.json")


def arcane_multiplier(required, current):
    if not required:
        return 1.0
    ratio = current / required * 100
    for limit, value in (
        (10, 10),
        (30, 30),
        (50, 60),
        (70, 70),
        (100, 80),
        (110, 100),
        (130, 110),
        (150, 130),
    ):
        if ratio < limit:
            return value / 100
    return 1.5


def sacred_multiplier(required, current):
    if not required:
        return 1.0
    gap = current - required
    for limit, value in (
        (-90, 5),
        (-80, 10),
        (-70, 20),
        (-60, 30),
        (-50, 40),
        (-40, 50),
        (-30, 60),
        (-20, 70),
        (-10, 80),
        (0, 90),
        (10, 100),
        (20, 105),
        (30, 110),
        (40, 115),
        (50, 120),
    ):
        if gap < limit:
            return value / 100
    return 1.25


def thresholds(party_reference, party_limit):
    """Ascending website category thresholds, expressed as percentages."""
    if party_reference:
        points = (
            [(90, "3인 최소컷"), (135, "2인 최소컷"), (270, "솔플 최소컷")]
            if party_limit == 3
            else [
                (90, "6인 최소컷"),
                (127.5, "4인 최소컷"),
                (170, "3인 최소컷"),
                (255, "2인 최소컷"),
                (510, "솔플 최소컷"),
            ]
        )
    else:
        party = {
            6: [(15, "파티 최소컷"), (25, "파티격 가능")],
            3: [(30, "파티 최소컷"), (36, "파티격 가능")],
            2: [(45, "파티 최소컷"), (55, "파티격 가능")],
            1: [],
        }
        points = party.get(party_limit, []) + [(90, "솔플 최소컷"), (110, "솔플 가능"), (200, "솔플 여유컷")]
    return points


def classify(rate, party_reference, party_limit, can_enter=True):
    if not can_enter:
        return "입장 불가능"
    result = "불가능"
    for percent, label in thresholds(party_reference, party_limit):
        # Compare the original ratio, not a rounded displayed percentage.
        if rate >= percent / 100:
            result = label
    return result


def fixed(value, digits):
    """Positive finite Number.toFixed rounding, including exact half ties."""
    return format(
        Decimal.from_float(value).quantize(Decimal(10) ** -digits, rounding=ROUND_HALF_UP), f".{digits}f"
    )


def display_percent(rate, party_reference):
    value = rate * 100
    if party_reference:
        return f"[Party] {math.floor(value + 0.5)}%"
    return (str(math.floor(value + 0.5)) if value >= 1000 else fixed(value, 1 if value >= 100 else 2)) + "%"


def potion_factor(job, efficiency, elixir, minutes=20):
    """Port of the result page's expiring Sayram/Collector correction."""
    data = catalog()
    before = data["buff_specs"]["before"][job]["spec"]
    after = data["buff_specs"]["after"][job]["spec"]
    archer = job in data["archers"]
    bishop = job == "비숍"
    hp_class = job == "데몬어벤져"
    cann = job in "캐논슈터"
    special = data["special_critical"]
    e = efficiency
    sayram = (
        (1 + (0 if archer else 8) * e["cridmgeff1"])
        * (1 + (0 if bishop else 30) * e["atkeff1"])
        * (1 + (0 if bishop else 10) * e["dmgeff1"])
        * (1 + (1275 if hp_class else 0) * e["mainStateff1"])
        * (1 + (0.235 * (0 if archer else 10) * e["cridmgeff1"] if special else 0))
        * (1 + (0 if job == "와일드헌터" else 10) * e["atkPereff1"])
    )
    attack = (
        (
            60
            if job in {"루미너스", "에반"}
            else 70
            if job in {"아란", "히어로", "미하일", "아크메이지(불,독)", "아크메이지(썬,콜)", "비숍"}
            else 100
        )
        + after[6]
        - before[6]
    )
    # Signed IED composition: remove the old buff, then add its replacement.
    ied = 100 * (after[11] - before[11]) / (100 - min(after[11], before[11]))
    collector = (
        (1 + (after[13] - before[13]) * e["cridmgeff1"])
        * (1 + attack * e["atkeff1"])
        * (1 + (after[9] - before[9] + after[8] - before[8]) * e["dmgeff1"])
        * (1 + ied * e["igreff1"])
        * (
            1
            + (400 + after[0] - before[0] if hp_class else (0 if cann else 30) + after[0] - before[0])
            * e["mainStateff1"]
        )
        * (1 + ((0 if cann else 30) + after[3] - before[3]) * (e["subStateff1"] + e["ssubStateff1"]))
        * ((1 + after[10] / 100) / (1 + before[10] / 100))
        * (1 + (0.235 * (after[12] - before[12]) * e["cridmgeff1"] if special else 0))
        * (1 + (after[7] - before[7]) * e["atkPereff1"])
    )
    time = min(20, max(0.1, minutes))
    first, middle, last = min(time, 8), max(0, min(7, time - 8)), max(0, min(5, time - 15))
    full = sayram * collector * first + sayram * middle + last
    active_sayram = sayram if elixir in (1, 3) else 1
    active_collector = collector if elixir in (2, 3) else 1
    actual = active_sayram * active_collector * first + active_sayram * middle + last
    return actual / full / (active_sayram * active_collector / (sayram * collector))


NAMES = {
    "jupiter": "Jupiter",
    "kaling": "Kaling",
    "adversary": "Adversary",
    "kalos": "Kalos",
    "bardrix": "Bardrix",
    "maleficStar": "Malefic Star",
    "limbo": "Limbo",
    "seren": "Seren",
    "blackMage": "Black Mage",
    "lotus": "Lotus",
    "verusHilla": "Verus Hilla",
    "darknell": "Darknell",
    "gloom": "Gloom",
    "slime": "Guardian Angel Slime",
    "will": "Will",
    "lucid": "Lucid",
    "damien": "Damien",
}


def _validate_calculate_args(user, minutes, view):
    if (
        user.get("isGMS") is not True
        or user.get("special", {}).get("isReboot") is not True
        or any(user.get(k) for k in ("isTMS", "isJMS", "isMSEA"))
    ):
        raise ValueError("Boss cuts are scoped to GMS Reboot")
    if not math.isfinite(minutes) or not 0.1 <= minutes <= 60:
        raise ValueError("Boss timer must be between 0.1 and 60 minutes")
    if view not in {"all", "relevant"}:
        raise ValueError("Boss view must be all or relevant")


def _arcane_and_sacred(user):
    # The website truncates string form fields with parseInt; numeric values
    # supplied directly to its helper retain their fractional part.
    def form_number(value):
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError("Arcane and Sacred Force must be finite nonnegative numbers")
        return number if isinstance(value, (int, float)) else int(number)

    arcane = min(form_number(user["stat"]["arcaneForce"]), catalog()["arcane_cap"])
    sacred = form_number(user["stat"]["authenticForce"])
    if any(not math.isfinite(value) or value < 0 for value in (arcane, sacred)):
        raise ValueError("Arcane and Sacred Force must be finite nonnegative numbers")
    return arcane, sacred


def _boss_adjusted_damage(boss, damage300, damage380, calculated, bonus, defense_ratio, correction, arcane, sacred, level):
    meta = boss["metadata"]
    force_arcane = arcane_multiplier(meta.get("bossArcaneForce"), arcane)
    force_sacred = sacred_multiplier(meta.get("bossAuthenticForce"), sacred)
    force_level = catalog()["level_multipliers"][str(max(-40, min(5, level - meta["bossLevel"])))] / 100
    standard_arcane = (1.1 if boss["boss"] == "검은 마법사" else 1.5) if boss.get("arcaneForce") else 1
    standard_sacred = 1.25 if boss.get("authenticForce") else 1
    damage = damage300 if boss["guard"] == 300 else damage380
    if boss["guard"] == 300 and boss["name"] == "slime":
        damage /= calculated.get("genePassConst") or 1
    if boss["guard"] == 380:
        if boss["name"] == "kaling":
            damage = calculated.get("calculatedHexaDamage_kaling") or damage380
        if bonus and boss["boss"] not in catalog()["authentic_bosses"]:
            damage *= defense_ratio
    adjusted = (
        damage
        * force_arcane
        * force_sacred
        * force_level
        / (1.2 * standard_arcane * standard_sacred)
        * correction
    )
    return adjusted, force_level, force_arcane, force_sacred


def _boss_rate(boss, adjusted, calculated):
    curve = calculated[f"spline_{boss['guard']}"]
    reference = damage_at_score(curve, boss.get("bossCut") or boss["partyBossCut"])
    rate = adjusted / (10000 if reference < 0 else reference) * (boss.get("easyRate") or 1)
    ascent = calculated.get("ascent_const", 0)
    ascent = 0 if ascent == 1 else ascent
    if ascent and rate:
        cycles = (
            0.4
            if boss["name"] == "lucid" and boss["difficulty"] == "Hard"
            else min(3, math.ceil(20 / rate / 5.667))
        )
        rate *= 1 + 3 * ascent / cycles - ascent
    return curve, rate


def calculate(user, calculated, *, minutes=20, view="all", include_quests=True, sacred_bonus=None):
    """Calculate the website's manual-input boss cards from damage and metadata.

    `calculated` can be an API calculatedData object or the offline adapter's
    equivalent. No network calls are made. Default settings match the manual
    page except `view=all` retains bosses hidden by its relevance filter.
    """
    _validate_calculate_args(user, minutes, view)
    result = {
        "source": "maplescouter_client_port",
        "region": "gms",
        "server": "reboot",
        "snapshot": catalog()["inspected"],
        "minutes": minutes,
        "view": view,
        "bosses": [],
    }
    damage300, damage380 = (calculated[f"calculatedHexaDamage_{defense}"] for defense in (300, 380))
    if damage300 <= 0 or damage380 <= 0:
        result.update(available=False, reason="The calculator has no usable HEXA damage for this profile")
        return result
    result["available"] = True
    level = int(float(user["stat"]["level"]))
    arcane, sacred = _arcane_and_sacred(user)
    correction = potion_factor(
        user["stat"]["myClass"], calculated["specEfficiency"], calculated["elixir"], minutes
    )
    bonus = bool(user["doping"].get("authenticDmg")) if sacred_bonus is None else sacred_bonus
    defense_ratio = (
        damage300 / calculated["ignoreDefConst_300"] * calculated["ignoreDefConst_380"] / damage380
        if bonus
        else 1
    )
    for boss in catalog()["bosses"]:
        if not include_quests and boss["difficulty"] in {"Destiny", "Champion"}:
            continue
        adjusted, force_level, force_arcane, force_sacred = _boss_adjusted_damage(
            boss, damage300, damage380, calculated, bonus, defense_ratio, correction, arcane, sacred, level
        )
        curve, rate = _boss_rate(boss, adjusted, calculated)
        party = bool(boss.get("partyBossCut"))
        limit = boss.get("partyLimit") or 6
        relevant = not (rate / limit > 10 or rate < 0.85 / limit) if party else 0.15 <= rate <= 10
        if view == "relevant" and not relevant:
            continue
        can_enter = level >= boss["entry_level"]
        category = classify(rate, party, limit, can_enter)
        result["bosses"].append(
            {
                "id": f"{boss['name']}_{boss['difficulty'].lower()}",
                "boss": NAMES.get(boss["name"], boss["name"]),
                "difficulty": boss["difficulty"],
                "icon": f"boss_{boss['difficulty'].lower()}_{boss['name']}.png",
                "percent": rate * 100,
                "display_percent": display_percent(rate, party),
                "category": catalog()["labels"][category],
                "reference": "party" if party else "solo",
                "party_limit": limit,
                "boss_hexa_score": score_from_damage(curve, adjusted),
                "can_enter": can_enter,
                "entry_level": boss["entry_level"],
                "relevant": relevant,
                "multipliers": {
                    "level": force_level,
                    "arcane": force_arcane,
                    "sacred": force_sacred,
                    "potion_duration": correction,
                },
                "thresholds": [
                    {"percent": threshold, "category": catalog()["labels"][label]}
                    for threshold, label in thresholds(party, limit)
                ],
            }
        )
    return result


def with_boss_cuts(record: dict[str, Any]) -> dict[str, Any]:
    """Add boss cards to legacy history using that record's exact saved inputs.

    Preserve already-saved estimates and their catalog snapshot. An unavailable
    estimate must never discard a successful API score or upgrade order.
    """
    if "boss_cuts" in record:
        return record
    try:
        cuts = calculate(record["input"], record["damage"]["calculatedData"])
    except (KeyError, ValueError, TypeError, ArithmeticError, OSError):
        cuts = {
            "available": False,
            "reason": "This saved result lacks supported boss-calculation data. Calculate again to refresh it.",
            "bosses": [],
        }
    return {**record, "boss_cuts": cuts}
