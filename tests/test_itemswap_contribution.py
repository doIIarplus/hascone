import pytest

from itemswap import catalog
from itemswap.contribution import contribution
from scouter import profiles
from starforce import stats as starforce


def info(name):
    return profiles.class_info(name)


def parts(class_name, slot, side):
    result = {}
    total = contribution(info(class_name), slot, side, result)
    return total, result


def test_stats_map_to_class_roles_for_a_str_class():
    total = contribution(info("Hero"), "hat", {"item": "warrior:eternal-warrior-hat"})
    assert total == {"mainStat": 80, "subStat": 80, "atk": 10, "ignoreGuard": 15}


def test_stats_map_to_class_roles_for_an_int_class_with_magic_attack():
    total = contribution(info("Bishop"), "hat", {"item": "magician:eternal-mage-hat"})
    assert total == {"mainStat": 80, "subStat": 80, "atk": 10, "ignoreGuard": 15}
    # All-stat items give MATT, not ATT, to a mage.
    assert contribution(info("Bishop"), "emblem", {"item": "magician:mithra-rage-mage"}) == {
        "mainStat": 40, "subStat": 40, "atk": 5,
    }


def test_xenon_uses_three_stats_and_ignores_int():
    total = contribution(info("Xenon"), "secondary",
                         {"item": "pirate:astra-decacore-controller", "variant": {"stage": 2, "version": 1}})
    assert total == {"mainStat": 7, "subStat": 7, "ssubStat": 7, "atk": 7}


def test_gear_without_the_class_attack_or_stats_adds_nothing_but_its_other_lines():
    assert contribution(info("Hero"), "hat", {"item": "magician:eternal-mage-hat"}) == {"ignoreGuard": 15}


def test_potential_boxes_and_damage_fold_into_boss_damage():
    side = {"item": "warrior:eternal-warrior-hat",
            "potential": {"mainStatPer": "21", "damage": 9, "bossDmg": "30", "ignoreGuard": 0, "coolTimeReduce": 2}}
    total, split = parts("Hero", "hat", side)
    assert split["potential"] == {"mainStatPer": 21, "bossDmg": 39, "coolTimeReduce": 2}
    assert total["ignoreGuard"] == 15


def test_flames_map_attack_by_class_and_all_stat_percent():
    side = {"item": "warrior:eternal-warrior-gloves",
            "flame": {"str": 100, "dex": 40, "int": 30, "matt": 5, "att": 3, "allStatPer": 6}}
    _, split = parts("Hero", "gloves", side)
    assert split["flame"] == {"mainStat": 100, "subStat": 40, "atk": 3, "allStatPer": 6}


@pytest.mark.parametrize(
    "class_name, slot, item_id, stars, job",
    [
        ("Hero", "hat", "warrior:eternal-warrior-hat", 22, "warrior"),
        ("Night Lord", "top", "thief:faf-thief-top", 17, "thief"),
        ("Bishop", "ring_1", "giant-fear", 23, "shared"),
        ("Hero", "pendant_2", "daybreak-pendant", 15, "shared"),
        ("Hero", "heart", "complete-under-control", 19, "shared"),
        ("Hero", "secondary", "warrior:pnou-medal", 10, "warrior"),
    ],
)
def test_star_force_matches_the_existing_tables(class_name, slot, item_id, stars, job):
    record = catalog.by_id()[item_id]
    level = record["level"]
    band = next(b for b in starforce.database()["bands"] if b["min_level"] <= level <= b["max_level"])
    meta = {"level": level, "band": band, "job": job, "kind": "armor", "slot": slot.split("_")[0],
            "base_attack": None, "base_magic_attack": None, "cap": 30}
    expected = starforce.gains(meta, 0, stars)
    _, split = parts(class_name, slot, {"item": item_id, "stars": stars})
    c = info(class_name)
    attack = expected.get("Magic Attack" if c["main"] == "INT" else "Attack Power", 0)
    assert split["starforce"].get("mainStat", 0) == expected.get(c["main"], 0)
    assert split["starforce"].get("atk", 0) == attack


def test_gloves_get_the_extra_star_attack():
    _, gloves = parts("Hero", "gloves", {"item": "warrior:eternal-warrior-gloves", "stars": 15})
    _, shoes = parts("Hero", "shoes", {"item": "warrior:eternal-warrior-shoes", "stars": 15})
    assert gloves["starforce"]["atk"] - shoes["starforce"].get("atk", 0) == 7


def test_weapon_like_secondaries_use_the_weapon_formula():
    _, katara = parts("Dual Blade", "secondary", {"item": "thief:astra-blade", "stars": 1})
    assert katara["starforce"]["atk"] == 5  # floor(225 * 2% + 1)
    _, talisman = parts("Kanna", "secondary", {"item": "magician:astra-kanna-talisman", "stars": 1})
    assert talisman["starforce"]["atk"] == 6  # floor(260 * 2% + 1), MATT for Kanna
    _, shield = parts("Hero", "secondary", {"item": "warrior:astra-medal", "stars": 1})
    assert shield["starforce"].get("atk", 0) == 0  # armor table: no attack below 16 stars


@pytest.mark.parametrize(
    "item_id, side, message",
    [
        ("warrior:astra-medal", {"variant": {"stage": 1, "version": 1}, "stars": 16}, "at most 15"),
        ("warrior:eternal-warrior-hat", {"stars": 31}, "at most 30"),
        ("ghost-ship-exorcist", {"stars": 23}, "at most 22"),
        ("immortal-legacy", {"stars": 1}, "cannot be Star Forced"),
        ("warrior:eternal-warrior-hat", {"stars": 1.5}, "whole number"),
        ("warrior:astra-medal", {"variant": {"stage": 4}}, "no such stage"),
    ],
)
def test_impossible_star_force_and_stages_rejected(item_id, side, message):
    slot = catalog.by_id()[item_id]["slot"]
    with pytest.raises(ValueError, match=message):
        contribution(info("Hero"), slot, {"item": item_id, **side})


def test_add_ons_count_flat_stats_and_reject_impossible_counts():
    base = contribution(info("Hero"), "face", {"item": "original-sin-of-pride"})
    three = contribution(info("Hero"), "face", {"item": "original-sin-of-pride", "addons": {"exceptional": 3}})
    assert three["mainStat"] - base["mainStat"] == 45 and three["atk"] - base["atk"] == 30
    with pytest.raises(ValueError, match="0 to 3"):
        contribution(info("Hero"), "face", {"item": "original-sin-of-pride", "addons": {"exceptional": 4}})
    transposed = contribution(info("Hero"), "eye", {"item": "sweetwater-monocle", "addons": {"transposed": 1}})
    assert transposed == {"mainStat": 19, "subStat": 19, "atk": 8}


def test_unmodifiable_black_heart_ignores_every_upgrade_box():
    side = {"item": "black-heart", "stars": 10, "flame": {"str": 50}, "potential": {"mainStatPer": 30},
            "other": {"atk": 10}}
    assert contribution(info("Hero"), "heart", side) == {
        "mainStat": 50, "subStat": 50, "atk": 77, "bossDmg": 30, "ignoreGuard": 30,
    }


def test_upgrades_an_item_cannot_have_are_not_counted():
    side = {"item": "giant-fear", "flame": {"str": 100}}
    assert "mainStat" not in parts("Hero", "ring_1", side)[1]["flame"]
    assert contribution(info("Hero"), "medal", {"item": "immortal-legacy", "potential": {"bossDmg": 30}}) == {
        "mainStat": 10, "subStat": 10, "atk": 10, "bossDmg": 10,
    }
    # Immortal Legacy is the one flameable medal.
    assert contribution(info("Hero"), "medal", {"item": "immortal-legacy", "flame": {"str": 40, "allStatPer": 3}}) == {
        "mainStat": 50, "subStat": 10, "atk": 10, "bossDmg": 10, "allStatPer": 3,
    }
    assert contribution(info("Hero"), "medal", {"item": "seven-day-monster-parker", "flame": {"str": 40}})["mainStat"] == 7


def test_custom_item_uses_its_attack_box_for_the_class_and_needs_a_level_for_stars():
    side = {"item": "custom", "custom_base": {"str": "10", "int": 10, "att": 4, "ignoreGuard": 5}}
    assert contribution(info("Hero"), "ring_1", side) == {"mainStat": 10, "atk": 4, "ignoreGuard": 5}
    assert contribution(info("Bishop"), "ring_1", side) == {"mainStat": 10, "atk": 4, "ignoreGuard": 5}
    with pytest.raises(ValueError, match="level"):
        contribution(info("Hero"), "ring_1", {**side, "stars": 5})
    starred = contribution(info("Hero"), "ring_1", {**side, "stars": 5, "custom_level": 160})
    assert starred["mainStat"] == 20


def test_other_bonuses_accept_simulator_fields_only():
    assert contribution(info("Hero"), "hat", {"item": None, "other": {"criDmg": "1.5"}}) == {"criDmg": 1.5}
    with pytest.raises(ValueError, match="Unsupported"):
        contribution(info("Hero"), "hat", {"item": None, "other": {"maxHp": 1}})
    with pytest.raises(ValueError, match="must be a number"):
        contribution(info("Hero"), "hat", {"item": "warrior:eternal-warrior-hat", "flame": {"str": "lots"}})


def test_pocket_items_take_flames_but_no_stars_or_potential():
    side = {"item": "will-red-book", "flame": {"str": 60, "allStatPer": 5}, "potential": {"mainStatPer": 30}}
    assert contribution(info("Hero"), "pocket", side) == {
        "mainStat": 80, "subStat": 10, "atk": 10, "allStatPer": 5,
    }
    with pytest.raises(ValueError, match="cannot be Star Forced"):
        contribution(info("Hero"), "pocket", {"item": "phg", "stars": 1})
    # The book's 20 lands on whichever stat the class uses.
    assert contribution(info("Bishop"), "pocket", {"item": "will-blue-book"}) == {
        "mainStat": 20, "subStat": 10, "atk": 10,
    }
