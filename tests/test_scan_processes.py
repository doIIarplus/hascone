import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from test_app import ID, client, post

import ocr_worker
import scan_worker
from flaming.stats import ReadError

ROOT = Path(__file__).resolve().parents[1]
BLANK = np.zeros((768, 1366, 3), np.uint8)


def _eventually(condition, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def scanner(monkeypatch):
    monkeypatch.setattr(scan_worker, "_enabled", True)
    yield scan_worker
    with scan_worker._steps, scan_worker._state:
        scan_worker._close()


@pytest.fixture
def reader(monkeypatch):
    monkeypatch.setattr(ocr_worker, "_enabled", True)
    yield ocr_worker
    with ocr_worker._lock:
        ocr_worker._close()


# Runs in a fresh interpreter: this test process has long since loaded OpenCV.
APP_PROCESS = r'''
import base64, json, sys, time
sys.path[:0] = [ROOT, ROOT + "/src"]
import app
import ocr_worker
import scan_worker
from flaming import characters

ocr_worker.enable()
scan_worker.enable()
client = app.app.test_client()
base, headers = "http://127.0.0.1:5001", {"X-Hascone-Token": app.TOKEN}
ID = "a" * 32
characters.write({"id": ID, "name": "Example", "class": "Shadower", "equipment": {}})
for path in ["/api/characters", f"/api/characters/{ID}", f"/api/characters/{ID}/steps", "/api/summary",
             f"/api/characters/{ID}/gear-value", f"/api/characters/{ID}/enhancement-analysis",
             f"/api/scouter/characters/{ID}", "/api/potential-weights", "/api/windows", "/api/scan"]:
    response = client.get(path, base_url=base)
    assert response.status_code == 200, (path, response.get_data(as_text=True)[:300])
app._warm_gear_values()
idle = sorted(m for m in ("cv2", "windows_capture", "paddle", "paddleocr") if m in sys.modules)

# An uploaded Equipment screenshot goes through both processes and is saved with its icons.
image = base64.b64encode(open(ROOT + "/tests/fixtures/resolution_1366/grid.png", "rb").read()).decode()
response = client.post("/api/scan", json={"character": ID, "mode": "equipment", "image": image, "delay": 0},
                       base_url=base, headers=headers)
assert response.status_code == 200, response.json
end = time.monotonic() + 60
while app.job.get("active") and time.monotonic() < end:
    time.sleep(0.05)
assert app.job["status"] == "review", app.job
opened = scan_worker.running(), ocr_worker.running()
response = client.post("/api/scan/save", json={}, base_url=base, headers=headers)
assert response.status_code == 200, response.json
icon = (characters.PROFILE_DIR / ID / "hat.png").read_bytes()
client.post("/api/scan/cancel", json={"release": True}, base_url=base, headers=headers)
print(json.dumps({
    "idle": idle,
    "scanning": sorted(m for m in ("cv2", "windows_capture", "paddle", "paddleocr") if m in sys.modules),
    "opened": opened,
    "closed": [scan_worker.running(), ocr_worker.running()],
    "equipment": len(characters.load(ID)["equipment"]),
    "png": icon[:8] == b"\x89PNG\r\n\x1a\n",
}))
'''


def test_app_process_never_loads_capture_or_ocr_libraries(tmp_path):
    script = "ROOT = " + repr(ROOT.as_posix()) + "\n" + APP_PROCESS
    env = {**__import__("os").environ, "HASCONE_DATA_DIR": str(tmp_path)}
    run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=180, env=env)
    assert run.returncode == 0, run.stderr[-3000:]
    outcome = json.loads(run.stdout.strip().splitlines()[-1])
    assert outcome == {
        "idle": [], "scanning": [], "opened": [True, True], "closed": [False, False], "equipment": 25, "png": True,
    }


def test_scanner_rebuilds_errors_without_its_libraries(scanner):
    with pytest.raises(ReadError, match="Currently Equipped"):
        scanner.call("render", BLANK, "hover:hat", {"kind": "hover", "slot": "hat"})
    with pytest.raises(ValueError, match="Select a running MapleStory window"):
        scanner.call("acquire", {"window": 1, "mode": "overview"})
    png, icons = scanner.call("render", BLANK, "overview", {})
    assert png.startswith(b"\x89PNG") and icons == {}


def test_scanner_closes_after_idle(scanner, monkeypatch):
    monkeypatch.setattr(scanner, "IDLE_SECONDS", 0.2)
    scanner.call("render", BLANK, "overview", {})
    assert scanner.running()
    assert _eventually(lambda: not scanner.running())


def test_scanner_stays_open_through_a_scan_and_closes_when_released(scanner, monkeypatch):
    monkeypatch.setattr(scanner, "IDLE_SECONDS", 0.2)
    with scanner.session():
        scanner.call("render", BLANK, "overview", {})
        time.sleep(0.5)
        assert scanner.running()
        scanner.release()
        assert scanner.running()
    assert not scanner.running()
    scanner.call("render", BLANK, "overview", {})
    assert scanner.running()
    scanner.release()
    assert not scanner.running()


def test_stop_leaves_the_scanner_open(scanner, monkeypatch):
    monkeypatch.setattr(scanner, "IDLE_SECONDS", 60)
    scanner.stop()  # nothing to stop yet
    assert not scanner.running()
    with scanner.session():
        scanner.call("render", BLANK, "overview", {})
        scanner.stop()
        assert scanner.running()


def test_ocr_worker_closes_after_idle(reader, monkeypatch):
    monkeypatch.setattr(reader, "IDLE_SECONDS", 0.2)
    with pytest.raises(ReadError, match="Open Equipment"):
        reader.read(BLANK, "equipment")
    assert reader.running()
    assert _eventually(lambda: not reader.running())


def test_closing_the_guide_keeps_ocr_while_reads_are_queued(client, monkeypatch):
    import hover_queue

    closed = []
    monkeypatch.setattr(scan_worker, "release", lambda: closed.append("scanner"))
    monkeypatch.setattr(ocr_worker, "release", lambda: closed.append("ocr"))
    monkeypatch.setattr(hover_queue, "all_status", lambda: {ID: {"pending": ["hat"]}})
    post(client, "/api/scan/cancel", {"release": True})
    assert closed == ["scanner"]
    monkeypatch.setattr(hover_queue, "all_status", lambda: {ID: {"pending": []}})
    post(client, "/api/scan/cancel", {"release": True})
    assert closed == ["scanner", "scanner", "ocr"]
    post(client, "/api/scan/cancel")
    assert closed == ["scanner", "scanner", "ocr"]
