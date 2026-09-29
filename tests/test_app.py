import time
from unittest.mock import Mock

import numpy as np
import pytest

import app
from flaming import characters
from scouter import profiles

ID = "a" * 32
BASE = "http://127.0.0.1:5001"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(characters, "PROFILE_DIR", tmp_path / "characters")
    monkeypatch.setattr(profiles, "DIRECTORY", tmp_path / "scouter")
    characters.write({"id": ID, "name": "Example", "class": "Shadower", "equipment": {}})
    app.generation += 1
    app.preview = None
    app.job = {"active": False, "status": "idle"}
    return app.app.test_client()


def post(client, path, body=None):
    return client.post(path, json=body or {}, base_url=BASE, headers={"X-Hascone-Token": app.TOKEN})


def get(client, path):
    return client.get(path, base_url=BASE)


def test_registry_and_scouter_form(client):
    assert get(client, "/api/characters").json["profiles"][0]["name"] == "Example"
    p = get(client, f"/api/scouter/characters/{ID}").json
    assert p["values"]["stat"]["mainStatBase"] is None
    assert p["missing"]
    assert (
        post(
            client,
            f"/api/scouter/characters/{ID}",
            {"revision": 0, "changes": {"stat.mainStatBase": "1234"}},
        ).status_code
        == 200
    )
    assert get(client, f"/api/scouter/characters/{ID}").json["values"]["stat"]["mainStatBase"] == "1234"


def test_host_and_cross_origin_write_protection(client):
    assert client.get("/api/session", base_url="http://evil.test:5001").status_code == 403
    assert client.post("/api/scan/cancel", base_url=BASE).status_code == 403


def test_new_character_from_public_rankings(client, monkeypatch):
    response = Mock()
    response.json.return_value = {
        "ranks": [{"characterName": "ActualName", "jobName": "Mercedes", "level": 280}]
    }
    monkeypatch.setattr(characters.requests, "get", Mock(return_value=response))
    r = post(client, "/api/characters", {"name": "ActualName"})
    assert r.status_code == 200, r.json
    assert r.json["class"] == "Mercedes"
    assert post(client, "/api/characters", {"name": "ActualName"}).json["id"] == r.json["id"]


def test_accented_character_names_preserve_accents_and_avoid_duplicates(client, monkeypatch):
    response = Mock()
    response.json.return_value = {
        "ranks": [{"characterName": "Bumblë", "jobName": "Mercedes", "level": 280}]
    }
    lookup = Mock(return_value=response)
    monkeypatch.setattr(characters.requests, "get", lookup)
    result = post(client, "/api/characters", {"name": "Bumble\u0308"})
    assert result.status_code == 200, result.json
    assert result.json["name"] == "Bumblë"
    assert lookup.call_args.kwargs["params"]["character_name"] == "Bumblë"
    assert post(client, "/api/characters", {"name": "BUMBLË"}).json["id"] == result.json["id"]
    assert post(client, "/api/characters", {"name": "Bumble"}).status_code == 400


@pytest.mark.parametrize("name", ["x", "a" * 17, "Bum ble", "../Bumblë", "Bumblë!"])
def test_invalid_character_names_are_rejected_before_lookup(client, monkeypatch, name):
    lookup = Mock(side_effect=AssertionError("Invalid names must not reach Nexon"))
    monkeypatch.setattr(characters.requests, "get", lookup)
    assert post(client, "/api/characters", {"name": name}).status_code == 400
    lookup.assert_not_called()


def test_countdown_cancel_never_captures(client, monkeypatch):
    import capture

    capture_mock = Mock(side_effect=AssertionError("must not capture"))
    monkeypatch.setattr(capture, "frame", capture_mock)
    r = post(
        client, "/api/scan", {"character": ID, "mode": "hover:hat", "slot": "hat", "window": 1, "delay": 0.2}
    )
    assert r.status_code == 200
    assert post(client, "/api/scan/cancel").status_code == 200
    time.sleep(0.3)
    capture_mock.assert_not_called()
    assert characters.load(ID)["equipment"] == {}


def preview(mode, result, slot="hat"):
    import cv2

    gear = mode == "equipment" or mode.startswith("hover:")
    app.preview = {
        "body": {"character": ID, "mode": mode, "slot": slot},
        "result": result,
        "stamp": profiles.fingerprint(characters.load(ID) if gear else profiles.load(ID)["inputs"]),
        "png": cv2.imencode(".png", np.zeros((1080, 1920, 3), np.uint8))[1].tobytes(),
    }
    app.job = {"active": False, "status": "review"}


def test_scan_save_revision_conflict_preserves_manual_edit(client):
    preview("overview", {"values": {"stat.mainStatBase": {"value": "999", "confidence": 1}}, "errors": []})
    profiles.save_inputs(ID, {"revision": 0, "changes": {"stat.mainStatBase": "1234"}})
    r = post(client, "/api/scan/save")
    assert r.status_code == 400
    assert profiles.load(ID)["inputs"]["stat.mainStatBase"] == "1234"


def test_review_does_not_save_until_accepted(client):
    preview("overview", {"values": {"stat.mainStatBase": {"value": "900", "confidence": 1}}, "errors": []})
    assert "stat.mainStatBase" not in profiles.load(ID)["inputs"]
    assert post(client, "/api/scan/save").status_code == 200
    assert profiles.load(ID)["inputs"]["stat.mainStatBase"] == "900"
    assert post(client, "/api/scan/save").status_code == 400


def test_scouter_steps_follow_class_roles(client):
    steps = get(client, f"/api/characters/{ID}/steps").json
    assert [x["label"] for x in steps[1:4]] == ["LUK breakdown", "DEX breakdown", "STR breakdown"]


def test_erel_light_profile_creation_and_scouter(client, monkeypatch):
    from unittest.mock import Mock

    from flaming.profiles import classes
    response = Mock()
    response.json.return_value = {"ranks": [{"characterName":"ErelTest", "jobName":"Erel Light", "level":267}]}
    monkeypatch.setattr(characters.requests,"get",Mock(return_value=response))
    result = post(client,"/api/characters",{"name":"ErelTest"})
    assert result.status_code == 200, result.json
    identifier = result.json["id"]
    assert result.json["class"] == "ErelLight"
    roles = classes()["ErelLight"]
    assert roles["main_stats"] == ["STR"]
    assert roles["secondary_stats"] == ["DEX"]
    assert roles["att"] == "ATT"
    assert profiles.load(identifier)["class_info"]["name"] == "Erel Light"
    steps = get(client,f"/api/characters/{identifier}/steps").json
    assert steps[1]["label"] == "STR breakdown"


def test_manual_flame_correction_persists_and_recalculates(client):
    data=characters.load(ID)
    data['equipment']['belt']={'name':'Dreamy Belt','updated':'old','flameable':True,
        'stats':[{'name':'LUK','value':3,'percent':False}],
        'starforce':{'stars':25}}
    characters.write(data)
    endpoint=f'/api/characters/{ID}/equipment/belt/flame'
    body={'item':'Dreamy Belt','updated':'old','values':{'LUK':36,'INT':102,'All Stats':6,'Reduced level requirement':25}}
    response=post(client,endpoint,body)
    assert response.status_code==200,response.json
    item=characters.load(ID)['equipment']['belt']
    assert {s['name']:s['value'] for s in item['stats']}=={'LUK':36,'INT':102,'All Stats':6,'Reduced level requirement':-25}
    assert item['starforce']=={'stars':25}
    assert response.json['equipment']['belt']['flame_score']>36
    assert post(client,endpoint,body).status_code==400
    body['updated']=item['updated']
    body['values']={'LUK':0}
    response=post(client,endpoint,body)
    assert response.status_code==200,response.json
    assert response.json['equipment']['belt']['flame_score']==0


@pytest.mark.parametrize('values',[{'LUK':-1},{'LUK':1.5},{'LUK':True},{'All Stats':101},{'nope':5},[]])
def test_manual_flame_rejects_invalid_values(client,values):
    response=post(client,f'/api/characters/{ID}/equipment/belt/flame',{'values':values})
    assert response.status_code==400


def test_hexa_stat_count_saves_and_reaches_optimizer(client):
    from scouter.client import optimizer_body
    endpoint=f'/api/scouter/characters/{ID}'
    data=get(client,endpoint).json
    response=post(client,endpoint,{'revision':data['revision'],'changes':{'hexa.hexaStat':'2'}})
    assert response.status_code==200,response.json
    user=profiles.effective(profiles.load(ID))
    assert user['hexa']['hexaStat']==2
    user['hexa']={k:('0' if v is None else v) for k,v in user['hexa'].items()}
    payload=optimizer_body(user,{'hexaUsed':[0,0],'specEfficiency':{}})
    assert payload['myHexa']['hexaStat']==2
    assert payload['myHexa']['hexaStat_opened'] is True
    assert post(client,endpoint,{'revision':response.json['revision'],'changes':{'hexa.hexaStat':'4'}}).status_code==400


def test_collapsed_sections_persist_without_replacing_other_preferences(client,tmp_path,monkeypatch):
    import ui_preferences
    monkeypatch.setattr(ui_preferences,'PATH',tmp_path/'sections.json')
    endpoint='/api/ui/sections'
    assert post(client,endpoint,{'key':'flame//weights','collapsed':True}).status_code==200
    assert post(client,endpoint,{'key':'potential//costs','collapsed':True}).status_code==200
    assert get(client,endpoint).json=={'flame//weights':True,'potential//costs':True}
    assert ui_preferences.read()==get(client,endpoint).json
    post(client,endpoint,{'key':'flame//weights','collapsed':False})
    assert get(client,endpoint).json=={'potential//costs':True}
    assert post(client,endpoint,{'key':'x','collapsed':'false'}).status_code==400


def test_maplescouter_preset_exports_current_inputs_and_blanks(client):
    import json
    from pathlib import Path
    endpoint=f'/api/scouter/characters/{ID}'
    current=get(client,endpoint).json
    post(client,endpoint,{'revision':current['revision'],'changes':{
        'stat.level':'285','stat.mainStatBase':'4321','special.continuosRing':'4','hexa.hexaStat':'2'}})
    response=get(client,f'/api/characters/{ID}/scouter-preset')
    assert response.status_code==200,response.json
    preset=response.json
    assert preset['type']=='maplescouter-manual-preset' and preset['v']==1
    assert preset['label']=='Example'
    data=preset['data']
    assert data['stat']['mainStatBase']=='4321'
    assert data['stat']['critical']==''
    assert data['isGMS'] is True and data['special']['isReboot'] is True
    assert data['seedRing']['continuosRing']['level']=='4'
    assert data['hexa']['hexaStat']==2
    assert not {'history','suggestions','equipment'}.intersection(preset)
    template=json.loads((Path(__file__).parent/'fixtures/scouter_preset_template.json').read_text(encoding='utf-8'))
    def check(value,expected):
        if isinstance(expected,dict):
            for key in expected:
                check(value[key],expected[key])
        elif isinstance(expected,list):
            assert len(value)==len(expected)
            for a,b in zip(value,expected):
                check(a,b)
        elif type(expected) in (float,int):
            assert type(value) in (float,int)
        else:
            assert type(value) is type(expected)
    check(data,template)
    assert profiles.effective(profiles.load(ID))['stat']['critical'] is None
