from datetime import UTC, datetime

import pytest
from test_app import BASE, ID, client, get  # noqa: F401  (client is a fixture)

import app
from bossing import tracker
from flaming import characters

A, B = "a" * 32, "b" * 32
NOW = datetime(2026, 9, 30, 12, tzinfo=UTC)  # A Wednesday; the week began Thursday Sept 24.


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(tracker, "PATH", tmp_path / "bossing.json")


def profile(identifier=A, world_id=45):
    return {"id": identifier, "name": "Example", "class": "Hero", "level": 280, "world_id": world_id}


def test_week_starts_thursday_midnight_utc():
    assert tracker.week_start(NOW) == datetime(2026, 9, 24, tzinfo=UTC)
    assert tracker.week_start(datetime(2026, 10, 1, tzinfo=UTC)) == datetime(2026, 10, 1, tzinfo=UTC)
    assert tracker.week_start(datetime(2026, 9, 30, 23, 59, tzinfo=UTC)) == datetime(2026, 9, 24, tzinfo=UTC)


def test_heroic_worlds_pay_five_times_and_party_splits():
    _, bosses = tracker.catalog()
    lotus = bosses["Hard Lotus"]
    assert tracker.value(lotus, 1, "Kronos") == lotus["mesos"] * 5
    assert tracker.value(lotus, 1, "Bera") == lotus["mesos"]
    assert tracker.value(lotus, 2, "Scania") == lotus["mesos"] // 2
    # Hard Jupiter uses the wiki's value, not MapleHub's transposed digits.
    assert bosses["Hard Jupiter"]["mesos"] * 5 == 5_953_000_000


def test_configure_validates_difficulty_party_and_world():
    tracker.configure(A, world="Bera", bosses={"weekly:Lotus": {"difficulty": "Hard", "party": 2}})
    assert tracker.read()["characters"][A] == {"world": "Bera", "bosses": {"weekly:Lotus": {"difficulty": "Hard", "party": 2}}, "clears": {}}
    with pytest.raises(ValueError, match="Unknown boss"):
        tracker.configure(A, bosses={"weekly:Lotus": {"difficulty": "Chaos"}})
    with pytest.raises(ValueError, match="Unknown boss"):
        tracker.configure(A, bosses={"daily:Lotus": {"difficulty": "Hard"}})
    with pytest.raises(ValueError, match="party of 1 to 2"):
        tracker.configure(A, bosses={"weekly:Lotus": {"difficulty": "Extreme", "party": 3}})
    with pytest.raises(ValueError, match="Kronos"):
        tracker.configure(A, world="Elysium")


def test_only_the_fourteen_most_valuable_weekly_crystals_sell():
    _, bosses = tracker.catalog()
    weekly = sorted((b for b in bosses.values() if b["category"] == "weekly"), key=lambda b: b["mesos"])
    chosen = {}
    for boss in weekly:
        chosen.setdefault(tracker.group(boss), {"difficulty": boss["difficulty"], "party": 1})
    tracker.configure(A, bosses=chosen)
    names = [f"{c['difficulty']} {key.partition(':')[2]}" for key, c in chosen.items()]
    assert len(names) > tracker.WEEKLY_LIMIT
    for name in names:
        tracker.set_clear(A, name, 1, profile(), NOW)
    row = tracker.summary([profile()], NOW)["characters"][0]
    values = sorted((b["value"] for b in row["bosses"] if b["category"] == "weekly"), reverse=True)
    assert row["earned"] == sum(values[: tracker.WEEKLY_LIMIT]) == row["possible"]
    assert row["done"]


def test_daily_bosses_count_up_to_seven_clears():
    # Zakum is both a daily (Normal) and a weekly (Chaos) boss; a character can do both.
    tracker.configure(A, bosses={"daily:Zakum": {"difficulty": "Normal", "party": 1}, "weekly:Zakum": {"difficulty": "Chaos", "party": 1}})
    tracker.set_clear(A, "Normal Zakum", 3, profile(), NOW)
    row = tracker.summary([profile()], NOW)["characters"][0]
    zakum = next(b for b in row["bosses"] if b["name"] == "Normal Zakum")
    chaos = next(b for b in row["bosses"] if b["name"] == "Chaos Zakum")
    assert (zakum["count"], zakum["limit"]) == (3, 7)
    assert row["earned"] == zakum["value"] * 3 and row["possible"] == zakum["value"] * 7 + chaos["value"]
    with pytest.raises(ValueError, match="0 to 7"):
        tracker.set_clear(A, "Normal Zakum", 8, profile(), NOW)


def test_black_mage_clears_once_a_month():
    tracker.configure(A, bosses={"monthly:Black Mage": {"difficulty": "Hard", "party": 6}})
    earlier = datetime(2026, 9, 10, tzinfo=UTC)
    tracker.set_clear(A, "Hard Black Mage", 1, profile(), earlier)
    row = tracker.summary([profile()], NOW)["characters"][0]
    assert row["bosses"][0]["cleared_this_month"] and row["possible"] == 0 and row["done"]
    with pytest.raises(ValueError, match="already cleared this month"):
        tracker.set_clear(A, "Hard Black Mage", 1, profile(), NOW)
    # October starts a new month.
    tracker.set_clear(A, "Hard Black Mage", 1, profile(), datetime(2026, 10, 2, tzinfo=UTC))


def test_clears_require_an_enabled_boss_and_keep_past_weeks():
    with pytest.raises(ValueError, match="Add this boss"):
        tracker.set_clear(A, "Hard Lotus", 1, profile(), NOW)
    tracker.configure(A, bosses={"weekly:Lotus": {"difficulty": "Hard", "party": 1}})
    tracker.set_clear(A, "Hard Lotus", 1, profile(), datetime(2026, 9, 20, tzinfo=UTC))
    data = tracker.summary([profile()], NOW)
    assert data["characters"][0]["earned"] == 0
    assert data["history"][1] == {"week": "2026-09-17", "mesos": data["characters"][0]["bosses"][0]["value"]}


def test_world_limit_counts_every_crystal_in_that_world():
    tracker.configure(A, bosses={"daily:Zakum": {"difficulty": "Normal", "party": 1}})
    tracker.configure(B, bosses={"daily:Zakum": {"difficulty": "Normal", "party": 1}})
    tracker.set_clear(A, "Normal Zakum", 7, profile(A), NOW)
    tracker.set_clear(B, "Normal Zakum", 2, profile(B, world_id=1), NOW)
    worlds = {w["world"]: w["crystals"] for w in tracker.summary([profile(A), profile(B, world_id=1)], NOW)["worlds"]}
    assert worlds == {"Kronos": 7, "Bera": 2}


def test_drops_validate_and_are_removed_with_their_character():
    entry = tracker.add_drop({"character": A, "item": "Dreamy Belt", "date": "2026-09-28", "note": " First belt "}, {A})
    assert (entry["boss"], entry["note"]) == ("Lucid", "First belt")
    with pytest.raises(ValueError, match="roster"):
        tracker.add_drop({"character": B, "item": "Dreamy Belt", "date": "2026-09-28"}, {A})
    with pytest.raises(ValueError, match="item"):
        tracker.add_drop({"character": A, "item": "Mystery", "date": "2026-09-28"}, {A})
    with pytest.raises(ValueError, match="date"):
        tracker.add_drop({"character": A, "item": "Dreamy Belt", "date": "yesterday"}, {A})
    badge = tracker.add_drop({"character": A, "item": "Genesis Badge", "date": "2026-09-28"}, {A})
    tracker.update_drop(entry["id"], {"character": A, "item": "Cursed Red Spellbook", "date": "2026-09-29"}, {A})
    assert tracker.read()["drops"][0] | {"id": None} == {"id": None, "character": A, "item": "Cursed Red Spellbook", "boss": "Will", "date": "2026-09-29", "note": ""}
    tracker.delete_drop(badge["id"])
    tracker.configure(A, world="Kronos")
    tracker.forget(A)
    assert tracker.read() == {"characters": {}, "drops": []}


def test_bossing_routes_look_up_worlds_once_and_forget_deleted_characters(client, monkeypatch):
    lookups = []

    def ranking(name):
        lookups.append(name)
        return {"worldID": 70}

    monkeypatch.setattr(characters, "_ranking", ranking)
    def put(path, body):
        return client.put(path, json=body, base_url=BASE, headers={"X-Hascone-Token": app.TOKEN})

    data = get(client, "/api/bossing").json
    assert data["characters"][0]["world"] == "Hyperion" and lookups == ["Example"]
    get(client, "/api/bossing")
    assert lookups == ["Example"]
    assert put(f"/api/bossing/characters/{ID}", {"bosses": {"weekly:Lotus": {"difficulty": "Hard", "party": 1}}}).status_code == 200
    data = put(f"/api/bossing/characters/{ID}/clears", {"boss": "Hard Lotus", "count": 1}).json
    assert data["characters"][0]["earned"] == data["characters"][0]["bosses"][0]["value"]
    assert put(f"/api/bossing/characters/{ID}/clears", {"boss": "Hard Lotus", "count": 2}).status_code == 400
    assert client.delete(f"/api/characters/{ID}", base_url=BASE, headers={"X-Hascone-Token": app.TOKEN}).status_code == 200
    assert ID not in tracker.read()["characters"]


def test_early_saves_keyed_by_boss_alone_still_load():
    tracker.PATH.write_text('{"characters": {"' + A + '": {"world": null, "bosses": {"Damien": {"difficulty": "Hard", "party": 1}}, "clears": {}}}, "drops": []}')
    assert tracker.read()["characters"][A]["bosses"] == {"weekly:Damien": {"difficulty": "Hard", "party": 1}}
    assert [b["name"] for b in tracker.summary([profile()], NOW)["characters"][0]["bosses"]] == ["Hard Damien"]


@pytest.mark.parametrize("job,expected", [("Hero", ["warrior"]), ("Kanna", ["magician"]), ("Mercedes", ["bowman"]), ("Shadower", ["thief"]), ("Corsair", ["pirate"]), ("MoXuan", ["pirate"]), ("Xenon", ["thief", "pirate"]), ("ErelLight", ["warrior"]), ("DemonAvenger", ["warrior"])])
def test_class_branches_for_class_locked_drops(job, expected):
    assert tracker.branches(job) == expected


def test_every_class_has_a_branch():
    from utils.payload_data import read_payload_json

    for row in read_payload_json("src/flaming_data/classes.json"):
        assert tracker.branches(row["class"]), row["class"]
