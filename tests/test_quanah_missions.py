import pytest
from test_app import BASE, client, get  # noqa: F401  (client is a fixture)

import app
from quanah import missions


@pytest.fixture(autouse=True)
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(missions, "PATH", tmp_path / "quanah_missions.json")


def put(client, path, body):
    return client.put(path, json=body, base_url=BASE, headers={"X-Hascone-Token": app.TOKEN})


def delete(client, path):
    return client.delete(path, base_url=BASE, headers={"X-Hascone-Token": app.TOKEN})


def test_catalog_matches_the_mission_tables():
    groups = {g["key"]: g for g in missions.catalog()["groups"]}
    count = lambda key: sum(len(c["missions"]) for c in groups[key]["chains"])  # noqa: E731
    points = lambda key: sum(m["points"] for c in groups[key]["chains"] for m in c["missions"])  # noqa: E731
    keys = ("inspector", "battlesim", "bosses", "starforce")
    assert [points(k) for k in keys] == [20700, 41000, 38700, 14250]
    assert [count(k) for k in keys] == [20, 30, 40, 20]
    assert [groups[k]["type"] for k in groups] == ["round", "round", "permanent", "permanent"]
    ids = [m["id"] for g in groups.values() for c in g["chains"] for m in c["missions"]]
    assert len(ids) == len(set(ids))


def test_completing_a_mission_completes_its_chain_up_to_it():
    done = missions.set_done("level-20", True)["done"]
    assert done == ["level-5", "level-10", "level-15", "level-20"]
    # Only that boss's lower difficulties.
    done = missions.set_done("boss-kalos-the-guardian-chaos", True)["done"]
    kalos = [i.removeprefix("boss-kalos-the-guardian-") for i in done if i.startswith("boss-kalos")]
    assert kalos == ["easy", "normal", "chaos"]
    assert not any(i.startswith("boss-lotus") for i in done)
    done = missions.set_done("sf-17", True)["done"]
    stars = [i for i in done if i.startswith("sf-")]
    assert stars == ["sf-5", "sf-8", "sf-10", "sf-12", "sf-15", "sf-16", "sf-17"]
    done = missions.set_done("floor-15", True)["done"]
    assert [i for i in done if i.startswith("floor-")] == ["floor-5", "floor-10", "floor-15"]


def test_star_force_can_skip_the_cascade_but_other_chains_cannot():
    assert missions.set_done("sf-17", True, False)["done"] == ["sf-17"]
    assert missions.set_done("sf-10", True, False)["done"] == ["sf-10", "sf-17"]
    # Undoing one without the cascade leaves the later ones.
    assert missions.set_done("sf-10", False, False)["done"] == ["sf-17"]
    # Bosses and levels always cascade.
    assert missions.set_done("level-10", True, False)["done"][:2] == ["level-5", "level-10"]
    with pytest.raises(ValueError):
        missions.set_done("sf-5", True, "no")


def test_undoing_a_mission_undoes_every_later_one_in_its_chain():
    missions.set_done("level-50", True)
    missions.set_done("sf-22", True)
    done = missions.set_done("level-30", False)["done"]
    levels = [i for i in done if i.startswith("level-")]
    assert levels == ["level-5", "level-10", "level-15", "level-20", "level-25"]
    assert "sf-22" in done


def test_summary_points_grade_and_counts():
    s = missions.payload()["summary"]
    assert (s["points"], s["grade"], s["completed"], s["total"]) == (0, 1, 0, 110)
    assert s["next"] == {"grade": 2, "points": 5000}
    missions.set_done("level-40", True)  # 50+50+100+200+300+400+500+600 = 2200, round
    missions.set_done("boss-lotus-extreme", True)  # 50+250+1300 = 1600, permanent
    missions.set_done("sf-22", True)  # 50+50+100+100+150*3+200*2+300+400+600 = 2450, permanent
    s = missions.payload()["summary"]
    assert (s["points"], s["round"], s["permanent"], s["completed"]) == (6250, 2200, 4050, 8 + 3 + 12)
    assert s["grade"] == 2 and s["next"] == {"grade": 3, "points": 10000}
    for group in missions.catalog()["groups"]:
        for chain in group["chains"]:
            missions.set_done(chain["missions"][-1]["id"], True)
    s = missions.payload()["summary"]
    assert (s["grade"], s["next"], s["completed"], s["points"]) == (5, None, 110, s["max_points"])


def test_reset_round_keeps_permanent_missions():
    missions.set_done("level-100", True)
    missions.set_done("floor-150", True)
    missions.set_done("boss-jupiter-normal", True)
    missions.set_done("sf-5", True)
    payload = missions.reset_round()
    assert payload["done"] == ["boss-jupiter-normal", "sf-5"]
    assert payload["summary"]["round"] == 0 and payload["summary"]["permanent"] == 2050


def test_bad_requests_are_refused():
    with pytest.raises(ValueError, match="Unknown mission"):
        missions.set_done("level-3", True)
    with pytest.raises(ValueError, match="true or false"):
        missions.set_done("level-5", "yes")


def test_api(client):  # noqa: F811
    assert get(client, "/api/quanah/missions").get_json()["summary"]["completed"] == 0
    body = put(client, "/api/quanah/missions/floor-10", {"done": True}).get_json()
    assert body["done"] == ["floor-5", "floor-10"]
    assert put(client, "/api/quanah/missions/nope", {"done": True}).status_code == 400
    put(client, "/api/quanah/missions/sf-8", {"done": True})
    assert delete(client, "/api/quanah/missions/round").get_json()["done"] == ["sf-5", "sf-8"]
    # Progress is saved, not kept in memory.
    assert missions.PATH.exists()
    assert get(client, "/api/quanah/missions").get_json()["done"] == ["sf-5", "sf-8"]


@pytest.mark.parametrize(
    "text", ['{"done": ["level-5"', '"oops"', '{"done": "level-5"}', '{"done": [5, "sf-5"]}']
)
def test_a_damaged_save_file_does_not_break_the_tracker(text):
    missions.PATH.write_text(text, encoding="utf-8")
    done = missions.read()
    assert done in ([], ["sf-5"])
    if not done:
        # The damaged file is kept aside, so it can be recovered.
        assert missions.PATH.with_suffix(".damaged.json").read_text(encoding="utf-8") == text
    assert missions.set_done("level-10", True)["done"][:2] == ["level-5", "level-10"]


def test_an_unreadable_save_file_fails_without_overwriting_progress():
    missions.set_done("level-50", True)
    saved = missions.PATH.read_text(encoding="utf-8")

    def locked(*args, **kwargs):
        raise PermissionError("in use by another process")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(type(missions.PATH), "read_text", locked)
        with pytest.raises(PermissionError):
            missions.set_done("sf-5", True)
    assert missions.PATH.read_text(encoding="utf-8") == saved
