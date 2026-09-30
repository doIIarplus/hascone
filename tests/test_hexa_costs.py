import pytest
from test_app import ID, client, get  # noqa: F401

from scouter import profiles
from scouter.hexa_costs import NODES, fragments, spent


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


def test_erda_link_classes_are_not_totalled():
    assert fragments({"hexa.skillCore1": "30"}, profiles.class_info("SiaAstelle")) == (None, False, False)


def test_overview_summary_includes_fragments(client):
    # Unsaved levels are unknown, even where the Scouter form shows a default 0.
    row = next(r for r in get(client, "/api/summary").json["profiles"] if r["id"] == ID)
    assert row["fragments"] is None
    data = profiles.load(ID)
    data["inputs"].update({**dict.fromkeys(NODES, "0"), "hexa.hexaStat": 0, "hexa.skillCore1": "10", "huntSkill.solJanus": "1"})
    profiles.write(ID, data)
    row = next(r for r in get(client, "/api/summary").json["profiles"] if r["id"] == ID)
    assert (row["fragments"], row["fragments_partial"], row["fragments_minimum"]) == (580 + 125, False, False)
