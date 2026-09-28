from unittest.mock import Mock

from test_app import ID, client, preview

import app
from watching import acceptable, scan_can_save, signature


def test_signature_ignores_ocr_confidence_and_position():
    assert signature({"origin": [1, 2], "values": {"a": {"value": "12", "confidence": .98}}}) == signature({"origin": [2, 3], "values": {"a": {"value": "12", "confidence": .99}}})
    assert not acceptable({"values": {"a": 1}, "errors": ["unread"]})
    assert not acceptable({"values": {}})


def test_ambiguous_stat_and_unknown_slot_require_review():
    assert not scan_can_save({"mode": "tooltip:mainStat"}, {"values": {"base": 1}})
    assert not scan_can_save({"mode": "hover:hat", "slot": "hat"}, {"kind": "hover", "slot_verified": False})


def test_watch_two_reads_auto_save(client, monkeypatch):
    result = {"values": {"stat.mainStatBase": {"value": "900", "confidence": 1}}}
    calls = []
    def read(*args):
        calls.append(1)
        preview("overview", result)
    monkeypatch.setattr(app, "perform_once", read)
    clock = iter(range(0, 100, 2))
    monkeypatch.setattr(app.time, "monotonic", lambda: next(clock))
    app.perform({"watch": True, "mode": "overview"}, app.generation, "", 0)
    assert len(calls) == 2
    assert app.job["status"] == "saved"
    from scouter import profiles
    assert profiles.load(ID)["inputs"]["stat.mainStatBase"] == "900"


def test_watch_excludes_previous_and_cancels(client, monkeypatch):
    result = {"values": {"stat.mainStatBase": {"value": "900", "confidence": 1}}}
    calls = []
    def read(*args):
        calls.append(1)
        preview("overview", result)
        if len(calls) == 3:
            app.generation += 1
    monkeypatch.setattr(app, "perform_once", read)
    clock = iter(range(0, 100, 2))
    monkeypatch.setattr(app.time, "monotonic", lambda: next(clock))
    app.perform({"watch": True, "mode": "overview", "exclude": signature(result)}, app.generation, "", 0)
    assert len(calls) == 3
    from scouter import profiles
    assert "stat.mainStatBase" not in profiles.load(ID)["inputs"]


def test_real_windows_capture_import():
    from utils.wgc_camera import WgcCamera
    assert callable(WgcCamera)


def test_watch_stops_on_dependency_failure(client, monkeypatch):
    import capture
    monkeypatch.setattr(capture, "frame", Mock(side_effect=ImportError("missing capture dependency")))
    app.perform({"watch": True, "mode": "overview", "window": 1}, app.generation, "", 0)
    assert app.job["status"] == "error"
    assert not app.job["active"]
    capture.frame.assert_called_once()


def test_partial_reading_gets_time_to_clear_before_review(client, monkeypatch):
    calls=[]
    def read(*args):
        calls.append(1)
        result={"values":{"stat.mainStatBase":{"value":"900", "confidence":1}}}
        if len(calls)<3:
            result["errors"]=["Cursor covers a row"]
        preview("overview",result)
    monkeypatch.setattr(app,"perform_once",read)
    clock=iter(range(0,100,2))
    monkeypatch.setattr(app.time,"monotonic",lambda:next(clock))
    app.perform({"watch":True,"mode":"overview"},app.generation,"",0)
    assert len(calls)==4
    assert app.job["status"]=="saved"


def test_persistent_partial_reading_still_offers_manual_review(client, monkeypatch):
    calls=[]
    def read(*args):
        calls.append(1)
        preview("overview",{"values":{"stat.mainStatBase":{"value":"900"}},"errors":["Unreadable row"]})
    monkeypatch.setattr(app,"perform_once",read)
    clock=iter(range(0,100,2))
    monkeypatch.setattr(app.time,"monotonic",lambda:next(clock))
    app.perform({"watch":True,"mode":"overview"},app.generation,"",0)
    assert len(calls)>=4
    assert app.job["status"]=="review"
    from scouter import profiles
    assert "stat.mainStatBase" not in profiles.load(ID)["inputs"]
