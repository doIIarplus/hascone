"""Resolve character flame weights from defaults, a saved Scouter calculation, or the user's own."""

import json
from decimal import Decimal, InvalidOperation

from flaming.score import normalize_score


def scoring(profile, identifier=None):
    from flaming import characters
    from flaming.profiles import STATS, classes, role_weights
    from scouter import profiles as scouter

    score = normalize_score({"class": profile["class"]})
    # Existing All Stat opt-ins now select the complete Scouter weight set.
    source = profile.get("flame_weight_source", profile.get("flame_all_stat_source", "default"))
    info = {
        "source": source,
        "effective_source": "default",
        "default_weight": score["weights"]["All Stats"],
        "scouter_weight": None,
        "default_weights": dict(score["weights"]),
        "scouter_weights": None,
        "stat_order": [],
        "calculated_at": None,
        "custom_weights": None,
    }
    if profile.get("flame_custom_weights"):
        try:
            info["custom_weights"] = normalize_score(
                {"class": profile["class"], "weights": profile["flame_custom_weights"]}
            )["weights"]
        except ValueError:
            pass
    if source == "custom" and info["custom_weights"]:
        # The user's own weights, e.g. to model another build or a future patch.
        score = {"class": profile["class"], "weights": info["custom_weights"]}
        info["effective_source"] = "custom"
    identifier = identifier or profile.get("id") or profile.get("source_character")
    try:
        if not identifier:
            raise ValueError("No character selected")
        characters.portrait_path(identifier)
        data = json.loads((scouter.DIRECTORY / f"{identifier}.json").read_text(encoding="utf-8"))
        class_info = scouter.class_info(profile["class"])
        key = class_info["key"]
        record = data["history"][-1]
        if data.get("class_key") != key or record["input"]["stat"]["myClass"] != key:
            raise ValueError("Scouter class does not match")
        efficiency = record["damage"]["calculatedData"]["specEfficiency"]

        def value(key):
            number = Decimal(str(efficiency[key]))
            if not number.is_finite() or number < 0:
                raise ValueError("Scouter efficiency is unavailable")
            return number

        main = value("mainStateff1")
        if main <= 0:
            raise ValueError("Scouter primary stat efficiency is unavailable")
        primary = Decimal(role_weights(profile["class"])["primary"])
        stats = {
            "Max HP" if class_info[role] == "HP" else class_info[role]: prefix + "Stateff1"
            for role, prefix in (("main", "main"), ("sub", "sub"), ("sub2", "ssub"))
            if class_info.get(role)
        }
        attack = "Attack Power" if classes()[profile["class"]]["att"] == "ATT" else "Magic Attack"
        stats.update({attack: "atkeff1", "All Stats": "allStatEff", "Damage": "dmgeff1", "Boss Damage": "dmgeff1"})
        # FD per stat / FD per primary stat converts each bonus to flat primary
        # stat equivalents. Unrelated stats and the other attack type stay zero.
        # Distinct secondary efficiencies matter (e.g. Dual Blade STR vs DEX).
        weights = dict.fromkeys(STATS, "0")
        weights.update(
            {stat: str((value(key) / main * primary).quantize(Decimal("0.000001"))) for stat, key in stats.items()}
        )
        validated = normalize_score({"class": profile["class"], "weights": weights})
        info.update(
            scouter_weight=validated["weights"]["All Stats"],
            scouter_weights=validated["weights"],
            stat_order=list(stats),
            primary_stat=next(iter(stats)),
            calculated_at=record.get("created"),
        )
        if source == "scouter":
            score = validated
            info["effective_source"] = "scouter"
    except (OSError, ValueError, KeyError, IndexError, TypeError, InvalidOperation):
        # Missing/invalid results never prevent scanning. The UI explains the
        # default fallback; no network requests or guesses about another class.
        pass
    info["weight"] = score["weights"]["All Stats"]
    info["weights"] = score["weights"]
    return score, info


def character_score(profile, identifier=None):
    return scoring(profile, identifier)[0]
