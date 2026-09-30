"""Value deterministic star targets using the character's Scouter efficiencies."""

from starforce import cost, stats


def suggestions(slot, item, weights, gear, settings=None):
    meta = stats.metadata(slot, item)
    reading = item.get("starforce") or {}
    if reading.get("status") != "scanned":
        raise ValueError("Star Force is unread; hover-scan the item to read its stars.")
    current, cap = reading.get("stars"), reading.get("max_stars")
    if type(current) is not int or type(cap) is not int or not 0 <= current <= cap <= 30:
        raise ValueError("Invalid scanned Star Force count; scan again.")
    cap = min(cap, meta["cap"])
    if current >= cap:
        raise ValueError("This item is already at its star limit.")
    if gear["class"] == "Demon Avenger":
        raise ValueError(
            "Demon Avenger's Star Force Conversion HP curve is not yet verified; FD is not ranked."
        )
    # Xenon's conversion caps at 100 total stars. A partial scan is sufficient
    # only when the confirmed subtotal already establishes that the cap is met.
    if gear["class"] == "Xenon":
        total = sum(
            v["starforce"]["stars"]
            for v in gear["equipment"].values()
            if isinstance(v, dict) and (v.get("starforce") or {}).get("status") == "scanned"
        )
        if total < 100:
            raise ValueError(
                "Xenon's conversion needs a complete equipped-star total; fewer than 100 stars are confirmed."
            )
    cfg = cost.options(settings)
    target = current + 1
    delta = stats.gains(meta, current, target)
    gain = sum(weights.get(key, 0) * value for key, value in delta.items())
    if gain <= 0:
        raise ValueError("No positive modeled FD gain from the next star.")
    custom = {**cost.expectations(meta["level"], current, target, cfg), "options": cfg}
    modes = cost.item_modes(item.get("starforce_modes"))
    strategies = [("custom", "Your modes")] if modes else [("mesos", "Least mesos"), ("booms", "Fewest booms")]
    rows = []
    for strategy, label in strategies:
        expected = cost.optimize(
            meta["level"], current, target, cfg, objective="booms" if strategy == "booms" else "mesos", modes=modes
        )
        rows.append(
            {
                "method": "Star Force",
                "kind": "starforce",
                "strategy": strategy,
                "strategy_label": label,
                "current_stars": current,
                "target_stars": target,
                "stat_gains": delta,
                **expected,
                "custom_plan": custom,
                "expected_fd": gain,
                "fd_per_billion": gain / expected["expected_mesos"] * 1e9,
                "current": [f"{current} stars · Lv. {meta['level']}"],
                "goal": f"Reach {target} stars · {label.lower()}",
                "examples": [f"{key}: +{value}" for key, value in delta.items()],
                "protected": [],
                "notes": [
                    f"Uses this item's modes: {cost.mode_summary(modes)}, including recovery after destruction."
                    if modes
                    else "Optimizes the enhancement mode separately at every star, including recovery after destruction.",
                    "Expected booms is the average number of destroyed items before reaching the target. Replacement equipment prices are excluded.",
                    "22★ and above use standard rates; Mode 4 does not prevent destruction there.",
                    *(["30% meso discount included."] if cfg["discount"] else []),
                    *(["30% destruction reduction included through 21★."] if cfg["boom_reduction"] else []),
                ],
            }
        )
    return rows
