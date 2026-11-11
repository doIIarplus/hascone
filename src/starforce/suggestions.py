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
    modes = cost.item_modes(item.get("starforce_modes"))
    wanted = cost.item_target(item.get("starforce_target"))
    # A target at or below the current stars does nothing; one above the cap stops at the cap.
    end = min(wanted, cap) if wanted is not None and wanted > current else current + 1
    clamped = wanted if wanted is not None and wanted > cap else None
    strategies = [("custom", "Your modes")] if modes else [("mesos", "Least mesos"), ("booms", "Fewest booms")]
    rows, previous, stopped = [], {}, None
    for start in range(current, end):
        target = start + 1
        delta = stats.gains(meta, start, target)
        gain = sum(weights.get(key, 0) * value for key, value in delta.items())
        if gain <= 0:
            if start == current:
                raise ValueError("No positive modeled FD gain from the next star.")
            stopped = start
            break
        rows.extend(_step_rows(meta, cfg, modes, strategies, start, target, delta, gain, previous))
    steps = len(rows) // len(strategies)
    chain_target = current + steps
    for row in rows:
        row.update(steps=steps, chain_target=chain_target)
        if wanted is not None and wanted > current + 1:
            row["notes"].append(f"Step {row['step']} of {steps} toward your {wanted}★ target.")
        if clamped is not None:
            row["clamped_from"] = clamped
            row["notes"].append(f"Your {clamped}★ target is above this item's {cap}★ limit; ranked up to {cap}★.")
        if stopped is not None:
            row["notes"].append(f"Stops at {stopped}★: the next star has no positive modeled FD gain.")
        if row["raw_fd_per_billion"] > row["fd_per_billion"]:
            row["notes"].append("Ranked no higher than the previous step, which must be done first.")
    return rows


def _step_rows(meta, cfg, modes, strategies, start, target, delta, gain, previous):
    """One row per strategy for the single star START→TARGET.

    PREVIOUS maps each strategy to the prior step's row and is updated in place. A step's
    ranking score is capped at its predecessor's, so a later star never outranks an earlier one."""
    custom = {**cost.expectations(meta["level"], start, target, cfg), "options": cfg}
    rows = []
    for strategy, label in strategies:
        expected = cost.optimize(
            meta["level"], start, target, cfg, objective="booms" if strategy == "booms" else "mesos", modes=modes
        )
        raw = gain / expected["expected_mesos"] * 1e9
        prior = previous.get(strategy)
        row = {
            "method": "Star Force",
            "kind": "starforce",
            "strategy": strategy,
            "strategy_label": label,
            "current_stars": start,
            "target_stars": target,
            "step": prior["step"] + 1 if prior else 1,
            "requires": f"{prior['current_stars']}→{prior['target_stars']}" if prior else None,
            "stat_gains": delta,
            **expected,
            "custom_plan": custom,
            "expected_fd": gain,
            "raw_fd_per_billion": raw,
            "fd_per_billion": min(raw, prior["fd_per_billion"]) if prior else raw,
            # Steps tied by the cap sort by their first step's cost, so they stay together and in order.
            "rank_mesos": prior["rank_mesos"]
            if prior and raw >= prior["fd_per_billion"]
            else expected["expected_mesos"],
            "current": [f"{start} stars · Lv. {meta['level']}"],
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
        previous[strategy] = row
        rows.append(row)
    return rows
