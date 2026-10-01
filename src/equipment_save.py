"""Store equipment readings and their icons.

Needs no image library: icons arrive as PNG bytes, cut by equipment_scan.icons
in the scanner process from the frame that was read.
"""


def _save_equipment_grid(profile, result, icons, folder):
    from scouter import profiles
    from utils.image_files import write_bytes

    old, equipment = profile["equipment"], {}
    for slot, reading in result["slots"].items():
        prior = old.get(slot, {})
        equipment[slot] = dict(prior) if prior.get("icon_hash") == reading["icon_hash"] else {}
        equipment[slot].update(occupied=True, icon_hash=reading["icon_hash"])
        if slot in icons:
            write_bytes(folder / (slot + ".png"), icons[slot])
    profile.update(equipment=equipment, equipment_captured=profiles.now())


def _save_hover_item(profile, result, icons, folder):
    from scouter import profiles
    from utils.image_files import write_bytes

    slot = result["slot"]
    prior = profile["equipment"].get(slot, {})
    icon_path = folder / (slot + ".png")
    if slot in icons and (not icon_path.exists() or prior.get("name", result["item"]) != result["item"]):
        write_bytes(icon_path, icons[slot])
    item = (
        dict(prior)
        if prior.get("name", result["item"]) == result["item"]
        else {k: v for k, v in prior.items() if k in ("occupied", "icon_hash")}
    )
    item.update({k: v for k, v in result.items() if k not in ("kind", "errors", "slot", "slot_verified", "readings", "item")})
    item.update(name=result["item"], updated=profiles.now(), hover_scanned=True)
    if result.get("flameable") is False:
        item.pop("stats", None)
    if result.get("cubeable") is False:
        item.pop("potential", None)
    if item.get("potential"):
        item["potential"]["scanned_at"] = profiles.now()
    if not item.get("required_level"):
        from cubing.item_database import metadata

        meta = metadata(item["name"], slot)
        if meta:
            item["required_level"] = meta["level"]
    if "stats" in item and item.get("flameable") is not False:
        item["status"] = "scanned"
    profile["equipment"][slot] = item


def _save_weapon_attack(profile, result):
    from scouter import profiles

    info = profiles.load(profile["id"])["class_info"]
    value = result["weapon_attack"].get("MATT" if info["main"] == "INT" else "ATT")
    if value is not None:
        profiles.save_scan(
            profile["id"], {"stat.weaponAtk": {"value": str(value), "confidence": 1}}, [], profiles.now()
        )


def _save_ring_level(profile, result):
    from scouter import profiles

    key = {
        "Continuous Ring": "continuosRing",
        "Ring of Restraint": "restraintRing",
        "Weapon Jump Ring": "weaponRing",
    }[result["item"]]
    profiles.save_scan(
        profile["id"], {"special." + key: {"value": str(result["ring_level"]), "confidence": 1}}, [], profiles.now()
    )


def save(profile, result, icons):
    """Save RESULT to PROFILE; ICONS maps slots to PNG bytes (equipment_scan.icons)."""
    from flaming import characters

    icons = icons or {}
    folder = characters.PROFILE_DIR / profile["id"]
    folder.mkdir(parents=True, exist_ok=True)
    if result["kind"] == "equipment":
        _save_equipment_grid(profile, result, icons, folder)
    else:
        _save_hover_item(profile, result, icons, folder)
    characters.write(profile)
    if result.get("weapon_attack"):
        _save_weapon_attack(profile, result)
    if result.get("ring_level"):
        _save_ring_level(profile, result)
