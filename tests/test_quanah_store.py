import pytest
from test_app import BASE, client, get, post  # noqa: F401  (client is a fixture)

import app
from quanah import store


@pytest.fixture(autouse=True)
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PATH", tmp_path / "quanah.json")


def put(client, path, body):
    return client.put(path, json=body, base_url=BASE, headers={"X-Hascone-Token": app.TOKEN})


def delete(client, path):
    return client.delete(path, base_url=BASE, headers={"X-Hascone-Token": app.TOKEN})


def test_pieces_need_a_class_first():
    with pytest.raises(ValueError, match="class"):
        store.add_item("hat", ["dl"])
    assert store.payload()["solution"] is None


def test_line_rules():
    store.configure("warrior")
    for lines, message in [([], "1 to 3"), (["dl", "wh", "reg", "atk"], "1 to 3"),
                           (["dl", "dl"], "same line"), (["nope"], "Unknown")]:
        with pytest.raises(ValueError, match=message):
            store.add_item("hat", lines)
    with pytest.raises(ValueError, match="slot"):
        store.add_item("weapon", ["dl"])
    # Unrecognized lines may repeat.
    assert store.add_item("hat", ["other", "other", "dl"])["lines"] == ["other", "other", "dl"]


def test_duplicates_ignore_line_order_but_not_slot():
    store.configure("warrior")
    a = store.add_item("hat", ["dl", "wh", "reg"])["id"]
    b = store.add_item("hat", ["reg", "dl", "wh"])["id"]
    c = store.add_item("top", ["dl", "wh", "reg"])["id"]
    d = store.add_item("hat", ["dl", "wh"])["id"]
    flags = {i["id"]: i["duplicate"] for i in store.payload()["items"]}
    assert flags == {a: True, b: True, c: False, d: False}


def test_other_class_pieces_are_flagged_and_used_as_transfers():
    store.configure("warrior")
    mine = store.add_item("hat", ["dl", "wh", "reg"], item_class="warrior", source="scan")["id"]
    theirs = store.add_item("top", ["dl", "wh", "reg"], item_class="bowman", source="scan")["id"]
    data = store.payload()
    wearable = {i["id"]: i["wearable"] for i in data["items"]}
    assert wearable == {mine: True, theirs: False}
    # The bowman top's lines can be orbed onto a warrior top, so it still counts.
    assert data["solution"]["picks"]["hat"] == mine and data["solution"]["picks"]["top"] == theirs
    # Switching class flips which piece needs the transfer.
    store.configure("bowman")
    solution = store.payload()["solution"]
    assert solution["picks"]["hat"] == mine and solution["picks"]["top"] == theirs


def test_a_hand_entered_piece_can_be_given_another_class_and_edited_later(client):
    store.configure(class_key="warrior")
    api = post(client, "/api/quanah/items", {"slot": "hat", "lines": ["dl"], "item_class": "bowman"}).get_json()
    piece = next(i for i in api["items"] if i["slot"] == "hat")
    assert piece["item_class"] == "bowman" and not piece["wearable"]
    # Left out, it defaults to the selected class.
    api = post(client, "/api/quanah/items", {"slot": "top", "lines": ["dl"]}).get_json()
    assert next(i for i in api["items"] if i["slot"] == "top")["item_class"] == "warrior"
    api = put(client, "/api/quanah/items/" + piece["id"], {"slot": "hat", "lines": ["dl"], "item_class": "warrior"}).get_json()
    assert next(i for i in api["items"] if i["id"] == piece["id"])["wearable"]
    with pytest.raises(ValueError):
        store.add_item("hat", ["dl"], item_class="nope")
    with pytest.raises(ValueError):
        store.update_item(piece["id"], "hat", ["dl"], "nope")


def test_one_preferred_piece_per_slot_locks_the_set():
    store.configure("warrior")
    best = store.add_item("hat", ["dl", "wh", "reg"])["id"]
    liked = store.add_item("hat", ["dl"])["id"]
    other = store.add_item("hat", ["wh"])["id"]
    assert store.payload()["solution"]["picks"]["hat"] == best
    store.mark_item(liked, "preferred", True)
    store.mark_item(other, "preferred", True)
    data = store.payload()
    assert {i["id"]: i["preferred"] for i in data["items"]} == {best: False, liked: False, other: True}
    assert data["solution"]["picks"]["hat"] == other
    store.mark_item(other, "preferred", False)
    assert store.payload()["solution"]["picks"]["hat"] == best
    with pytest.raises(ValueError, match="true or false"):
        store.mark_item(best, "preferred", "yes")
    with pytest.raises(ValueError, match="already gone"):
        store.mark_item("nope", "preferred", True)


def test_worn_piece_sets_the_orb_cost_of_its_slot():
    store.configure("warrior")
    worn = store.add_item("hat", ["dl"])["id"]
    mine = store.add_item("hat", ["wh"])["id"]
    store.configure(build={"preset": "custom", "targets": {"dl": 1}})
    costs = lambda: {i["id"]: i["transfer"] for i in store.payload()["items"]}  # noqa: E731
    assert costs() == {worn: False, mine: False}
    store.mark_item(worn, "worn", True)
    assert costs() == {worn: False, mine: True}
    with pytest.raises(ValueError, match="Unknown mark"):
        store.mark_item(worn, "loved", True)


def test_disabled_pieces_are_left_out_of_every_combo():
    store.configure("warrior")
    best = store.add_item("hat", ["dl", "wh", "reg"])["id"]
    other = store.add_item("hat", ["dl"])["id"]
    store.configure(build={"preset": "custom", "targets": {"dl": 1, "wh": 1, "reg": 1}})
    store.mark_item(best, "disabled", True)
    store.mark_item(other, "disabled", True)
    data = store.payload()
    # Any number of pieces in a slot can be disabled; they stay listed.
    assert {i["id"]: i["disabled"] for i in data["items"]} == {best: True, other: True}
    assert data["solution"]["picks"]["hat"] is None
    store.mark_item(best, "disabled", False)
    assert store.payload()["solution"]["picks"]["hat"] == best


def test_disabling_a_starred_piece_unstars_it_and_starring_enables_it():
    store.configure("warrior")
    piece = store.add_item("hat", ["dl"])["id"]
    store.mark_item(piece, "preferred", True)
    store.mark_item(piece, "disabled", True)
    assert {k: store.read()["items"][0].get(k) for k in ("preferred", "disabled")} == {"preferred": None,
                                                                                      "disabled": True}
    store.mark_item(piece, "preferred", True)
    assert {k: store.read()["items"][0].get(k) for k in ("preferred", "disabled")} == {"preferred": True,
                                                                                      "disabled": None}


def test_the_gandi_build_is_read_back_as_hybrid():
    store.PATH.parent.mkdir(parents=True, exist_ok=True)
    store.PATH.write_text('{"class": "thief", "build": {"preset": "gandi", "job_mode": "any"}, "items": []}',
                          encoding="utf-8")
    assert store.read()["build"]["preset"] == "hybrid"


def test_moving_a_preferred_piece_drops_the_preference():
    store.configure("warrior")
    liked = store.add_item("hat", ["dl"])["id"]
    store.mark_item(liked, "preferred", True)
    store.update_item(liked, "hat", ["wh"])
    assert store.read()["items"][0]["preferred"] is True
    store.update_item(liked, "top", ["wh"])
    assert "preferred" not in store.read()["items"][0]


def test_build_validation():
    store.configure(build={"preset": "custom", "targets": {"dl": 3, "wh": 0}})
    assert store.read()["build"]["targets"] == {"dl": 3}
    for build, message in [({"preset": "nope"}, "Unknown build"), ({"targets": {"dl": 4}}, "0 to 3"),
                           ({"targets": {"zz": 1}}, "Unknown custom"), ({"jobs": ["thief", "thief"]}, "jobs"),
                           ({"job_mode": "random"}, "job mode")]:
        with pytest.raises(ValueError, match=message):
            store.configure(build=build)
    with pytest.raises(ValueError, match="Warrior"):
        store.configure("archer")


def test_api_round_trip(client):
    assert get(client, "/api/quanah").json["class"] is None
    assert post(client, "/api/quanah/items", {"slot": "hat", "lines": ["dl"]}).status_code == 400
    data = put(client, "/api/quanah/settings", {"class": "thief", "build": {"preset": "eu"}}).json
    assert data["class"] == "thief" and data["solution"]["goal"] == 18
    data = post(client, "/api/quanah/items", {"slot": "hat", "lines": ["dl", "wh", "dmg"]}).json
    assert data["solution"]["score"] == 3
    piece = data["items"][0]["id"]
    assert put(client, f"/api/quanah/items/{piece}/preferred", {"preferred": True}).json["items"][0]["preferred"]
    assert put(client, f"/api/quanah/items/{piece}/preferred", {}).status_code == 400
    assert put(client, f"/api/quanah/items/{piece}/worn", {"worn": True}).json["items"][0]["worn"]
    assert put(client, f"/api/quanah/items/{piece}/disabled", {"disabled": True}).json["solution"]["score"] == 0
    assert put(client, f"/api/quanah/items/{piece}/loved", {"loved": True}).status_code == 400
    assert delete(client, f"/api/quanah/items/{piece}").json["items"] == []
    assert delete(client, f"/api/quanah/items/{piece}").status_code == 400
    post(client, "/api/quanah/items", {"slot": "cape", "lines": ["crit"]})
    assert delete(client, "/api/quanah/items").json["items"] == []


def test_custom_builds_hold_at_most_18_lines():
    full = {"dl": 3, "wh": 3, "reg": 3, "atk": 3, "crit": 3, "dmg": 3}
    assert store.configure(build={"preset": "custom", "targets": full})["build"]["targets"] == full
    with pytest.raises(ValueError, match="at most 18 lines"):
        store.configure(build={"preset": "custom", "targets": {**full, "warrior": 1}})
    # A file saved before the cap is trimmed when solved, so it can't make the solver crawl.
    store.PATH.write_text('{"class": "warrior", "build": {"preset": "custom", "targets": '
                          '{"dl": 3, "wh": 3, "reg": 3, "atk": 3, "crit": 3, "dmg": 3, "warrior": 3, "pirate": 3}}}',
                          encoding="utf-8")
    assert store.payload()["solution"]["goal"] == 18
    # The page sees the same trimmed targets, and the build can still be changed.
    assert sum(store.read()["build"]["targets"].values()) == 18
    assert store.configure(build={"preset": "skill"})["build"]["preset"] == "skill"


def test_a_saved_original_build_opens_as_skill():
    store.PATH.write_text('{"class": "warrior", "build": {"preset": "original"}, "items": []}', encoding="utf-8")
    assert store.read()["build"]["preset"] == "skill"
    assert store.payload()["solution"]["goal"] == 18


def test_edit_a_piece():
    store.configure("warrior")
    scanned = store.add_item("top", ["atk", "crit", "other"], raw=["…", "…", "[Hologram] Bowman Attack Skill"],
                             item_class="warrior", source="scan")
    edited = store.update_item(scanned["id"], "top", ["atk", "crit", "bowman"])
    assert edited["lines"] == ["atk", "crit", "bowman"] and edited["edited"]
    # What the scanner read and where the piece came from are kept.
    assert edited["source"] == "scan" and edited["raw"] == scanned["raw"]
    assert store.update_item(scanned["id"], "cape", ["dl"])["slot"] == "cape"
    for args, message in [(("nope", "top", ["dl"]), "gone"), ((scanned["id"], "ring", ["dl"]), "slot"),
                          ((scanned["id"], "top", ["dl", "dl"]), "same line")]:
        with pytest.raises(ValueError, match=message):
            store.update_item(*args)


def test_saved_scans_are_rematched_but_edits_are_kept():
    store.configure("warrior")
    level = "[Hologram] Warrior Attack Skill Level Lv. +1"
    # As saved by the first reader, which did not know the "Skill Level" wording.
    misread = store.add_item("bottom", ["other"], raw=[level], item_class="warrior", source="scan")
    edited = store.add_item("top", ["other"], raw=[level], item_class="warrior", source="scan")
    store.update_item(edited["id"], "top", ["pirate"])
    manual = store.add_item("hat", ["other"])
    lines = {i["id"]: i["lines"] for i in store.read()["items"]}
    assert lines == {misread["id"]: ["warrior"], edited["id"]: ["pirate"], manual["id"]: ["other"]}


def test_rematch_never_makes_an_invalid_piece():
    from quanah.lines import rematch

    assert rematch(["White Hole Lv. +1", "White Hole Lv. +1"]) is None
    assert rematch([]) is None and rematch(None) is None
    assert rematch(["Boss Damage +10%", "White Hole Lv. +1"]) == ["other", "wh"]


def test_edit_through_the_api(client):
    put(client, "/api/quanah/settings", {"class": "warrior"})
    piece = post(client, "/api/quanah/items", {"slot": "hat", "lines": ["dl"]}).json["items"][0]["id"]
    data = put(client, f"/api/quanah/items/{piece}", {"slot": "hat", "lines": ["dl", "wh"]}).json
    assert data["items"][0]["lines"] == ["dl", "wh"] and data["solution"]["score"] == 2


@pytest.mark.parametrize("message, kept", [
    ("Couldn't read the item name", 1),
    # Another item is expected while hovering; it is not kept as a failure.
    ("Skipped HYPER BURNING MAX: not a Quanah piece", 0),
])
def test_only_real_failures_are_kept_for_diagnosis(tmp_path, monkeypatch, message, kept):
    import numpy as np

    import ocr_worker
    from flaming.stats import ReadError

    modes = []

    def fail(frame, mode):
        modes.append(mode)
        raise ReadError(message)

    monkeypatch.setattr(ocr_worker, "read", fail)
    monkeypatch.setattr(app, "QUANAH_FAILED", tmp_path / "failed")
    with pytest.raises(ReadError, match=f"^{message}$"):
        app._save_quanah_piece(np.zeros((10, 10, 3), np.uint8), (1, 2))
    assert len(list((tmp_path / "failed").glob("*.png"))) == kept
    # The tooltip chosen at capture time travels with the frame.
    assert modes == ["quanah:1:2"]


def test_scan_needs_a_class_and_window(client):
    assert "class" in post(client, "/api/quanah/scan", {"window": 1}).json["error"]
    put(client, "/api/quanah/settings", {"class": "pirate"})
    assert "window" in post(client, "/api/quanah/scan", {}).json["error"]
