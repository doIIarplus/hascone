"""Character-specific potential weights from saved Scouter percentage efficiencies."""
import json
import math

from cubing import profiles


def scoring(profile):
    from flaming import characters
    from scouter import profiles as scouter
    job = profile["class"]
    score, attack = profiles.score(job), profiles.attack_score(job)
    from cubing.probability import family
    manual = {"stats": family("MAIN_EQ", {"score": score}), "boss_per_attack": attack["boss_per_attack"]}
    info = {"manual_weights": manual, "source": profile.get("potential_weight_source", "default"),
            "effective_source": "default", "scouter_weights": None,
            "calculated_at": None, "reason": "Calculate Scouter for this character first."}
    try:
        identifier = profile.get("id") or profile.get("source_character")
        characters.portrait_path(identifier)
        data = json.loads((scouter.DIRECTORY / f"{identifier}.json").read_text(encoding="utf-8"))
        role = scouter.class_info(job)
        record = data["history"][-1]
        if data.get("class_key") != role["key"] or record["input"]["stat"]["myClass"] != role["key"]:
            raise ValueError("Saved Scouter calculation belongs to a different class.")
        efficiencies = record["damage"]["calculatedData"]["specEfficiency"]
        def value(key, positive=False):
            if isinstance(efficiencies[key], bool):
                raise ValueError("Recalculate Scouter: percentage efficiencies are unavailable.")
            number = float(efficiencies[key])
            if not math.isfinite(number) or number < 0 or (positive and number == 0):
                raise ValueError("Recalculate Scouter: percentage efficiencies are unavailable.")
            return number
        main = value("mainStatPereff1", True)
        stat_weights = {}
        for name, prefix in (("main", "main"), ("sub", "sub"), ("sub2", "ssub")):
            if role.get(name):
                stat = "Max HP" if role[name] == "HP" else role[name]
                stat_weights[stat] = value(prefix + "StatPereff1") / main
        derived = {"class": job, "secondary_weight": value("subStatPereff1") / main,
                   "all_stat_weight": value("allStatEff") / main, "stat_weights": stat_weights}
        derived_attack = {"boss_per_attack": value("atkPereff1", True) / value("dmgeff1", True)}
        from cubing.targets import validate_spec
        validate_spec("hat", {"rank":"Rare","item_level":None,"rules":[],"score":derived,"attack_score":derived_attack}, job)
        info.update(scouter_weights={"score":derived,"attack_score":derived_attack},
                    calculated_at=record.get("created"), reason=None)
        if info["source"] == "scouter":
            score, attack = derived, derived_attack
            info["effective_source"] = "scouter"
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        pass
    info.update(score=score, attack_score=attack)
    return score, attack, info
