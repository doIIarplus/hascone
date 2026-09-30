"""Recover possible individual flame lines from saved summed bonus stats."""

from functools import lru_cache

from flaming import item_database as db


def breakdown(item, slot):
    stats = tuple(sorted((s["name"], s["value"]) for s in item.get("stats", []) if s["value"]))
    return _breakdown(item.get("name", ""), slot, stats)


def legacy(item, slot):
    """Why a saved flame cannot be rolled on this item today, or None.

    Transposed items (e.g. old Sweetwater transfers) kept flame tiers above
    what the item rolls now; re-flaming can never restore or match them."""
    result = breakdown(item, slot)
    return result["message"] if result.get("legacy") else None


def _options(catalog, table, target, top):
    candidates = []
    for index, line in enumerate(table):
        if not all(stat in target for stat in line["stats"]):
            continue
        for tier, value in line["tiers"].items():
            if int(tier) > top:
                continue
            if all(0 < abs(value) <= abs(target[stat]) and value * target[stat] > 0 for stat in line["stats"]):
                candidates.append((index, {"stats": line["stats"], "tier": int(tier), "value": value, "percent": line["percent"]}))
    options = []

    def search(start, remaining, lines):
        if not any(remaining.values()):
            if lines and (not catalog["flame_advantaged"] or len(lines) == 4):
                options.append(lines)
            return
        if len(lines) == 4 or len(options) >= 2:
            return
        for pos in range(start, len(candidates)):
            index, line = candidates[pos]
            if lines and index <= lines[-1][0]:
                continue
            if all(abs(remaining.get(s, 0)) >= abs(line["value"]) for s in line["stats"]):
                rest = dict(remaining)
                for stat in line["stats"]:
                    rest[stat] -= line["value"]
                search(pos + 1, rest, lines + [(index, line)])
                if len(options) >= 2:
                    return

    search(0, target, [])
    return [[line for _, line in option] for option in options]


@lru_cache(maxsize=256)
def _breakdown(name, slot, stats):
    catalog = db.lookup(name, slot)
    if not catalog or not catalog["flameable"]:
        return {"options": [], "message": "Verified flame metadata is unavailable for this item."}
    target = dict(stats)
    try:
        table = db.line_table(catalog, tiers=range(1, 8))
        top = max(map(int, db.tier_distribution(catalog)))
    except ValueError as exc:
        return {"options": [], "message": str(exc)}
    options = _options(catalog, table, target, 7)
    if options and not _options(catalog, table, target, top):
        highest = min(max(line["tier"] for line in option) for option in options)
        return {"options": options, "legacy": True,
                "message": f"Legacy flame: its tier {highest} lines exceed the tier {top} maximum this item rolls now "
                           "(e.g. a transposed item). Re-flaming cannot restore it, so it is not priced."}
    return {"options": options,
            "message": ("Possible tier breakdowns inferred from summed stats; the original roll is ambiguous."
                        if len(options) > 1 else "Tier breakdown inferred from saved bonus stats."
                        if options else "These totals do not match a supported tier breakdown. Check the saved flame stats.")}
