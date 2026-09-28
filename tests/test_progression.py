from unittest.mock import Mock

from test_app import ID, client, get, post
from test_scouter_suggestions import saved

from scouter import profiles, service, suggestions
from starforce.cost import options


def test_background_comparison_only_once_per_revision(saved,monkeypatch):
    data,gear=saved
    monkeypatch.setattr(service,"_job",{"active":False,"message":"failed","profile":ID})
    monkeypatch.setattr(service,"_suggestion_attempts",{})
    start=Mock(return_value={"active":True,"status":"calculating"})
    monkeypatch.setattr(service,"start_suggestions",start)
    assert service.ensure_suggestions(ID)["active"]
    assert service.ensure_suggestions(ID)["status"]=="needs_retry"
    assert start.call_count==1
    data["starforce_options"]={"discount":True}
    profiles.write(ID,data)
    assert service.ensure_suggestions(ID)["active"]
    assert start.call_count==2


def test_background_reuses_current_result(saved,monkeypatch):
    data,gear=saved
    data["suggestions"]={"fingerprint":data["history"][0]["fingerprint"],"gear_fingerprint":suggestions.signature(gear),"starforce_options":options(None),"model_version":5}
    profiles.write(ID,data)
    start=Mock()
    monkeypatch.setattr(service,"start_suggestions",start)
    assert service.ensure_suggestions(ID)["status"]=="complete"
    start.assert_not_called()


def test_background_requires_current_scouter_result(saved,monkeypatch):
    data,gear=saved
    data["inputs"]["stat.level"]="280"
    profiles.write(ID,data)
    start=Mock()
    monkeypatch.setattr(service,"start_suggestions",start)
    assert service.ensure_suggestions(ID)["status"]=="needs_calculation"
    start.assert_not_called()


def test_summary_shows_unscanned_character_without_fake_score(client):
    summary=get(client,"/api/summary").json["profiles"][0]
    assert summary["name"]=="Example"
    assert summary["hexa"] is None
    assert summary["scanned"]==0


def test_potential_weights_roundtrip_and_validation(client,tmp_path,monkeypatch):
    from cubing import profiles as weights
    monkeypatch.setattr(weights,"SETTINGS_PATH",tmp_path/"weights.json")
    catalog=get(client,"/api/potential-weights").json
    settings={key:catalog[key] for key in ("version","defaults","overrides")}
    settings["overrides"]["Shadower"]={"secondary_weight":0.2,"boss_per_attack":4}
    saved=post(client,"/api/potential-weights",{"revision":catalog["revision"],"settings":settings})
    assert saved.status_code==200
    assert saved.json["effective"]["Shadower"]["all_stat_weight"]==1.4
    settings["overrides"]["Shadower"]["boss_per_attack"]=0
    assert post(client,"/api/potential-weights",{"revision":saved.json["revision"],"settings":settings}).status_code==400
