"""Hyper stats tab data: defaults, saved settings and the no-network suggestion."""

from hyperstats import optimizer
from scouter import profiles


def record(data, result_id):
    found = next((r for r in data["history"] if r["id"] == result_id), None)
    if found is None or "input" not in found or "damage" not in found:
        raise ValueError("Choose an existing saved calculation")
    return found


def stored(settings):
    """Settings as saved per character; a blank crit rate means "use the scanned value"."""
    cleaned = optimizer.clean({**settings, "crit_rate": 100})
    crit = settings.get("crit_rate")
    if crit is not None:
        crit = optimizer.clean({"keep": [], "crit_rate": crit})["crit_rate"]
    return {
        "levels": cleaned["levels"],
        "keep": sorted(cleaned["keep"]),
        "defense": cleaned["defense"],
        "crit_rate": crit,
    }


def evaluate(info, baseline, settings):
    scanned = optimizer.number(baseline["input"]["stat"].get("critical"))
    crit = scanned if settings.get("crit_rate") is None else settings["crit_rate"]
    calculated = baseline["damage"]["calculatedData"]
    result = optimizer.optimize(info, baseline["input"], calculated, {**settings, "crit_rate": crit})
    return {**result, "scanned_crit_rate": scanned}


def payload(identifier):
    data = profiles.load(identifier)
    info = data["class_info"]
    return {
        "stats": optimizer.table()["stats"],
        "costs": optimizer.table()["costs"],
        "keep": optimizer.default_keep(info),
        "archer": info["name"] in optimizer.ARCHERS,
        "blocked": optimizer.blocked(info),
        "settings": data.get("hyper_stats"),
    }


def parse(request):
    """(result id, normalized settings) from a suggestion or verify request body."""
    if not isinstance(request, dict) or set(request) != {"result_id", "settings"} or not isinstance(
        request["settings"], dict
    ):
        raise ValueError("Choose a saved calculation and enter your hyper stats")
    return request["result_id"], stored(request["settings"])


def optimize(identifier, request):
    """The suggestion for one saved calculation; valid settings are kept for the character."""
    result_id, settings = parse(request)
    data = profiles.load(identifier)
    result = evaluate(data["class_info"], record(data, result_id), settings)
    if data.get("hyper_stats") != settings:
        # The search runs on a snapshot; only the save holds the profile lock.
        with profiles.lock:
            data = profiles.load(identifier)
            data["hyper_stats"] = settings
            profiles.write(identifier, data)
    return result
