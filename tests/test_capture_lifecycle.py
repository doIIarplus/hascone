import threading
from unittest.mock import Mock

import numpy as np
import pytest
from test_app import client, post  # noqa: F401

import app
import capture
from utils import wgc_camera


@pytest.fixture
def cameras(monkeypatch):
    made = []

    def create(**kwargs):
        camera = Mock()
        camera.grab_fresh.return_value = np.zeros((1080, 1920, 3), np.uint8)
        made.append(camera)
        return camera

    monkeypatch.setattr(wgc_camera, "WgcCamera", create)
    monkeypatch.setattr(capture, "windows", lambda: [{"id": 1}])
    monkeypatch.setattr(capture, "_camera", None)
    monkeypatch.setattr(capture, "_camera_hwnd", None)
    monkeypatch.setattr(capture, "_session", None)
    monkeypatch.setattr(capture, "_retired", [])
    return made


@pytest.mark.parametrize("fails", [False, True])
def test_scan_closes_capture_on_success_and_error(monkeypatch, cameras, fails):
    def scan(*args):
        capture.frame(1)
        capture.frame(1)
        assert len(cameras) == 1
        if fails:
            raise ValueError("scan failed")

    monkeypatch.setattr(app, "_perform", scan)
    if fails:
        with pytest.raises(ValueError, match="scan failed"):
            app.perform({}, 0, "", 0)
    else:
        app.perform({}, 0, "", 0)
    assert capture._camera is None
    cameras[0].release.assert_called_once()
    with capture.session():
        capture.frame(1)
    assert len(cameras) == 2
    cameras[1].release.assert_called_once()


def test_cancel_stops_capture_before_worker_finishes_and_prevents_reopen(client, cameras):
    captured, resume = threading.Event(), threading.Event()
    outcome = []

    def scan():
        with capture.session():
            capture.frame(1)
            captured.set()
            assert resume.wait(5)
            try:
                capture.frame(1)
            except RuntimeError as exc:
                outcome.append(str(exc))

    worker = threading.Thread(target=scan)
    worker.start()
    try:
        assert captured.wait(5)
        assert post(client, "/api/scan/cancel").status_code == 200
        assert worker.is_alive()
        assert capture._camera is None
        cameras[0].release.assert_called_once()
    finally:
        resume.set()
        worker.join(5)
    assert outcome == ["Capture was cancelled"]
    assert len(cameras) == 1


def test_empty_or_cancelled_countdown_never_starts_camera(client, cameras):
    app.perform({"mode": "overview", "window": 1}, app.generation - 1, "", 0)
    assert cameras == []
