import copy
import threading
import time

import cv2
import pytest
from test_app import ID, client, get, post
from test_resolution import frame

import app
import hover_queue
from flaming import characters
from flaming.vision import ReadError
from scouter import profiles
from scouter.capture_ready import regions, stable


@pytest.mark.parametrize("filtered_1440p", [False, True])
def test_character_capture_finishes_before_ocr_and_survives_cancel(client, monkeypatch, filtered_1440p):
    import capture
    import ocr_worker

    started, release = threading.Event(), threading.Event()
    image = frame("stats")
    if filtered_1440p:
        image = cv2.resize(image, (2560, 1440), interpolation=cv2.INTER_LINEAR)
    monkeypatch.setattr(capture, "frame", lambda window: image.copy())
    monkeypatch.setattr(capture, "pointer", lambda window: (0, 0))
    result = {"values": {"stat.level": {"value": "280", "confidence": 1}}, "errors": []}
    monkeypatch.setattr(app, "_finalize_result", lambda mode, body, image, pointer, result: result)

    def read(image, mode):
        assert image.shape == (768, 1366, 3)
        started.set()
        assert release.wait(5)
        return copy.deepcopy(result)

    monkeypatch.setattr(ocr_worker, "read", read)
    hover_queue.reset(ID)
    try:
        app.perform({"character": ID, "mode": "overview", "watch": True, "background": True, "window": 1},
                    app.generation, "", 0)
        assert app.job["status"] == "captured"
        assert started.wait(2)
        assert get(client, "/api/scan/queues").json[ID]["pending"] == ["overview"]
        post(client, "/api/scan/cancel")
        other = "b" * 32
        characters.write({"id": other, "name": "Other", "class": "Shadower", "equipment": {}})
        assert post(client, "/api/scan", {"character": other, "mode": "overview", "delay": 15}).status_code == 200
        post(client, "/api/scan/cancel")
    finally:
        release.set()
        for _ in range(200):
            if not hover_queue.status(ID)["pending"]:
                break
            time.sleep(.01)
    assert hover_queue.status(ID)["failed"] == {}
    assert profiles.load(ID)["inputs"]["stat.level"] == "280"
    assert profiles.load(other)["inputs"] == {}
    hover_queue.reset(ID)


def test_background_scan_preserves_manual_edits_but_allows_earlier_scan(client, monkeypatch):
    import ocr_worker

    result = {"values": {"stat.level": {"value": "280", "confidence": 1}}}
    monkeypatch.setattr(ocr_worker, "read", lambda image, mode: copy.deepcopy(result))
    monkeypatch.setattr(app, "_finalize_result", lambda mode, body, image, pointer, result: result)
    body = {"character": ID, "mode": "overview"}
    profiles.save_scan(ID, {"stat.level": {"value": "279"}}, [], profiles.now())
    app._process_character_capture(body, None, {})
    assert profiles.load(ID)["inputs"]["stat.level"] == "280"
    current = profiles.load(ID)
    profiles.save_inputs(ID, {"revision": current["revision"], "changes": {"stat.level": "281"}})
    with pytest.raises(ValueError, match="changed during processing"):
        app._process_character_capture(body, None, {})
    assert profiles.load(ID)["inputs"]["stat.level"] == "281"


def test_background_errors_leave_saved_inputs_untouched(client, monkeypatch):
    import ocr_worker

    monkeypatch.setattr(ocr_worker, "read", lambda image, mode: {"values": {"stat.level": {"value": "280"}}, "errors": ["unclear"]})
    monkeypatch.setattr(app, "_finalize_result", lambda mode, body, image, pointer, result: result)
    with pytest.raises(ValueError, match="unclear"):
        app._process_character_capture({"character": ID, "mode": "overview"}, None, {})
    assert profiles.load(ID)["inputs"] == {}


def test_character_regions_validate_cursor_and_reject_changing_stats():
    info = {"main": "INT", "sub": "LUK"}
    image = frame("stats")
    crops = regions(image, "overview", (0, 0), info)
    stable(crops, crops)
    changed = [crop.copy() for crop in crops]
    changed[0][:] = 255 - changed[0]
    with pytest.raises(ReadError, match="changing"):
        stable(crops, changed)
    regions(frame("int"), "tooltip:mainStat", (661, 397), info)
    with pytest.raises(ReadError, match="Hover"):
        regions(frame("int"), "tooltip:subStat", (661, 397), info)


def test_snapshot_name_persists_and_validates(client):
    data = profiles.load(ID)
    data["history"] = [{"id": "example", "created": profiles.now(), "fingerprint": "old"}]
    profiles.write(ID, data)
    path = f"/api/scouter/characters/{ID}/history/example/name"
    assert post(client, path, {"name": " Before upgrades "}).json == {"name": "Before upgrades"}
    assert profiles.load(ID)["history"][0]["name"] == "Before upgrades"
    assert post(client, path, {"name": "x" * 81}).status_code == 400
    assert post(client, path, {"name": ""}).json == {"name": ""}
    assert post(client, path.replace("example", "missing"), {"name": "test"}).status_code == 400


def test_tooltip_heading_can_be_partly_covered_by_cursor():
    from scouter.vision import anchor, applied_anchor

    image = frame("int").copy()
    expected = applied_anchor(image)
    x, y = expected
    image[y:y + 12, x:x + 18] = 255
    with pytest.raises(ReadError):
        anchor(image, "applied", masked=True, threshold=0.95)
    assert applied_anchor(image) == expected
    assert regions(image, "tooltip:mainStat", (661, 397), {"main": "INT", "sub": "LUK"})[0].size
    image[y:y + 12, x:x + 80] = 255
    with pytest.raises(ReadError):
        applied_anchor(image)


def test_hexa_capture_returns_read_levels_without_starting_ocr(client, monkeypatch):
    from pathlib import Path

    import cv2

    import capture
    import ocr_worker
    from scouter import hexa_scan
    image = cv2.imread(str(Path(__file__).parent / "fixtures/demon_slayer_hexa.png"))
    # Capture returns a complete supported client frame, not a panel crop.
    image = cv2.copyMakeBorder(image, 0, 1080 - image.shape[0], 0, 1920 - image.shape[1], cv2.BORDER_CONSTANT)
    expected = hexa_scan.read_matrix(image)
    monkeypatch.setattr(capture, "frame", lambda window: image)
    monkeypatch.setattr(capture, "pointer", lambda window: (0, 0))
    monkeypatch.setattr("scouter.capture_ready.regions", lambda *args: [image])
    monkeypatch.setattr(hover_queue, "submit_task", lambda character, key, task: task())
    monkeypatch.setattr(ocr_worker, "read", lambda *args: pytest.fail("HEXA badges do not need OCR"))
    app.perform({"character": ID, "mode": "hexa", "watch": True, "background": True, "window": 1}, app.generation, "", 0)
    assert app.job["status"] == "captured"
    assert app.job["result"] == expected
    assert profiles.load(ID)["inputs"]["hexa.skillCore1"] == "9"
