"""Upgrade odds and current-equipment replacement costs."""

import json
import threading
from functools import lru_cache

import zero
from cubing.item_database import item_metadata
from cubing.scoring import current_score
from cubing.targets import SLOTS
from flaming import item_database
from flaming.breakdown import legacy as legacy_flame
from flaming.character_score import character_score
from flaming.probability import improvement
from flaming.score import flame_score
from flaming.vision import Stat
from utils.payload_data import read_payload_json

PRICES = {"Bright": 22_000_000, "Glowing": 12_000_000}
_lock = threading.Lock()


def _inputs(profile):
    from cubing.character_score import scoring
    cube_score, attack_score, _ = scoring(profile)
    from scouter import profiles as scouter_profiles
    from starforce.cost import options
    saved = scouter_profiles.DIRECTORY / f"{profile.get('id') or profile.get('source_character')}.json"
    sf_options = options(json.loads(saved.read_text(encoding="utf-8")).get("starforce_options") if saved.exists() else None)
    encoded = json.dumps({
        "profile": {"class": profile["class"], "equipment": profile["equipment"]},
        "flame_score": character_score(profile),
        "starforce_options": sf_options,
        "cube_score": cube_score,
        "attack_score": attack_score,
    }, sort_keys=True)
    return encoded


def snapshot(profile):
    encoded = _inputs(profile)
    # Serialize cold distribution builds; repeated UI reads reuse this snapshot.
    with _lock:
        return json.loads(_cached(encoded))


def gear_value(profile):
    """The combined cost of the character's current gear, and whether any item is unpriced."""
    encoded = _inputs(profile)
    with _lock:
        return dict(_value(encoded))


@lru_cache(maxsize=64)
def _value(encoded):
    data = json.loads(_cached(encoded))
    return (("mesos", data["totals"]["Combined"]), ("partial", any(row["missing"] for row in data["combined_costs"])))


def _add_starforce_row(result, detail, common, slot, item, options_config):
    reading = item.get("starforce") or {}
    from starforce import cost as sf_cost
    from starforce import stats as sf_stats

    if slot.split("_")[0] in sf_stats.EXCLUDED_SLOTS or reading.get("status") == "not_applicable":
        return
    try:
        if reading.get("status") != "scanned":
            raise ValueError("Hover this item to scan its stars first.")
        meta = sf_stats.metadata(slot, item)
        cap = min(meta["cap"], reading.get("max_stars") or meta["cap"])
        detail["starforce_mode_table"] = sf_cost.mode_table(meta["level"], options_config, cap)
        stars = reading.get("stars")
        if type(stars) is not int or not 0 <= stars <= meta["cap"]:
            raise ValueError("Invalid or unsupported scanned star count.")
        estimate = (
            sf_cost.optimize(meta["level"], 0, stars, options_config, modes=sf_cost.item_modes(item.get("starforce_modes")))
            if stars
            else {"expected_mesos": 0, "expected_rolls": 0, "expected_booms": 0}
        )
        row = {**common, "stars": stars, "level": meta["level"], "modes": item.get("starforce_modes"), **estimate}
        result["starforce_costs"].append(row)
        detail["starforce_current"] = row
        result["totals"]["Star Force"] += row["expected_mesos"]
    except (ValueError, KeyError, TypeError) as exc:
        detail["starforce_error"] = str(exc)
        detail["starforce_fixed"] = isinstance(exc, sf_stats.FixedStars)
        result["unpriced"]["starforce"].append({**common, "reason": str(exc)})


def _add_flame_row(result, detail, common, slot, item, layout, flame_weights):
    if not item.get("flameable", layout[slot].get("flameable", True)):
        return
    try:
        if not isinstance(item.get("stats"), list):
            raise ValueError("Scan this item's flame stats first.")
        baseline = flame_score([Stat(**s) for s in item["stats"]], flame_weights)
        detail["flame_score"] = float(baseline)
        catalog = item_database.lookup(item.get("name"), slot)
        if catalog is None:
            raise ValueError("Flame level and advantage metadata are unknown.")
        if note := legacy_flame(item, slot):
            raise ValueError(note)
        detail["catalog"] = {k: catalog[k] for k in ("level", "flame_advantaged")}
        upgrade = improvement(catalog, baseline, flame_weights)
        current = improvement(catalog, baseline, flame_weights, inclusive=True)
        detail.update(flame_upgrade=upgrade, flame_current=current)
        result["flame_order"].append({**common, "score": float(baseline), **detail["catalog"], **upgrade})
        if current["expected_mesos"] is None:
            raise ValueError("Current flame is outside the published roll table.")
        result["flame_costs"].append({**common, "score": float(baseline), **current})
        result["totals"]["Black Flame"] += current["expected_mesos"]
    except (ValueError, KeyError, TypeError) as exc:
        detail["flame_error"] = str(exc)
        result["unpriced"]["flame"].append({**common, "reason": str(exc)})


def _add_cube_row(result, detail, common, slot, item, character_class, cube_score, attack_score):
    if slot not in SLOTS or item.get("cubeable") is False:
        return
    try:
        level = (item_metadata(slot, item) or {}).get("level")
        score = current_score(slot, character_class, item.get("potential"), cube_score, attack_score, level)
        detail["potential"] = score
        estimate = score.get("current_cost", {})
        if score.get("unavailable") or estimate.get("unavailable"):
            raise ValueError(score.get("unavailable") or estimate["unavailable"])
        cubes = [
            {
                **row,
                "expected_mesos": row["expected_cubes"] * PRICES[row["cube"]]
                if row["expected_cubes"] is not None
                else None,
            }
            for row in estimate["cubes"]
        ]
        detail["cube_current"] = cubes
        if any(row["expected_mesos"] is None for row in cubes):
            raise ValueError("Current potential has no matching outcome in the published tables.")
        result["cube_costs"].append(
            {**common, "value": score["value"], "label": score["label"], "cubes": cubes, "notes": estimate.get("notes", [])}
        )
        for row in cubes:
            result["totals"][row["cube"]] += row["expected_mesos"]
    except (ValueError, KeyError, TypeError) as exc:
        detail["cube_error"] = str(exc)
        result["unpriced"]["cube"].append({**common, "reason": str(exc)})


def _add_combined_row(result, detail, common):
    """Star Force + flame + cheaper cube cost to rebuild this item as scanned."""
    parts, missing = {}, []
    if "starforce_current" in detail:
        parts["Star Force"] = detail["starforce_current"]["expected_mesos"]
    elif "starforce_error" in detail and not detail["starforce_fixed"]:
        # Fixed-star weapons have nothing left to buy, so they do not make the total partial.
        missing.append("Star Force: " + detail["starforce_error"])
    if detail.get("flame_current", {}).get("expected_mesos") is not None and "flame_error" not in detail:
        parts["Flames"] = detail["flame_current"]["expected_mesos"]
    elif "flame_error" in detail:
        missing.append("Flames: " + detail["flame_error"])
    if "cube_current" in detail and "cube_error" not in detail:
        cheapest = min(detail["cube_current"], key=lambda row: row["expected_mesos"])
        parts["Cubes"] = cheapest["expected_mesos"]
        detail["cube_cheapest"] = cheapest["cube"]
    elif "cube_error" in detail:
        missing.append("Potential: " + detail["cube_error"])
    if not parts and not missing:
        return
    combined = {"parts": parts, "missing": missing, "expected_mesos": sum(parts.values())}
    detail["combined"] = combined
    result["combined_costs"].append({**common, **combined})
    result["totals"]["Combined"] += combined["expected_mesos"]


def _sorted_result(result):
    result["combined_costs"].sort(key=lambda r: (r["expected_mesos"], r["slot"]))
    result["starforce_costs"].sort(key=lambda r: (r["expected_mesos"], r["slot"]))
    result["flame_order"].sort(key=lambda r: (-r["probability"], r["slot"]))
    result["flame_costs"].sort(key=lambda r: (r["expected_mesos"], r["slot"]))
    result["cube_costs"].sort(key=lambda r: (r["cubes"][0]["expected_mesos"], r["slot"]))
    return result


@lru_cache(maxsize=64)
def _cached(encoded):
    data = json.loads(encoded)
    profile = data["profile"]
    layout = read_payload_json("src/flaming_data/equipment_layout.json")["slots"]
    result = {
        "items": {},
        "flame_order": [],
        "flame_costs": [],
        "cube_costs": [],
        "starforce_costs": [],
        "combined_costs": [],
        "starforce_options": data["starforce_options"],
        "totals": {"Black Flame": 0, "Bright": 0, "Glowing": 0, "Star Force": 0, "Combined": 0},
        "unpriced": {"flame": [], "cube": [], "starforce": []},
    }
    for slot, item in profile["equipment"].items():
        if not item or slot not in layout:
            continue
        common = {"slot": slot, "name": item.get("name") or slot.replace("_", " ")}
        detail = result["items"][slot] = {}
        if zero.mirrored(profile["class"], slot):
            detail["mirror"] = zero.MIRROR_NOTE
            continue
        _add_starforce_row(result, detail, common, slot, item, data["starforce_options"])
        _add_flame_row(result, detail, common, slot, item, layout, data["flame_score"])
        _add_cube_row(result, detail, common, slot, item, profile["class"], data["cube_score"], data["attack_score"])
        _add_combined_row(result, detail, common)
    return json.dumps(_sorted_result(result), allow_nan=False)
