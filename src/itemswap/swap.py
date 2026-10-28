"""Combine enabled slot swaps and custom stat groups into one Simulator stat delta."""

from itemswap import catalog
from itemswap.contribution import contribution, number
from scouter import simulator

DUPLICATE_SLOTS = ("ring", "pendant")


def swappable_slots():
    from utils.payload_data import read_payload_json

    layout = read_payload_json("src/flaming_data/equipment_layout.json")["slots"]
    return [s for s in layout if s.split("_")[0] not in catalog.UNSWAPPABLE]


def blocked(class_info):
    if class_info.get("main") == "HP":
        return "Item swap does not support Demon Avenger: HP is the main stat and the Simulator has no HP field."
    return None


def validate_config(config):
    if not isinstance(config, dict) or not isinstance(config.get("slots", {}), dict):
        raise ValueError("Send the item swap as an object with slots and groups")
    if not isinstance(config.get("groups", []), list):
        raise ValueError("Custom stat groups must be a list")
    allowed = set(swappable_slots())
    for slot, entry in config.get("slots", {}).items():
        if slot not in allowed:
            raise ValueError(f"{slot} cannot be swapped")
        if not isinstance(entry, dict) or not all(isinstance(entry.get(k, {}), dict) for k in ("current", "candidate")):
            raise ValueError(f"Invalid {slot} swap")
    for group in config.get("groups", []):
        # Values carry their own sign. "mode" survives only in swaps saved before that change.
        if not isinstance(group, dict) or group.get("mode", "gain") not in ("gain", "lose"):
            raise ValueError("Invalid custom stat group")
        if not isinstance(group.get("name", ""), str) or len(group.get("name", "")) > 80:
            raise ValueError("Custom stat group names must be text up to 80 characters")
        if not isinstance(group.get("fields", {}), dict):
            raise ValueError("Invalid custom stat group")
    return config


def _add(total, part, sign=1):
    for key, value in part.items():
        total[key] = total.get(key, 0.0) + sign * value


def _clean(values):
    return {k: round(v, 6) for k, v in sorted(values.items()) if round(v, 6)}


def _unlisted_without_base(side):
    if side.get("item") != "custom" or not side.get("unlisted") or side.get("no_base"):
        return False
    return not any(number((side.get("custom_base") or {}).get(k), k) for k in (side.get("custom_base") or {}))


def _group_fields(group):
    allowed = {f["key"]: f for f in simulator.fields()}
    result = {}
    for key, value in group.get("fields", {}).items():
        if key not in allowed:
            raise ValueError(f"Unsupported simulator field: {key}")
        amount = number(value, allowed[key]["label"])
        f = allowed[key]
        if not f["min"] <= amount <= f["max"]:
            raise ValueError(f"{group.get('name') or 'Custom group'}: {f['label']} must be between "
                             f"{f['min']} and {f['max']}")
        if amount:
            result[key] = amount
    return result


def _set_hint(slots):
    """Pieces per item set before and after the enabled swaps (hint only; weapons are not counted)."""
    items = catalog.by_id()
    counts = {}
    for entry in slots.values():
        before = items.get((entry.get("current") or {}).get("item"))
        after = items.get((entry.get("candidate") or {}).get("item")) if entry.get("enabled") else before
        for record, index in ((before, 0), (after, 1)):
            if record and record.get("set_label"):
                counts.setdefault(record["set_label"], [0, 0])[index] += 1
    return [{"set": label, "before": b, "after": a} for label, (b, a) in sorted(counts.items()) if b != a]


def _duplicates(slots):
    seen, warnings = {}, []
    names = catalog.by_id()
    for slot, entry in sorted(slots.items()):
        part = slot.split("_")[0]
        if part not in DUPLICATE_SLOTS:
            continue
        side = entry.get("candidate") if entry.get("enabled") else entry.get("current")
        item = (side or {}).get("item")
        if item and item != "custom":
            if (part, item) in seen:
                warnings.append(f"{names[item]['name']} is in both {seen[(part, item)]} and {slot}. "
                                "Check that the game allows wearing two.")
            seen[(part, item)] = slot
    return warnings


def compute(class_info, config):
    """Per-slot and per-group deltas, the combined `changes`, blockers and warnings. Never calls Scouter."""
    validate_config(config)
    result = {"slots": {}, "groups": [], "delta": {}, "changes": {}, "blockers": [], "warnings": [],
              "errors": {}, "set_hint": []}
    reason = blocked(class_info)
    if reason:
        result["blockers"].append(reason)
        return result
    slots = config.get("slots", {})
    total = {}
    for slot, entry in sorted(slots.items()):
        current_parts, candidate_parts = {}, {}
        try:
            current = contribution(class_info, slot, entry.get("current") or {}, current_parts)
            candidate = contribution(class_info, slot, entry.get("candidate") or {}, candidate_parts) if (
                entry.get("candidate") or {}).get("item") else None
        except ValueError as exc:
            result["errors"][slot] = str(exc)
            if entry.get("enabled"):
                result["blockers"].append(f"{slot}: {exc}")
            continue
        delta = {}
        if candidate is not None:
            _add(delta, candidate)
            _add(delta, current, -1)
        result["slots"][slot] = {"enabled": bool(entry.get("enabled")), "current": current,
                                 "candidate": candidate, "delta": _clean(delta),
                                 "parts": {"current": current_parts, "candidate": candidate_parts or None}}
        if not entry.get("enabled"):
            continue
        if candidate is None:
            result["blockers"].append(f"Choose a candidate item for {slot}, or turn its swap off.")
        if _unlisted_without_base(entry.get("current") or {}):
            result["blockers"].append(
                f"Your current {slot} is not in the item list. Enter its base stats or tick "
                "“Continue without base stats”; otherwise the new item's whole base counts as a gain."
            )
        _add(total, delta)
    for group in config.get("groups", []):
        sign = -1 if group.get("mode") == "lose" else 1
        try:
            values = _group_fields(group)
        except ValueError as exc:
            result["errors"][f"group:{group.get('id')}"] = str(exc)
            if group.get("enabled"):
                result["blockers"].append(str(exc))
            continue
        signed = _clean({k: sign * v for k, v in values.items()})
        result["groups"].append({"id": group.get("id"), "name": group.get("name", ""),
                                 "enabled": bool(group.get("enabled")), "delta": signed})
        if group.get("enabled"):
            _add(total, signed)
    result["delta"] = _clean(total)
    try:
        result["changes"] = simulator.validate(result["delta"])
    except ValueError as exc:
        result["blockers"].append(f"Combined change: {exc}")
    if not any(e.get("enabled") for e in slots.values()) and not any(g.get("enabled") for g in config.get("groups", [])):
        result["blockers"].append("Turn on at least one slot swap or custom stat group.")
    result["warnings"] = _duplicates(slots)
    result["set_hint"] = _set_hint(slots)
    return result


def enabled_slots(config):
    return sorted(slot for slot, entry in config.get("slots", {}).items() if entry.get("enabled"))
