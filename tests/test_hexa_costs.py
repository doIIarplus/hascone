import pytest
from test_app import ID, client, get  # noqa: F401

from flaming import characters
from scouter import profiles
from scouter.hexa_costs import NODES, fragments, spent, split_spent


def test_tables_match_published_totals():
    totals = {"origin": 4400, "ascent": 4500, "mastery": 2252, "enhancement": 3383, "common": 6268, "third_common": 4035}
    assert {table: spent(table, 30) for table in totals} == totals
    # Origin level 1 is granted at 6th job; the Ascent node costs 100 to unlock.
    assert (spent("origin", 1), spent("ascent", 1)) == (0, 100)


def test_fragments_from_saved_levels():
    info = profiles.class_info("Shadower")
    values = {path: "0" for path in NODES}
    values.update({"hexa.skillCore1": "30", "hexa.skillCore2": "1", "hexa.generalCore2": "1", "huntSkill.solJanus": "10",
                   **{f"hexa.masteryCore{i}": "30" for i in range(1, 5)}, **{f"hexa.reinCore{i}": "30" for i in range(1, 5)}})
    values["hexa.hexaStat"] = 2
    # 4400 + 100 + 4×2252 + 4×3383 + 125 (Sol Hecate Lv1) + 903 (Sol Janus Lv10) + (10 + 200) + 2×200 (HEXA Stat minimum)
    assert fragments(values, info) == (28678, False, True)
    values["hexa.reinCore4"] = None
    assert fragments(values, info) == (28678 - 3383, True, True)
    assert fragments(dict.fromkeys(values), info) == (None, True, False)


def test_erda_link_tables_match_datamined_totals():
    assert (spent("erda_origin", 30), spent("ultimate", 30), spent("half_stone", 15)) == (4415, 2245, 827)
    # Half stones cost unevenly, so e.g. Lv5 is cheapest as 2 + 3 (141), not 5 + 0 (152).
    assert [split_spent(level) for level in range(31)] == [
        0, 37, 59, 82, 107, 141, 164, 189, 214, 259, 298, 339, 381, 423, 464, 506,
        548, 593, 638, 748, 798, 852, 909, 971, 1066, 1123, 1180, 1242, 1304, 1479, 1654]


def test_erda_link_fragments_are_a_minimum():
    erel, sia = profiles.class_info("ErelLight"), profiles.class_info("SiaAstelle")
    values = {path: "0" for path in NODES}
    # Sia's Shine Boost is split into half stones; Erel's Eternal Light Boost is one full stone.
    values["hexa.reinCore1"] = "30"
    assert (fragments(values, sia), fragments(values, erel)) == ((1654, False, True), (3383, False, True))
    values.update({"hexa.skillCore1": "30", "hexa.skillCore2": "1", "hexa.generalCore2": "1", "huntSkill.solJanus": "10",
                   "hexa.masteryCore1": "30", "hexa.masteryCore2": "30", **{f"hexa.reinCore{i}": "30" for i in range(2, 5)}})
    # Erda Link Stats is not a HEXA Stat core count.
    values["hexa.hexaStat"] = 2
    # 4415 + 100 + 2×2245 (shared mastery skills count once) + 3383 + 3×1654 + 125 (Sol Hecate Lv1) + 903 (Sol Janus Lv10)
    assert fragments(values, erel) == (18378, False, True)
    assert fragments(dict.fromkeys(values), erel) == (None, True, False)


def test_overview_summary_includes_fragments(client):
    # Unsaved levels are unknown, even where the Scouter form shows a default 0.
    row = next(r for r in get(client, "/api/summary").json["profiles"] if r["id"] == ID)
    assert row["fragments"] is None
    data = profiles.load(ID)
    data["inputs"].update({**dict.fromkeys(NODES, "0"), "hexa.hexaStat": 0, "hexa.skillCore1": "10", "huntSkill.solJanus": "1"})
    profiles.write(ID, data)
    row = next(r for r in get(client, "/api/summary").json["profiles"] if r["id"] == ID)
    assert (row["fragments"], row["fragments_partial"], row["fragments_minimum"]) == (580 + 125, False, False)


def test_overview_summary_flags_erda_link_classes(client):
    row = next(r for r in get(client, "/api/summary").json["profiles"] if r["id"] == ID)
    assert row["erda_link"] is False
    data = characters.load(ID)
    data["class"] = "ErelLight"
    characters.write(data)
    row = next(r for r in get(client, "/api/summary").json["profiles"] if r["id"] == ID)
    assert (row["fragments"], row["erda_link"]) == (None, True)
    data = profiles.load(ID)
    data["inputs"].update({**dict.fromkeys(NODES, "0"), "hexa.skillCore1": "10", "huntSkill.solJanus": "1"})
    profiles.write(ID, data)
    row = next(r for r in get(client, "/api/summary").json["profiles"] if r["id"] == ID)
    assert (row["fragments"], row["fragments_partial"], row["fragments_minimum"]) == (565 + 125, False, True)
