"""Upgrade kinds a player has chosen to leave out of an item slot's recommendations."""

KINDS = ("flame", "cube", "starforce")

# Settings the player made on a slot; scans must carry them over to a rescanned or replaced item.
PRESERVED = ("skip_upgrades", "starforce_modes")


def normalize(value):
    """Sorted unique KINDS from a request, or [] when nothing is skipped."""
    if not isinstance(value, list) or any(kind not in KINDS for kind in value):
        raise ValueError("Choose flame, cube or starforce")
    return sorted(set(value), key=KINDS.index)


def skipped(item, kind):
    return kind in (item.get("skip_upgrades") or ())
