import copy
import threading
from unittest.mock import Mock

import pytest
from test_app import BASE, ID, client, get, post

from scouter import client as scouter_client
from scouter import profiles, service
from scouter.hexa_order import saved_order
from utils.payload_data import read_payload_json

ENDPOINT = f"/api/scouter/characters/{ID}/hexa-order"
FRAGMENTS = {"class_hexa": [["Fragment route"]]}
SOL = {"class_hexa": [["Sol Erda route"]]}


@pytest.fixture
def saved(client, monkeypatch):
    data = profiles.load(ID)
    user = read_payload_json("src/scouter/data/defaults.json")
    user["stat"]["myClass"] = data["class_info"]["key"]
    data["history"] = [{
        "id": "base", "created": profiles.now(), "fingerprint": "baseline", "input": user,
        "damage": {"calculatedData": {"specEfficiency": {"dmgeff1": 0.001}, "hexaUsed": [1, 20]}},
        "order": copy.deepcopy(FRAGMENTS), "order_error": None,
    }]
    profiles.write(ID, data)
    monkeypatch.setattr(service, "_job", {"active": False})
    return client


@pytest.fixture
def inline(monkeypatch):
    class InlineThread:
        def __init__(self, target, args, **_):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(service.threading, "Thread", InlineThread)


def select(client, resource="sol_erda", **extra):
    return post(client, ENDPOINT, {"result_id": "base", "resource": resource, **extra})


def test_legacy_fragments_are_reused_without_network_or_changing_the_baseline(saved, monkeypatch):
    fetch = Mock()
    monkeypatch.setattr(scouter_client, "hexa_order", fetch)
    before = profiles.load(ID)
    response = select(saved, "fragments")
    assert response.status_code == 200 and response.json["active"] is False
    assert response.json["kind"] == "hexa_order" and "result_id" not in response.json
    after = profiles.load(ID)
    assert after["hexa_resource"] == "fragments"
    assert after["history"] == before["history"] and after["revision"] == before["revision"]
    fetch.assert_not_called()


def test_routes_are_cached_per_resource_and_per_baseline(saved, inline, monkeypatch):
    fetch = Mock(return_value=copy.deepcopy(SOL))
    monkeypatch.setattr(scouter_client, "hexa_order", fetch)
    original = profiles.load(ID)["history"][0]
    response = select(saved)
    assert response.status_code == 200 and response.json["status"] == "complete"
    record = profiles.load(ID)["history"][0]
    assert saved_order(record, "sol_erda") == SOL
    assert saved_order(record, "fragments") == FRAGMENTS
    assert record["input"] == original["input"] and record["damage"] == original["damage"]
    assert get(saved, f"/api/scouter/characters/{ID}").json["hexa_resource"] == "sol_erda"
    select(saved, "fragments")
    select(saved, "sol_erda")
    assert fetch.call_count == 1

    data = profiles.load(ID)
    other = copy.deepcopy(original)
    other["id"] = "other"
    data["history"].append(other)
    profiles.write(ID, data)
    post(saved, ENDPOINT, {"result_id": "other", "resource": "sol_erda"})
    assert fetch.call_count == 2
    assert all(saved_order(record, "sol_erda") == SOL for record in profiles.load(ID)["history"])


def test_refresh_is_explicit_and_updates_only_the_selected_route(saved, inline, monkeypatch):
    monkeypatch.setattr(scouter_client, "hexa_order", Mock(return_value=copy.deepcopy(SOL)))
    select(saved)
    refreshed = {"class_hexa": [["Updated Sol route"]]}
    scouter_client.hexa_order.return_value = refreshed
    select(saved, refresh=True)
    assert scouter_client.hexa_order.call_count == 2
    record = profiles.load(ID)["history"][0]
    assert saved_order(record, "sol_erda") == refreshed
    assert saved_order(record, "fragments") == FRAGMENTS
    assert record["order"] == FRAGMENTS


@pytest.mark.parametrize("failure", ["cancel", "network", "delete"])
def test_failed_or_cancelled_routes_do_not_replace_saved_results(saved, inline, monkeypatch, failure):
    def fetch(user, result, cancelled, resource):
        if failure == "cancel":
            cancelled.set()
        elif failure == "network":
            raise ValueError("MapleScouter returned HTTP 503")
        else:
            data = profiles.load(ID)
            data["history"] = []
            profiles.write(ID, data)
        return copy.deepcopy(SOL)

    monkeypatch.setattr(scouter_client, "hexa_order", fetch)
    response = select(saved)
    assert response.json["status"] == ("stopped" if failure == "cancel" else "error")
    history = profiles.load(ID)["history"]
    if failure == "delete":
        assert history == []
    else:
        assert history[0]["order"] == FRAGMENTS and "hexa_orders" not in history[0]


def test_failed_refresh_keeps_the_previous_route_available(saved, inline, monkeypatch):
    monkeypatch.setattr(scouter_client, "hexa_order", Mock(return_value=copy.deepcopy(SOL)))
    select(saved)
    scouter_client.hexa_order.side_effect = ValueError("MapleScouter returned HTTP 503")
    assert select(saved, refresh=True).json["status"] == "error"
    assert saved_order(profiles.load(ID)["history"][0], "sol_erda") == SOL


def test_route_save_preserves_concurrent_input_and_history_edits(saved, inline, monkeypatch):
    original = profiles.load(ID)["history"][0]

    def fetch(user, result, cancelled, resource):
        assert user == original["input"] and result == original["damage"]["calculatedData"]
        data = profiles.load(ID)
        data["inputs"]["stat.level"] = "285"
        data["revision"] += 1
        data["history"][0]["name"] = "Renamed while calculating"
        data["history"].append({"id": "newer"})
        profiles.write(ID, data)
        return copy.deepcopy(SOL)

    monkeypatch.setattr(scouter_client, "hexa_order", fetch)
    select(saved)
    data = profiles.load(ID)
    assert data["inputs"]["stat.level"] == "285" and data["revision"] == 1
    assert data["history"][0]["name"] == "Renamed while calculating"
    assert data["history"][1] == {"id": "newer"}
    assert saved_order(data["history"][0], "sol_erda") == SOL


@pytest.mark.parametrize("body", [[], {}, {"result_id": "base"}, {"result_id": "base", "resource": []},
                                   {"result_id": "base", "resource": "kms"},
                                   {"result_id": "base", "resource": "sol_erda", "refresh": "false"},
                                   {"result_id": "base", "resource": "sol_erda", "extra": 1}])
def test_malformed_requests_do_not_change_the_saved_preference(saved, body):
    assert post(saved, ENDPOINT, body).status_code == 400
    assert "hexa_resource" not in profiles.load(ID)


def test_busy_missing_baseline_and_unauthenticated_requests_are_rejected(saved, monkeypatch):
    assert saved.post(ENDPOINT, json={"result_id": "base", "resource": "sol_erda"}, base_url=BASE).status_code == 403
    assert post(saved, ENDPOINT, {"result_id": "missing", "resource": "sol_erda"}).status_code == 400
    monkeypatch.setattr(service, "_job", {"active": True})
    assert select(saved).status_code == 400
    assert "hexa_resource" not in profiles.load(ID)


def test_snapshot_defaults_to_fragments(saved):
    assert get(saved, f"/api/scouter/characters/{ID}").json["hexa_resource"] == "fragments"


@pytest.mark.parametrize("resource", ["fragments", "sol_erda"])
def test_route_client_sends_one_order_request_using_the_saved_damage(saved, monkeypatch, resource):
    baseline = profiles.load(ID)["history"][0]
    original = copy.deepcopy(baseline)
    monkeypatch.setattr(scouter_client, "public_headers", lambda _: {"api-key": "test"})
    fetch = Mock(return_value=copy.deepcopy(SOL))
    monkeypatch.setattr(scouter_client, "_post", fetch)
    assert scouter_client.hexa_order(baseline["input"], baseline["damage"]["calculatedData"], threading.Event(), resource) == SOL
    fetch.assert_called_once()
    endpoint, body, _, _ = fetch.call_args.args
    assert endpoint.startswith("/api/calc/hexa-order?class=")
    assert body["sole"] is (resource == "sol_erda") and body["start"] is True
    assert body["userStat"]["isGMS"] is True
    assert body["specEff"] == baseline["damage"]["calculatedData"]["specEfficiency"]
    assert body["myHexa"]["hexaSkill_used"] == {"sole_Erda": 1, "sole_ErdaPrice": 20}
    assert baseline == original


def test_client_rejects_invalid_order_responses(saved, monkeypatch):
    baseline = profiles.load(ID)["history"][0]
    monkeypatch.setattr(scouter_client, "public_headers", lambda _: {})
    monkeypatch.setattr(scouter_client, "_post", lambda *_: {"class_hexa": None})
    with pytest.raises(ValueError, match="did not return an upgrade order"):
        scouter_client.hexa_order(baseline["input"], baseline["damage"]["calculatedData"], threading.Event(), "sol_erda")
