"""The Quanah solver against results recorded from the three community solvers.

Each site's EXAMPLE gear was run through that site's own solve() (2026-11-24);
the expected scores, counts and one-drop options below are its output.
"""

from quanah import solver

# The sites order slots Hat, Top, Bottom, Cape, Glove, Shoe and use mage/archer.
SITE_SLOTS = ["hat", "top", "bottom", "cape", "gloves", "shoes"]
RENAME = {"mage": "magician", "archer": "bowman"}


def items(example, skip=None):
    out = []
    for slot, pieces in zip(SITE_SLOTS, example, strict=True):
        if slot == skip:
            continue
        for n, lines in enumerate(pieces):
            out.append({"id": f"{slot}{n}", "slot": slot, "lines": [RENAME.get(k, k) for k in lines]})
    return out


THREE_L = [
    [["dl", "atk", "mage"], ["atk", "wh", "other"]],
    [["wh", "reg", "crit"], ["dl", "mage", "crit"]],
    [["reg", "dl", "pirate"]],
    [["atk", "wh", "thief"], ["thief", "archer", "dl"]],
    [["dl", "wh", "warrior"], ["crit", "wh", "reg"]],
    [["atk", "reg", "archer"]],
]
GANDI = [
    [["dl", "atk", "mage"]],
    [["wh", "reg", "crit"]],
    [["reg", "dl", "thief"]],
    [["atk", "wh", "archer"]],
    [["dl", "wh", "crit"]],
    [["atk", "reg", "crit"]],
]
EU = [
    [["dl", "atk", "dmg"], ["atk", "wh", "other"]],
    [["wh", "reg", "crit"], ["dl", "dmg", "other"]],
    [["reg", "dl", "dmg"]],
    [["atk", "wh", "crit"], ["crit", "dmg", "dl"]],
    [["dl", "wh", "dmg"], ["crit", "wh", "reg"]],
    [["atk", "reg", "crit"]],
]


def build(preset, **extra):
    return solver.resolve_build({"preset": preset, **extra})


def solve(example, preset, skip=None, **extra):
    targets, jobs = build(preset, **extra)
    return solver.solve(items(example, skip), targets, jobs)


def hunt(result):
    return sorted((h["slot"], tuple(h["need"])) for h in result["hunt"])


def test_skill_example_completes_with_one_winning_combo():
    result = solve(THREE_L, "skill")
    assert (result["score"], result["goal"], result["ways"]) == (18, 18, 1)
    assert result["picks"] == {"hat": "hat0", "top": "top0", "bottom": "bottom0",
                               "cape": "cape0", "gloves": "gloves0", "shoes": "shoes0"}
    assert all(all(flags) for flags in result["used"].values())
    assert result["hunt"] == [] and result["missing"] == []


def test_skill_without_hat_lists_the_sites_one_drop_options():
    result = solve(THREE_L, "skill", skip="hat")
    assert result["score"] == 15
    assert result["counts"] == {"dl": 2, "wh": 3, "reg": 3, "atk": 2, "warrior": 1, "magician": 0,
                                "bowman": 1, "thief": 1, "pirate": 1, "crit": 1}
    assert result["picks"]["hat"] is None and result["used"]["hat"] == []
    assert hunt(result) == [("hat", ("dl", "atk", "magician")), ("hat", ("wh", "reg", "atk"))]


def test_gandi_chosen_jobs():
    result = solve(GANDI, "gandi", job_mode="custom", jobs=["magician", "thief", "bowman"])
    assert (result["score"], result["goal"], result["ways"]) == (18, 18, 1)
    # Only one of the three chosen jobs is on this gear.
    assert solve(GANDI, "gandi", job_mode="custom", jobs=["pirate", "warrior", "thief"])["score"] == 16


def test_gandi_any_three_jobs_offers_every_open_job():
    chosen = solve(GANDI, "gandi", skip="hat", job_mode="custom", jobs=["magician", "thief", "bowman"])
    assert chosen["score"] == 15 and hunt(chosen) == [("hat", ("dl", "atk", "magician"))]
    anyjob = solve(GANDI, "gandi", skip="hat", job_mode="any")
    assert hunt(anyjob) == [("hat", ("dl", "atk", "magician")), ("hat", ("dl", "atk", "pirate")),
                            ("hat", ("dl", "atk", "warrior"))]


def test_gandi_with_an_invalid_job_choice_falls_back_to_the_default():
    targets, jobs = build("gandi", job_mode="custom", jobs=["magician"])
    assert jobs == (3, ("magician", "thief", "bowman"))
    assert targets == {"dl": 3, "wh": 3, "reg": 3, "atk": 3, "crit": 3}


def test_eu_example_and_one_drop_option():
    assert solve(EU, "eu")["score"] == 18
    result = solve(EU, "eu", skip="hat")
    assert result["score"] == 15
    assert result["counts"] == {"dl": 2, "wh": 3, "reg": 3, "atk": 2, "crit": 3, "dmg": 2}
    assert hunt(result) == [("hat", ("dl", "atk", "dmg"))]


def test_lines_above_a_target_are_wasted():
    pieces = [{"id": "a", "slot": "hat", "lines": ["dl", "wh", "reg"]},
              {"id": "b", "slot": "top", "lines": ["dl", "wh", "atk"]}]
    result = solver.solve(pieces, {"dl": 1, "wh": 2, "atk": 1})
    assert result["score"] == 4
    assert result["used"]["hat"] == [True, True, False]
    assert result["used"]["top"] == [False, True, True]


def test_custom_targets_set_the_goal():
    targets, jobs = build("custom", targets={"dl": 3, "crit": 2, "pirate": 1, "wh": 0})
    assert jobs is None and targets == {"dl": 3, "crit": 2, "pirate": 1}
    result = solver.solve([{"id": "a", "slot": "hat", "lines": ["dl", "crit", "pirate"]}], targets)
    assert (result["score"], result["goal"]) == (3, 6)
    # Two more pieces are needed, so no single drop finishes it.
    assert result["hunt"] == [] and sorted(result["missing"]) == ["crit", "dl", "dl"]


def test_a_shorter_custom_goal_can_be_finished_by_a_partial_piece():
    result = solver.solve([{"id": "a", "slot": "hat", "lines": ["dl", "wh"]}], {"dl": 2, "wh": 1})
    assert result["score"] == 2
    assert ("top", ("dl",)) in hunt(result)
