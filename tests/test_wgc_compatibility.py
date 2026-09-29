import sys
from types import SimpleNamespace

import numpy as np
import pytest

from utils import wgc_camera as wgc


@pytest.mark.parametrize("old_cosmetics", [False, True])
def test_unsupported_interval_falls_back_and_copies_only_requested_frames(monkeypatch, old_cosmetics):
    sessions = []

    class Capture:
        def __init__(self, **options):
            self.options = options
            self.callbacks = {}
            sessions.append(self)

        def event(self, callback):
            self.callbacks[callback.__name__] = callback
            return callback

        def start_free_threaded(self):
            if self.options["minimum_update_interval"] is not None:
                raise RuntimeError("Setting a minimum update interval is not supported by the Graphics Capture API on this platform")
            if old_cosmetics and any(self.options[k] is not None for k in ("cursor_capture", "draw_border")):
                raise RuntimeError("Capture toggle is not supported")
            return SimpleNamespace(stop=lambda: None)

    monkeypatch.setitem(sys.modules, "windows_capture", SimpleNamespace(WindowsCapture=Capture))
    camera = wgc.WgcCamera(window_hwnd=123)
    assert sessions[-1].options["minimum_update_interval"] is None
    assert sessions[-1].options["window_hwnd"] == 123
    assert len(sessions) == (6 if old_cosmetics else 2)
    if not old_cosmetics:
        assert sessions[-1].options["cursor_capture"] is False
        assert sessions[-1].options["draw_border"] is False
    callback = sessions[-1].callbacks["on_frame_arrived"]
    frame = SimpleNamespace(frame_buffer=np.zeros((3, 4, 4), dtype=np.uint8))
    for _ in range(3):
        callback(frame, None)
    assert camera._frame_id == 0 and camera._latest is None  # idle frames are not copied
    camera._wanted = True
    for _ in range(3):
        callback(frame, None)
    assert camera._frame_id == 1  # one request, one copy
    assert camera._latest.shape == (3, 4, 3)
    camera.release()
    assert camera._latest is None
    camera._wanted = True
    callback(frame, None)
    assert camera._latest is None  # late callbacks after stop cannot retain frames


def test_genuine_capture_failure_still_reaches_caller(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Window is unavailable")
    monkeypatch.setattr(wgc.WgcCamera, "_start", fail)
    with pytest.raises(RuntimeError, match="window 123: Window is unavailable"):
        wgc.WgcCamera(window_hwnd=123)


@pytest.mark.parametrize("offset", [(0, 0), (8, 31)])
def test_1440p_fullscreen_and_bordered_window_preserve_client_pixels(monkeypatch, offset):
    x, y = offset
    frame = np.zeros((1440 + y + 8, 2560 + x + 8, 3), dtype=np.uint8)
    frame[y + 1400, x + 2500] = [11, 22, 33]
    camera = object.__new__(wgc.WgcCamera)
    camera.window_hwnd = 123
    camera._crop_warned = False
    monkeypatch.setattr(wgc, "client_rect_in_window_frame", lambda hwnd: (x, y, 2560, 1440))
    client = camera._crop_to_client(frame)
    assert client.shape == (1440, 2560, 3)
    assert client[1400, 2500].tolist() == [11, 22, 33]


def test_switch_to_1440p_drops_old_size_frame(monkeypatch):
    camera = object.__new__(wgc.WgcCamera)
    camera.window_hwnd = 123
    camera._crop_warned = False
    monkeypatch.setattr(wgc, "client_rect_in_window_frame", lambda hwnd: (0, 0, 2560, 1440))
    assert camera._crop_to_client(np.zeros((1080, 1920, 3), dtype=np.uint8)) is None
    assert camera._crop_to_client(np.zeros((1440, 2560, 3), dtype=np.uint8)).shape == (1440, 2560, 3)
