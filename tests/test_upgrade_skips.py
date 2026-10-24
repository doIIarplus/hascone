import pytest
from test_app import ID, client, get, post  # noqa: F401
from test_equipment_scan import frame, replay

import enhancement_analysis
import upgrade_skips
from equipment_save import save
from equipment_scan import grid, hover, icons
from flaming import characters
from scouter import suggestions


def test_normalize_validates_and_orders():
    assert upgrade_skips.normalize([]) == []
    assert upgrade_skips.normalize(["starforce", "flame", "flame"]) == ["flame", "starforce"]
    for bad in ("flame", None, ["flames"], [1], {"flame": True}):
        with pytest.raises(ValueError):
            upgrade_skips.normalize(bad)


def test_route_saves_and_clears(client):
    p = characters.load(ID)
    p["equipment"]["hat"] = {"name": "Hat"}
    characters.write(p)
    path = f"/api/characters/{ID}/equipment/hat/skip-upgrades"
    assert post(client, path, {"skip": ["starforce", "flame"]}).status_code == 200
    assert characters.load(ID)["equipment"]["hat"]["skip_upgrades"] == ["flame", "starforce"]
    assert post(client, path, {"skip": ["pet"]}).status_code == 400
    assert post(client, path, {"skip": []}).status_code == 200
    assert "skip_upgrades" not in characters.load(ID)["equipment"]["hat"]
    assert post(client, f"/api/characters/{ID}/equipment/top/skip-upgrades", {"skip": ["flame"]}).status_code == 400


def test_slot_kinds_leave_out_only_skipped_kinds():
    layout = {"hat": {}}
    item = {"name": "Hat", "starforce": {"status": "scanned"}}
    assert list(suggestions._slot_kinds("hat", item, layout)) == ["flame", "cube", "starforce"]
    item["skip_upgrades"] = ["cube", "starforce"]
    assert list(suggestions._slot_kinds("hat", item, layout)) == ["flame"]


def test_skip_settings_survive_rescan_and_replacement(client):
    settings = {"skip_upgrades": ["flame"], "starforce_modes": {str(s): 1 for s in range(15, 22)}}
    save(characters.load(ID), grid(frame("grid")), icons(frame("grid"), grid(frame("grid"))))
    result = hover(frame("hat"), replay, "hat")
    save(characters.load(ID), result, icons(frame("hat"), result))
    p = characters.load(ID)
    p["equipment"]["hat"].update(settings)
    characters.write(p)
    # Rescanning the same item keeps them.
    save(characters.load(ID), result, icons(frame("hat"), result))
    assert {k: characters.load(ID)["equipment"]["hat"][k] for k in settings} == settings
    # A different item in the slot (new name, then new icon in the grid) keeps them too.
    save(characters.load(ID), {**result, "item": "Another Hat"}, {})
    hat = characters.load(ID)["equipment"]["hat"]
    assert hat["name"] == "Another Hat" and {k: hat[k] for k in settings} == settings
    p = characters.load(ID)
    p["equipment"]["hat"]["icon_hash"] = "old"
    characters.write(p)
    save(characters.load(ID), grid(frame("grid")), {})
    assert {k: characters.load(ID)["equipment"]["hat"][k] for k in settings} == settings


def test_flame_order_drops_skipped_flame_but_costs_keep_it(client):
    p = characters.load(ID)
    result = hover(frame("hat"), replay, "hat")
    save(p, grid(frame("grid")), {})
    save(characters.load(ID), result, {})
    p = characters.load(ID)
    plain = enhancement_analysis.snapshot(p)
    assert any(r["slot"] == "hat" for r in plain["flame_order"])
    p["equipment"]["hat"]["skip_upgrades"] = ["flame"]
    skipped = enhancement_analysis.snapshot(p)
    assert all(r["slot"] != "hat" for r in skipped["flame_order"])
    assert [r["slot"] for r in skipped["flame_costs"]] == [r["slot"] for r in plain["flame_costs"]]
    assert skipped["totals"] == plain["totals"]
