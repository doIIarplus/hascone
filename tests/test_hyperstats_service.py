import copy
import json
from pathlib import Path

import pytest
from test_app import BASE, ID, client, get, post  # noqa: F401  (client is a fixture)

import app
from hyperstats import optimizer
from scouter import client as scouter_client
from scouter import profiles, service

CASE = json.loads((Path(__file__).parent / "fixtures/boss_cuts.json").read_text(encoding="utf-8"))["cases"][0]
SPREAD = dict(luk=10, crit_rate=5, crit_damage=10, ied=10, damage=10, boss_damage=10, attack=10)
SHADOWER = profiles.class_info("Shadower")


def settings(**changes):
    levels = {key: SPREAD.get(key, 0) for key in optimizer.stats()}
    return {"levels": levels, "keep": optimizer.default_keep(SHADOWER), "defense": "380", "crit_rate": None,
            **changes}


@pytest.fixture
def saved(client):
    record = {"id": "base", "created": "2026-10-29T00:00:00+00:00", "fingerprint": "x",
              "input": copy.deepcopy(CASE["user"]), "damage": {"calculatedData": copy.deepcopy(CASE["calculated"])}}
    profiles.write(ID, {"version": 2, "scanned": {}, "inputs": {}, "scan": None, "history": [record], "revision": 0})
    return client


class InlineThread:
    def __init__(self, target, args, **_):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture
def inline(monkeypatch):
    monkeypatch.setattr(service.threading, "Thread", InlineThread)
    monkeypatch.setattr(service, "_job", {"active": False})


def delete(client, path):
    return client.delete(path, base_url=BASE, headers={"X-Hascone-Token": app.TOKEN})


def test_payload_has_the_table_defaults_and_no_saved_settings(saved):
    body = get(saved, f"/api/scouter/characters/{ID}/hyper").json
    assert len(body["stats"]) == 17 and body["stats"][0]["label"] == "STR"
    assert body["keep"] == optimizer.default_keep(SHADOWER)
    assert body["archer"] is False and body["blocked"] is None and body["settings"] is None


def test_optimize_uses_the_scanned_crit_rate_and_saves_the_settings(saved):
    response = post(saved, f"/api/scouter/characters/{ID}/hyper/optimize", {"result_id": "base", "settings": settings()})
    body = response.json
    assert response.status_code == 200 and body["scanned_crit_rate"] == 100
    assert body["budget"] == 1347 and body["fd_percent"]["380"] > 0
    # 100% scanned with level 5 (+5%) is 95% without hyper crit, so level 5 stays.
    assert body["suggested"]["levels"]["crit_rate"] == 5
    stored = profiles.load(ID)["hyper_stats"]
    assert stored["levels"]["luk"] == 10 and stored["crit_rate"] is None and stored["defense"] == "380"
    assert get(saved, f"/api/scouter/characters/{ID}/hyper").json["settings"] == stored


def test_an_entered_crit_rate_overrides_the_scan(saved):
    body = post(saved, f"/api/scouter/characters/{ID}/hyper/optimize",
                {"result_id": "base", "settings": settings(crit_rate=130, keep=[])}).json
    assert body["suggested"]["levels"]["crit_rate"] == 0
    assert profiles.load(ID)["hyper_stats"]["crit_rate"] == 130


@pytest.mark.parametrize("endpoint", ["optimize", "verify"])
@pytest.mark.parametrize(
    "body",
    [[], {"result_id": "base"}, {"result_id": "base", "settings": []}, {"result_id": "base", "settings": {}, "x": 1}],
)
def test_both_endpoints_reject_malformed_requests(saved, endpoint, body):
    response = post(saved, f"/api/scouter/characters/{ID}/hyper/{endpoint}", body)
    assert response.status_code == 400 and "saved calculation" in response.json["error"]


def test_invalid_settings_are_rejected_and_not_saved(saved):
    bad = settings()
    bad["levels"]["ied"] = 16
    response = post(saved, f"/api/scouter/characters/{ID}/hyper/optimize", {"result_id": "base", "settings": bad})
    assert response.status_code == 400 and "0 to 15" in response.json["error"]
    assert "hyper_stats" not in profiles.load(ID)
    response = post(saved, f"/api/scouter/characters/{ID}/hyper/optimize", {"result_id": "gone", "settings": settings()})
    assert response.status_code == 400 and "saved calculation" in response.json["error"]


def test_verify_makes_one_full_calculation_and_saves_the_run(saved, inline, monkeypatch):
    calls = []
    monkeypatch.setattr(scouter_client, "damage",
                        lambda user, event: calls.append(user) or {"calculatedData": copy.deepcopy(CASE["calculated"])})
    response = post(saved, f"/api/scouter/characters/{ID}/hyper/verify", {"result_id": "base", "settings": settings()})
    assert response.status_code == 200 and len(calls) == 1
    run = profiles.load(ID)["history"][0]["hyper_runs"][0]
    suggested = run["suggested"]["levels"]
    assert run["baseline_id"] == "base" and run["settings"]["levels"]["luk"] == 10
    assert run["local_fd_percent"]["380"] > 0 and set(run["scores"]) == {"300", "380"}
    # The call carries the suggested hyper stats in place of the current ones.
    luk = optimizer.value(optimizer.stats()["luk"], suggested["luk"])
    assert calls[0]["stat"]["mainStatAbs"] == format(20000 - 300 + luk, ".12g")
    assert run["changes"]["mainStatAbs"] == calls[0]["stat"]["mainStatAbs"]
    assert service.state()["status"] == "complete"

    assert delete(saved, f"/api/scouter/characters/{ID}/history/base/hyper/{run['id']}").status_code == 200
    assert profiles.load(ID)["history"][0]["hyper_runs"] == []
    assert delete(saved, f"/api/scouter/characters/{ID}/history/base/hyper/{run['id']}").status_code == 400


def test_verify_refuses_when_already_optimized_or_blocked(saved, inline, monkeypatch):
    monkeypatch.setattr(scouter_client, "damage", lambda *_: pytest.fail("called MapleScouter"))
    best = post(saved, f"/api/scouter/characters/{ID}/hyper/optimize",
                {"result_id": "base", "settings": settings()}).json["suggested"]["levels"]
    response = post(saved, f"/api/scouter/characters/{ID}/hyper/verify",
                    {"result_id": "base", "settings": settings(levels=best)})
    assert response.status_code == 400 and "Already optimized" in response.json["error"]
    over = settings(levels={key: 15 for key in optimizer.stats() if key != "df_tf"})
    response = post(saved, f"/api/scouter/characters/{ID}/hyper/verify", {"result_id": "base", "settings": over})
    assert response.status_code == 400 and "points" in response.json["error"]


def test_scouter_rejecting_the_suggestion_saves_nothing(saved, inline, monkeypatch):
    rejected = {**copy.deepcopy(CASE["calculated"]), "boss380_hexaStat": -6}
    monkeypatch.setattr(scouter_client, "damage", lambda *_: {"calculatedData": rejected})
    post(saved, f"/api/scouter/characters/{ID}/hyper/verify", {"result_id": "base", "settings": settings()})
    assert service.state()["status"] == "error" and "100% critical rate" in service.state()["message"]
    assert "hyper_runs" not in profiles.load(ID)["history"][0]
