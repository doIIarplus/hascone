import pytest
from test_scouter_suggestions import cube_table, saved

from cubing.lines import parse_line
from cubing.probability import pools_for
from cubing.scoring import current_score
from scouter import suggestions


@pytest.mark.parametrize("line", ["Damage: +13%", "Damage +13%", " damage : +13 % "])
def test_damage_percentage_is_preserved(line):
    assert parse_line(line) == ("Damage %", 13)


def test_malformed_damage_is_not_silently_discarded():
    with pytest.raises(ValueError, match="Unrecognized potential line"):
        parse_line("Damage: +1O%")


@pytest.mark.parametrize("job,attack", [("Hero", "ATT"), ("Bishop", "MATT")])
def test_damage_and_boss_damage_have_identical_equivalents_and_costs(job, attack):
    def score(line):
        return current_score(
            "weapon", job,
            {"status": "scanned", "rank": "Legendary", "lines": [line, f"{attack}: +13%", "DEF: +10%"]},
            attack_score={"boss_per_attack": 4}, item_level=200,
        )

    damage, boss = score("Damage: +13%"), score("Boss Damage: +13%")
    assert damage == boss
    assert damage["value"] == pytest.approx(16.25)
    assert all(row["probability"] > 0 for row in damage["current_cost"]["cubes"])


@pytest.mark.parametrize("level,expected", [(159, 12), (160, 13), (200, 13)])
def test_damage_roll_values_and_level_adjustment(level, expected):
    raw = {name: [("Damage %", 12, 100)] for name in ("first_line", "second_line", "third_line")}
    rules = [{"metric": "DAMAGE", "unit": "percent"}, {"metric": "ATT_EQ", "unit": "percent"}]
    pools = pools_for(raw, level, rules, {"attack_score": {"boss_per_attack": 4}})
    assert pools == [[("Damage %", (expected, expected / 4), 1.0)]] * 3


def test_replacing_13_damage_with_3_attack_is_not_an_upgrade(saved, cube_table):
    data, _ = saved
    efficiencies = data["history"][0]["damage"]["calculatedData"]["specEfficiency"]
    efficiencies.update(dmgeff1=0.0015, atkPereff1=0.006)
    _, weights, _, _ = suggestions.coefficients(data["history"][0], data["class_info"])
    item = cube_table(
        [[("ATT %", 3, 100)], [("Junk", 0, 100)], [("Junk", 0, 100)]],
        ["Damage: +13%", "DEF: +9%", "DEF: +9%"], "weapon",
    )
    with pytest.raises(ValueError, match="No positive FD outcome"):
        suggestions.cube_suggestions("weapon", item, "Shadower", weights, 0, lambda: None)


@pytest.mark.parametrize("baseline", ["Damage: +13%", "Boss Damage: +13%"])
def test_rolling_damage_counts_as_a_positive_gain(saved, cube_table, baseline):
    data, _ = saved
    _, weights, _, _ = suggestions.coefficients(data["history"][0], data["class_info"])
    item = cube_table(
        [[("Damage %", 20, 50), ("ATT %", 13, 50)], [("Junk", 0, 100)], [("Junk", 0, 100)]],
        [baseline, "DEF: +9%", "DEF: +9%"], "weapon",
    )
    rows = suggestions.cube_suggestions("weapon", item, "Shadower", weights, 0, lambda: None)
    assert len(rows) == 2
    for row in rows:
        assert row["probability"] == pytest.approx(0.5)
        assert row["expected_fd"] == pytest.approx(0.7)
        assert row["examples"][0] == "Damage: +20%"
