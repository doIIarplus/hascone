import json
import threading

import pytest

from scouter import client, profiles, service


@pytest.fixture
def store(tmp_path, monkeypatch):
    from flaming import characters

    monkeypatch.setattr(characters, "PROFILE_DIR", tmp_path / "characters")
    characters.PROFILE_DIR.mkdir()
    (characters.PROFILE_DIR / "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.json").write_text(
        json.dumps({"name": "Example", "class": "Shadower"})
    )
    monkeypatch.setattr(profiles, "DIRECTORY", tmp_path / "scouter")
    return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_blank_profile_does_not_submit_synthetic_stats(store):
    data = profiles.load(store)
    values = profiles.effective(data)
    assert values["stat"]["mainStatBase"] is None
    assert values["hexa"]["skillCore1"] is None
    assert values["special"]["genesis"] is True
    with pytest.raises(ValueError, match="missing inputs"):
        profiles.payload(data)


def test_history_roundtrips_unicode_on_windows(store):
    data = profiles.load(store)
    data["history"] = [{"label": "\uac15\ud654 \u2605 \u2192"}]
    profiles.write(store, data)
    assert profiles.load(store)["history"] == data["history"]


def test_scans_and_manual_edits_replace_the_same_values(store):
    profiles.save_inputs(
        store, {"revision": 0, "changes": {"special.restraintRing": "4", "stat.mainStatBase": "8000"}}
    )
    profiles.save_scan(
        store, {"stat.mainStatBase": {"value": "6731", "confidence": 0.99}}, [], profiles.now()
    )
    data = profiles.snapshot(store)
    assert data["values"]["stat"]["mainStatBase"] == "6731"
    assert data["values"]["special"]["restraintRing"] == "4"
    assert "overrides" not in data
    profiles.save_inputs(store, {"revision": 2, "changes": {"stat.mainStatBase": "9000"}})
    assert profiles.snapshot(store)["values"]["stat"]["mainStatBase"] == "9000"
    assert "stat.mainStatBase" not in profiles.snapshot(store)["scanned"]
    profiles.save_scan(
        store, {"stat.mainStatBase": {"value": "7000", "confidence": 0.99}}, [], profiles.now()
    )
    assert profiles.snapshot(store)["values"]["stat"]["mainStatBase"] == "7000"


def test_partial_scan_leaves_unread_fields_and_reports_errors(store):
    profiles.save_inputs(store, {"revision": 0, "changes": {"stat.critical": "100", "linkSkill.thief": "3"}})
    profiles.save_scan(
        store,
        {"linkSkill.thief": {"value": "9", "confidence": 0.99}},
        ["Critical rate unreadable"],
        profiles.now(),
    )
    data = profiles.snapshot(store)
    assert data["values"]["stat"]["critical"] == "100"
    assert data["values"]["linkSkill"]["thief"] == "9"
    assert data["scan"]["errors"] == ["Critical rate unreadable"]
    assert "stat.critical" not in data["scanned"]


def test_existing_profile_migrates_without_changing_displayed_values_or_history(store):
    old = {
        "version": 1,
        "scanned": {"stat.mainStatBase": {"value": "6731", "confidence": 0.99}},
        "overrides": {"stat.mainStatBase": "8000", "special.restraintRing": "4"},
        "revision": 7,
        "scan": None,
        "history": [{"id": "old", "input": {"untouched": True}}],
    }
    profiles.write(store, old)
    migrated = profiles.load(store)
    assert migrated["version"] == 2
    assert "overrides" not in migrated
    assert profiles.effective(migrated)["stat"]["mainStatBase"] == "8000"
    assert migrated["history"] == old["history"]
    profiles.save_scan(
        store, {"stat.mainStatBase": {"value": "7000", "confidence": 0.99}}, [], profiles.now()
    )
    disk = json.loads((profiles.DIRECTORY / f"{store}.json").read_text(encoding="utf-8"))
    assert disk["inputs"]["stat.mainStatBase"] == "7000"
    assert disk["inputs"]["special.restraintRing"] == "4"
    assert "overrides" not in disk
    assert disk["history"] == old["history"]


def test_manual_patch_does_not_replace_other_inputs(store):
    profiles.save_inputs(
        store, {"revision": 0, "changes": {"stat.mainStatBase": "6731", "special.restraintRing": "4"}}
    )
    profiles.save_inputs(store, {"revision": 1, "changes": {"stat.mainStatBase": None}})
    data = profiles.snapshot(store)
    assert data["values"]["stat"]["mainStatBase"] is None
    assert data["values"]["special"]["restraintRing"] == "4"


@pytest.mark.parametrize(
    "path,value",
    [
        ("special.isReboot", False),
        ("stat.myClass", "Hero"),
        ("stat.weaponAtk", "nan"),
        ("hexa.skillCore1", "31"),
        ("hexa.skillCore1", "1.5"),
        ("stat.ignoreDef", "100"),
        ("stat.level", "301"),
        ("special.combat", "true"),
        ("power.atk", 10),
    ],
)
def test_rejects_invalid_inputs(store, path, value):
    with pytest.raises(ValueError):
        profiles.save_inputs(store, {"revision": 0, "changes": {path: value}})


def test_revision_prevents_overwriting_new_scan(store):
    profiles.save_scan(store, {}, [], profiles.now())
    with pytest.raises(ValueError, match="changed"):
        profiles.save_inputs(store, {"revision": 0, "changes": {}})


def test_unknown_character_and_traversal_rejected(store):
    with pytest.raises(ValueError):
        profiles.load("../outside")
    with pytest.raises(ValueError):
        profiles.load("missing")


def test_api_build_does_not_mutate_input(store):
    data = profiles.load(store)
    user = profiles.effective(data)
    for path, value in profiles.flatten(user).items():
        if value is None:
            profiles.assign(user, path, "0")
    body = client.optimizer_body(user, {"specEfficiency": {}, "hexaUsed": [1, 20], "mercedesBuildType": 1})
    assert body["myHexa"]["hexaSkill_used"]["sole_ErdaPrice"] == 20
    assert "hexaSkill" not in user["hexa"]
    assert body["merType"] == 1


def test_cancelled_request_does_not_submit(monkeypatch):
    event = threading.Event()
    event.set()
    monkeypatch.setattr(client, "_headers", {"not-a-real-key": "test"})
    monkeypatch.setattr(client, "_headers_at", 0)

    def forbidden(*args, **kwargs):
        raise AssertionError("Network called after cancel")

    monkeypatch.setattr(client.requests, "get", forbidden)
    with pytest.raises(ValueError, match="cancelled"):
        client.calculate({}, event, lambda _: None)


def test_result_keeps_exact_input_even_if_profile_changes(store, monkeypatch):
    def calc(user, cancel, progress):
        profiles.save_inputs(store, {"revision": 0, "changes": {"special.restraintRing": "4"}})
        return {
            "damage": {"calculatedData": {"boss380_hexaStat": 123}},
            "order": None,
            "order_error": "unavailable",
        }

    monkeypatch.setattr(client, "calculate", calc)
    service._run(store, {"original": "input"}, "original-digest", threading.Event())
    data = profiles.load(store)
    assert data["history"][0]["input"] == {"original": "input"}
    assert data["inputs"]["special.restraintRing"] == "4"
    assert data["history"][0]["order_error"] == "unavailable"


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_optimizer_preserves_completed_hexa_stat_count(store, count):
    profiles.save_inputs(store, {"revision": 0, "changes": {"hexa.hexaStat": str(count)}})
    user = profiles.effective(profiles.load(store))
    for path, value in profiles.flatten(user).items():
        if value is None:
            profiles.assign(user, path, "0")
    body = client.optimizer_body(user, {"specEfficiency": {}, "hexaUsed": [1, 20]})
    assert body["myHexa"]["hexaStat"] == count
    assert body["myHexa"]["hexaStat_opened"] is (count > 0)
    assert user["hexa"]["hexaStat"] == count
    assert "hexaStat_opened" not in user["hexa"]


@pytest.mark.parametrize("value", ["4", "1.5"])
def test_invalid_hexa_stat_count_rejected(store, value):
    with pytest.raises(ValueError):
        profiles.save_inputs(store, {"revision": 0, "changes": {"hexa.hexaStat": value}})


def test_website_inputs_are_sufficient_without_hidden_api_fields(store):
    data = profiles.load(store)
    paths = profiles.input_paths(data["class_info"])
    assert "stat.ssubStatBase" in paths  # Shadower's second secondary stat.
    assert "hexa.hexaStat" in paths  # Explicit manual input for completed cores.
    assert not paths.intersection(
        {"stat.weaponAtk", "stat.ssubStat_ability", "stat.normalDmg"}
    )
    inputs: dict[str, str | None] = dict.fromkeys(paths, "0")
    data["inputs"] = inputs
    data["inputs"]["stat.level"] = "285"
    # Old editor allowed clearing these internal fields. No visible input can repair them.
    data["inputs"].update({"stat.weaponAtk": None, "stat.ssubStat_ability": None})
    user = profiles.payload(data)
    assert all(value is not None for value in profiles.flatten(user).values())
    assert user["stat"]["weaponAtk"] == "0"
    assert data["inputs"]["stat.weaponAtk"] is None  # Saved data is not destroyed.
    data["inputs"]["stat.critical"] = None
    with pytest.raises(ValueError, match="stat.critical"):
        profiles.payload(data)


@pytest.mark.parametrize("name", ["Hero", "Shadower", "Demon Avenger", "Zero", "Mihile", "Kaiser"])
def test_required_inputs_follow_website_class_conditions(name):
    info = profiles.class_info(name)
    paths = profiles.input_paths(info)
    assert ("stat.ssubStatBase" in paths) == bool(info["sub2"])
    assert ("stat.classForce" in paths) == (name == "Zero")
    assert ("special.epiSoul" in paths) == (name == "Demon Avenger")
    assert ("linkSkill.mihile" in paths) == (name == "Mihile")
    assert ("linkSkill.kaiser" in paths) == (name == "Kaiser")
    assert "linkSkill.hayato" not in paths
    assert "special.ringOfSum" not in paths
