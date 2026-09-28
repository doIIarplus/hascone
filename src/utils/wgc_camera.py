"""Windows.Graphics.Capture screenshots of the game window.

Frames are copied only when a screenshot is requested, so an idle session costs
nothing and a request is answered by the next native frame.
"""

import contextlib
import ctypes
import ctypes.wintypes as wintypes
import logging
import threading
import time

import numpy as np
import win32gui

logger = logging.getLogger(__name__)

# Native frame-rate hint (about 30 fps) where the platform supports it.
_MINIMUM_UPDATE_INTERVAL_MS = 33

# DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS). This — not GetWindowRect —
# is the rectangle a WGC window capture frame covers. On Win10+ GetWindowRect
# includes the invisible resize border, so deriving the client offset from it
# shifts every captured pixel and silently breaks template matching.
_DWMWA_EXTENDED_FRAME_BOUNDS = 9


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


def client_rect_in_window_frame(hwnd: int) -> tuple[int, int, int, int] | None:
    """Where the client area sits inside a WGC window-capture frame.

    Returns ``(x, y, width, height)`` in frame-local pixels, or None if the
    window is gone or the DWM query fails.

    A window-capture frame includes the title bar and borders, so it is larger
    than the client area the screenshot readers expect. Template coordinates and
    OCR regions are expressed in client-area pixels, so the crop has to be exact.

    Recomputed per capture rather than cached: it changes with DPI, theme and
    maximize state without the window handle changing.
    """
    try:
        bounds = _RECT()
        hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(_DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(bounds),
            ctypes.sizeof(bounds),
        )
        if hr != 0:
            return None
        client = win32gui.GetClientRect(hwnd)
        origin_x, origin_y = win32gui.ClientToScreen(hwnd, (0, 0))
    except Exception:
        return None

    width, height = client[2], client[3]
    if width <= 0 or height <= 0:
        return None
    return origin_x - bounds.left, origin_y - bounds.top, width, height


class WgcCamera:
    """Screenshots of one window's client area through Windows.Graphics.Capture.

    Frames arrive on a background thread. ``grab_fresh()`` asks for the next one,
    which the callback copies to BGR; other frames are dropped without copying.
    """

    def __init__(self, window_hwnd: int):
        self.window_hwnd = window_hwnd
        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._frame_id: int = 0
        self._wanted: bool = False
        self._control = None
        self._crop_warned: bool = False

        # ``cursor_capture`` and ``draw_border`` are cosmetic, and each one is
        # only settable on new enough Windows builds (the border toggle needs
        # Win11 22000, the cursor toggle Win10 2004). Passing None leaves the
        # property untouched, which every build supports, so an unsupported
        # cosmetic setting never prevents capture.
        cosmetic_options = (
            {"cursor_capture": False, "draw_border": False},
            {"cursor_capture": False, "draw_border": None},
            {"cursor_capture": None, "draw_border": None},
        )
        attempts = [
            dict(options, minimum_update_interval=interval)
            for options in cosmetic_options
            for interval in (_MINIMUM_UPDATE_INTERVAL_MS, None)
        ]
        last_error: Exception = RuntimeError("no capture attempt was made")
        for opts in attempts:
            try:
                self._start(**opts)
            except Exception as e:
                last_error = e
                self._teardown()
                continue
            if any(value is None for value in opts.values()):
                logger.warning(
                    f"WGC rejected optional capture settings ({last_error}) — started with "
                    f"cursor_capture={opts['cursor_capture']}, draw_border={opts['draw_border']}, "
                    f"minimum_update_interval={opts['minimum_update_interval']}."
                )
            return
        raise RuntimeError(f"WGC capture could not be started on window {self.window_hwnd}: {last_error}") from last_error

    def _start(self, cursor_capture: bool | None, draw_border: bool | None, minimum_update_interval: int | None) -> None:
        """Build a capture session with the given optional toggles and start it.

        The toggles are applied when the session starts, not at construction, so
        an unsupported one surfaces out of ``start_free_threaded()`` — both calls
        have to live inside the caller's try.
        """
        # Imported lazily so a machine without the package only fails when a
        # screenshot is requested, not at module import.
        from windows_capture import WindowsCapture

        # Binding by hwnd rather than window name: the game can show more than
        # one visible window titled "MapleStory".
        self._cap = WindowsCapture(
            cursor_capture=cursor_capture,
            draw_border=draw_border,
            minimum_update_interval=minimum_update_interval,
            window_hwnd=self.window_hwnd,
        )

        @self._cap.event
        def on_frame_arrived(frame, capture_control):  # noqa: ANN001 — windows-capture callback
            # Only pay for the full-frame BGRA -> BGR copy when a screenshot is pending.
            if not self._wanted:
                return
            # frame_buffer is (H, W, 4) BGRA, already de-strided by the lib. A
            # copy is mandatory: the native buffer is reused after this callback
            # returns. Drop alpha → BGR for OpenCV.
            buf = np.asarray(frame.frame_buffer)
            bgr = np.ascontiguousarray(buf[:, :, :3])
            with self._lock:
                self._latest = bgr
                self._frame_id += 1
                self._wanted = False

        @self._cap.event
        def on_closed():  # noqa: ANN202 — windows-capture callback
            pass

        self._control = self._cap.start_free_threaded()

    def _teardown(self) -> None:
        """Drop a half-built session so the next attempt starts clean."""
        with contextlib.suppress(Exception):
            if self._control is not None:
                self._control.stop()
        self._control = None
        self._cap = None

    def grab_fresh(self, timeout=1.0):
        """Wait for a new native frame instead of reusing an earlier screenshot."""
        with self._lock:
            previous = self._frame_id
            self._wanted = True
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                frame, frame_id = self._latest, self._frame_id
            if frame_id > previous:
                result = self._crop_to_client(frame)
                if result is not None:
                    return result.copy()
                # The window geometry did not fit; ask for another frame.
                with self._lock:
                    previous, self._wanted = frame_id, True
            time.sleep(0.005)
        raise RuntimeError("No fresh screenshot arrived before the capture timeout")

    def _crop_to_client(self, frame: np.ndarray) -> np.ndarray | None:
        """Trim a window-capture frame down to the window's client area.

        Returns None rather than a mis-offset frame when the geometry doesn't
        fit: a frame shifted by the title-bar height would corrupt every
        template match and fixed coordinate, silently.
        """
        geometry = client_rect_in_window_frame(self.window_hwnd)
        if geometry is None:
            return None
        x, y, width, height = geometry
        frame_h, frame_w = frame.shape[:2]
        if x < 0 or y < 0 or x + width > frame_w or y + height > frame_h:
            if not self._crop_warned:
                self._crop_warned = True
                logger.warning(
                    "WGC window frame %dx%d cannot contain client area %dx%d at (%d,%d) — "
                    "dropping frames until the geometry agrees.",
                    frame_w,
                    frame_h,
                    width,
                    height,
                    x,
                    y,
                )
            return None
        self._crop_warned = False
        return frame[y : y + height, x : x + width]

    def release(self) -> None:
        with contextlib.suppress(Exception):
            if self._control is not None:
                self._control.stop()
        self._control = None
