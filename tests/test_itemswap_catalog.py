import copy
import importlib.util
import json
from pathlib import Path

import pytest

from itemswap import catalog
from scouter import profiles

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("build_swap_items", ROOT / "tools/build_swap_items.py")
build_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_tool)


def info(name):
    return profiles.class_info(name)


def names(class_name, slot):
    return sorted(i["name"] for i in catalog.for_class(info(class_name)) if i["slot"] == slot)


def test_saved_snapshot_rebuilds_the_committed_catalog_exactly():
    committed = (ROOT / "src/itemswap/data/items.json").read_text(encoding="utf-8")
    assert build_tool.render(build_tool.build()) == committed


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda d: d["items"].append(copy.deepcopy(d["items"][0])), "duplicated"),
        (lambda d: d["items"][0].update(slot="weapon"), "unknown slot"),
        (lambda d: d["items"][0].update(job="noble"), "unknown job"),
        (lambda d: d["items"][0]["base"].update(maxHp=500), "invalid base"),
        (lambda d: d["items"][0]["base"].update(str=1.5), "invalid base"),
        (lambda d: d["items"][0].update(level=None, starforce=True), "level"),
        (lambda d: d["items"][0].update(addons=[{"id": "x", "label": "X", "max": 0, "per": {}}]), "add-on"),
        (lambda d: d["items"][0].pop("flame"), "missing"),
        (lambda d: d["items"][0].update(classes=["nobody"]), "unknown classes"),
    ],
)
def test_malformed_catalog_rejected(change, message):
    data = copy.deepcopy(catalog.database())
    change(data)
    with pytest.raises(ValueError, match=message):
        catalog.validate(data)


def test_xenon_sees_thief_and_pirate_class_items_and_its_own_secondaries():
    hats = names("Xenon", "hat")
    assert {"Eternal Thief Bandana", "Eternal Pirate Hat"} <= set(hats)
    assert "Eternal Knight Helm" not in hats
    assert names("Xenon", "secondary") == [
        "Astra Deca Core Controller", "Evolving Octo Core Controller", "Princess Nou's Controller",
    ]


def test_class_items_stay_with_their_class():
    assert "Eternal Thief Bandana" in names("Night Lord", "hat")
    assert "Eternal Pirate Hat" not in names("Night Lord", "hat")
    assert "Astra Charm" in names("Night Lord", "secondary")
    assert "Astra Talisman" not in names("Night Lord", "secondary")  # Kanna's, same SEA name
    assert "Astra Talisman" in names("Kanna", "secondary")


def test_ren_and_erel_light_get_common_items_and_their_own_secondaries_only():
    assert names("Ren", "hat") == []
    assert "Superior Gollux Ring" in names("Ren", "ring")
    assert "Astra Imugi Gem" in names("Ren", "secondary")
    assert "Astra Keir" not in names("Ren", "secondary")
    assert "Princess Nou's Keir" in names("Erel Light", "secondary")


@pytest.mark.parametrize(
    "class_name, scanned, slot, expected",
    [
        ("Hero", "Meister Signet", "ring_2", "meister-signet"),
        ("Hero", "Meister Ring", "ring_1", "meister-signet"),
        ("Hero", "Royal Warrior Helm", "hat", "warrior:faf-warrior-hat"),
        ("Hero", "Mitra's Rage: Warrior", "emblem", "warrior:mithra-rage-warrior"),
        ("Hero", "Endless Terror", "ring_4", "giant-fear"),
        ("Hero", "Seven-day Monster Parker", "medal", "seven-day-monster-parker"),
        ("Paladin", "Astra Rosario", "secondary", "warrior:astra-rosario"),
        ("Paladin", "Astra Rosary", "secondary", "warrior:astra-rosario"),
        ("Demon Slayer", "Astra Force Shield", "secondary", "warrior:astra-force-shield"),
        ("Bishop", "ETERNAL  mage hat", "hat", "magician:eternal-mage-hat"),
        ("Hero", "Eternal Knight Helm", "top", None),
        ("Hero", "Eternal Mage Hat", "hat", None),
        ("Hero", "Ring of Restraint", "ring_1", None),
        ("Hero", "", "ring_1", None),
    ],
)
def test_scan_names_match_exactly_one_item_for_the_class_and_slot(class_name, scanned, slot, expected):
    record = catalog.match(scanned, slot, info(class_name))
    assert (record or {}).get("id") == expected


# Appendix A of the plan (the player's list); stats the API lacks come from the overlay.
APPENDIX_A = [
    ("ring", "Kanna's Treasure", 140, {"str": 5, "att": 1}),
    ("ring", "Reinforced Gollux Ring", 140, {"str": 8, "att": 5}),
    ("ring", "Superior Gollux Ring", 150, {"str": 10, "att": 8}),
    ("ring", "Guardian Angel Ring", 160, {"str": 5, "att": 2}),
    ("ring", "Dawn Guardian Angel Ring", 160, {"str": 5, "att": 2}),
    ("ring", "Endless Terror", 200, {"str": 5, "att": 4}),
    ("ring", "Whisper of the Source", 250, {"str": 10, "att": 5}),
    ("ring", "Blissful Nightmare", 250, {"str": 10, "att": 5}),
    ("belt", "Superior Engraved Gollux Belt", 150, {"str": 60, "att": 35}),
    ("belt", "Dreamy Belt", 200, {"str": 50, "att": 6}),
    ("face", "Twilight Mark", 140, {"str": 5, "att": 5}),
    ("face", "Berserked", 160, {"str": 10, "att": 10}),
    ("face", "Original Sin of Pride", 250, {"str": 15, "att": 15}),
    ("eye", "Black Bean Mark", 135, {"str": 7, "att": 1}),
    ("eye", "Papulatus Mark", 145, {"str": 8, "att": 1}),
    ("eye", "Sweetwater Monocle", 160, {"str": 10}),
    ("eye", "Magic Eyepatch", 160, {"str": 15, "att": 3}),
    ("earring", "Superior Gollux Earrings", 150, {"str": 15, "att": 10}),
    ("earring", "Estella Earrings", 160, {"str": 7, "att": 2}),
    ("earring", "Commanding Force Earring", 200, {"str": 7, "att": 5}),
    ("pendant", "Daybreak Pendant", 140, {"str": 8, "att": 2}),
    ("pendant", "Dominator Pendant", 140, {"str": 20, "att": 3}),
    ("pendant", "Superior Engraved Gollux Pendant", 150, {"str": 28, "att": 5}),
    ("pendant", "Sweetwater Pendant", 160, {"str": 34}),
    ("pendant", "Source of Suffering", 160, {"str": 10, "att": 3}),
    ("pendant", "Oath of Death", 250, {"str": 15, "att": 5}),
    ("pocket", "Pink Holy Cup", 140, {"str": 5, "int": 5, "att": 5}),
    ("pocket", "Cursed Red Spellbook", 160, {"str": 20, "dex": 10, "int": 10, "luk": 10, "att": 10}),
    ("pocket", "Cursed Blue Spellbook", 160, {"str": 10, "dex": 10, "int": 20, "luk": 10, "matt": 10}),
    ("pocket", "Cursed Green Spellbook", 160, {"str": 10, "dex": 20, "int": 10, "luk": 10, "att": 10}),
    ("pocket", "Cursed Yellow Spellbook", 160, {"str": 10, "dex": 10, "int": 10, "luk": 20, "att": 10}),
    ("emblem", "Gold Maple Leaf Emblem", 100, {"str": 10, "att": 2}),
    ("emblem", "Mitra's Rage: Warrior", 200, {"str": 40, "att": 5}),
    ("hat", "Royal Warrior Helm", 150, {"str": 40, "att": 2, "ignoreGuard": 10}),
    ("hat", "Eternal Knight Helm", 250, {"str": 80, "att": 10, "ignoreGuard": 15}),
    ("top", "Eagle Eye Warrior Armor", 150, {"str": 30, "att": 2, "ignoreGuard": 5}),
    ("top", "Eternal Knight Armor", 250, {"str": 50, "att": 6, "ignoreGuard": 5}),
    ("bottom", "Trixter Warrior Pants", 150, {"str": 30, "att": 2, "ignoreGuard": 5}),
    ("bottom", "Eternal Knight Pants", 250, {"str": 50, "att": 6, "ignoreGuard": 5}),
    ("shoulder", "AbsoLab Knight Shoulder", 160, {"str": 14, "att": 10}),
    ("shoulder", "Arcane Umbra Knight Shoulder", 200, {"str": 35, "att": 20}),
    ("shoulder", "Eternal Knight Shoulder", 250, {"str": 51, "att": 28}),
    ("cape", "AbsoLab Knight Cape", 160, {"str": 15, "att": 2}),
    ("cape", "Arcane Umbra Knight Cape", 200, {"str": 35, "att": 6}),
    ("cape", "Eternal Knight Cape", 250, {"str": 50, "att": 9}),
    ("gloves", "AbsoLab Knight Gloves", 160, {"str": 20, "att": 5}),
    ("gloves", "Arcane Umbra Knight Gloves", 200, {"str": 40, "att": 9}),
    ("gloves", "Eternal Knight Gloves", 250, {"str": 55, "att": 12}),
    ("shoes", "AbsoLab Knight Shoes", 160, {"str": 20, "att": 5}),
    ("shoes", "Arcane Umbra Knight Shoes", 200, {"str": 40, "att": 9}),
    ("shoes", "Eternal Knight Shoes", 250, {"str": 55, "att": 12}),
    ("medal", "Chaos Vellum Crusher", None, {"bossDmg": 5}),
    ("medal", "Seven Day Monster Parker", 100, {"str": 7, "att": 7, "ignoreGuard": 10}),
    ("medal", "THE RED", None, {"str": 7, "att": 7, "bossDmg": 5}),
    ("medal", "Immortal Legacy", 250, {"str": 10, "att": 10, "bossDmg": 10}),
    ("heart", "Plasma Heart", 130, {"str": 10, "att": 5, "ignoreGuard": 15}),
    ("heart", "Black Heart", 120, {"str": 50, "att": 77, "bossDmg": 30, "ignoreGuard": 30}),
    ("heart", "Total Control", 200, {"str": 25, "att": 15, "ignoreGuard": 30}),
    ("badge", "Crystal Ventus Badge", 130, {"str": 10, "att": 5}),
    ("badge", "Seven Days Badge", 100, {"str": 7, "att": 7, "ignoreGuard": 10}),
    ("badge", "Genesis Badge", 200, {"str": 15, "att": 10}),
    ("badge", "Ghost Ship Exorcist", 150, {"str": 3, "att": 2}),
    ("badge", "Sengoku Hakase Badge", 160, {"str": 10, "att": 10}),
]


@pytest.mark.parametrize("slot, name, level, stats", APPENDIX_A)
def test_appendix_a_items_resolve_once_with_the_listed_stats(slot, name, level, stats):
    found = [i for i in catalog.for_class(info("Hero")) if i["slot"] == slot and i["name"] == name]
    assert len(found) == 1
    assert found[0]["level"] == level
    assert {k: found[0]["base"].get(k, 0) for k in stats} == stats


def test_class_armor_exists_once_per_job_group():
    for name in ("eternal-{}-hat", "faf-{}-top", "eternal-{}-bottom"):
        for job, word in {"warrior": "warrior", "magician": "mage", "archer": "archer", "thief": "thief",
                          "pirate": "pirate"}.items():
            assert sum(i["id"] == f"{job}:{name.format(word)}" for i in catalog.database()["items"]) == 1


def test_thief_absolab_gloves_use_the_wiki_stats():
    assert catalog.by_id()["thief:abs-gloves"]["base"] == {"dex": 20, "luk": 20, "att": 5}


def test_upgrade_flags_follow_the_item_rules():
    items = catalog.by_id()
    assert not items["black-heart"]["flame"] and not items["black-heart"]["potential"]
    assert not items["black-heart"]["starforce"] and items["black-heart"]["unmodifiable"]
    assert not items["genesis-badge"]["potential"] and items["ghost-ship-exorcist"]["potential"]
    assert items["ghost-ship-exorcist"]["max_stars"] == 22
    assert not items["immortal-legacy"]["starforce"] and not items["immortal-legacy"]["potential"]
    assert items["immortal-legacy"]["flame"] and not items["seven-day-monster-parker"]["flame"]
    for pocket in ("phg", "will-red-book", "will-blue-book", "will-green-book", "will-yellow-book"):
        assert items[pocket]["flame"] and not items[pocket]["potential"] and not items[pocket]["starforce"]
    assert items["will-red-book"]["set_label"] == "Pitched Boss" and items["phg"]["set_label"] == "Boss Accessory"
    assert not items["giant-fear"]["flame"] and items["giant-fear"]["potential"]
    assert not items["warrior:eternal-shoulder"]["flame"]
    assert items["warrior:eternal-warrior-cape"]["flame"]
    assert not items["warrior:mithra-rage-warrior"]["starforce"]
    assert items["sweetwater-pendant"]["flame_advantaged"] is False
    assert [a["max"] for a in items["original-sin-of-pride"]["addons"]] == [3]
    assert items["warrior:ruin-force-shield"]["base"]["finalDmg"] == 10
    assert items["warrior:astra-force-shield"]["addons"] == [
        {"id": "rfs_infused", "label": "RFS infused (Astra Infusion skill)", "max": 1, "per": {"finalDmg": 10}}]


def stages(item_id):
    return [(v["stage"], v["version"], v["base"], v["max_stars"]) for v in catalog.by_id()[item_id]["variants"]]


def test_astra_stages_follow_the_wiki_gms_tab():
    assert stages("warrior:astra-medal") == [
        (1, 1, {"str": 10, "dex": 10, "att": 7}, 15),
        (2, 1, {"str": 15, "dex": 15, "att": 7}, 20),
        (3, 1, {"str": 20, "dex": 20, "att": 7}, 30),
    ]
    assert stages("warrior:astra-sacred-aegis")[0] == (1, 1, {"str": 40, "dex": 10, "att": 47}, 15)
    assert stages("magician:astra-leaf-shield")[2] == (3, 1, {"int": 50, "luk": 20, "matt": 47}, 30)
    assert [s[2]["str"] for s in stages("pirate:astra-decacore-controller")] == [5, 7, 10]
    assert [(s[2], s[3]) for s in stages("magician:astra-kanna-talisman")] == [
        ({"int": 75, "luk": 75, "matt": 260}, 30), ({"int": 85, "luk": 85, "matt": 260}, 30),
        ({"int": 95, "luk": 95, "matt": 260}, 30),
    ]
    katara = stages("thief:astra-blade")
    assert katara[0] == (1, 1, {"str": 10, "dex": 10, "luk": 80, "att": 225}, 30)
    assert katara[3] == (1, 2, {"str": 10, "dex": 10, "luk": 15, "att": 171, "bossDmg": 30, "ignoreGuard": 10}, 30)
    assert catalog.by_id()["thief:astra-blade"]["weapon_like"] is True
    # Demon Slayer's two Force Shield versions differ only in HP, so one choice is offered.
    assert {s[1] for s in stages("warrior:astra-force-shield")} == {1}


def test_wiki_parser_prefers_non_kms_and_gms_values():
    page = """==Equipment==
===Stage 1===
<tabber>
|-|KMS=
{{Equipment
|incSTR=10
|incWAttack=7
|starForceEnhancements=15
}}
|-|Non-KMS=
{{Equipment
|incSTR=40
|incWAttack=47
|incBossDamage=30%
|scrollEnhancements=Non-GMS: 9<br />GMS: 10
|starForceEnhancements=15
}}
</tabber>
===Version 2: Stage 2===
{{Equipment
|incSTR=1,000
|starForceEnhancements=Non-GMS: 20<br />GMS: 22
}}
"""
    parsed = build_tool.parse_astra(page)
    assert build_tool._wiki_base(parsed[(1, 1)]) == {"str": 40, "att": 47, "bossDmg": 30}
    assert build_tool._number(parsed[(2, 2)]["starForceEnhancements"]) == 22
    assert build_tool._number(parsed[(2, 2)]["incSTR"]) == 1000
    with pytest.raises(ValueError):
        build_tool.parse_astra("==Nothing here==")


def test_generated_file_records_its_sources():
    data = json.loads((ROOT / "src/itemswap/data/items.json").read_text(encoding="utf-8"))
    urls = [s["url"] for s in data["sources"]]
    assert sum("whackybeanz.com/api/getEquips" in u for u in urls) == 53
    assert any("maplestorywiki.net/w/Astra_Katara" in u for u in urls)
    assert all(len(s["sha256"]) == 64 for s in data["sources"])
