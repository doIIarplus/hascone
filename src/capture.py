"""Capture game window screenshots."""

import sys
import threading


def windows():
    if sys.platform != "win32":
        return []
    import win32gui

    result = []

    def visit(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if win32gui.IsWindowVisible(hwnd) and "MapleStory" in title:
            _, _, w, h = win32gui.GetClientRect(hwnd)
            if w > 1000 and h > 600:
                result.append({"id": hwnd, "title": title, "width": w, "height": h})

    win32gui.EnumWindows(visit, None)
    return result


_camera = None
_camera_hwnd = None
_camera_lock = threading.Lock()
_retired = []


def frame(hwnd):
    """Reuse one capture session; never tear down a native callback per frame."""
    global _camera, _camera_hwnd
    from utils.wgc_camera import WgcCamera

    hwnd = int(hwnd)
    if hwnd not in [w["id"] for w in windows()]:
        raise ValueError("Select a running MapleStory window and unminimize it.")
    with _camera_lock:
        if _camera is None or _camera_hwnd != hwnd:
            if _camera is not None:
                _camera.release()
                # Keep callback owners alive after asynchronous native stop.
                _retired.append(_camera)
            _camera = WgcCamera(window_hwnd=hwnd)
            _camera_hwnd = hwnd
        result = _camera.grab_fresh(timeout=3)
        from game_resolution import validate_frame

        validate_frame(result)
        return result.copy()


def pointer(hwnd):
    """Read the pointer in game-client coordinates."""
    import win32gui

    return win32gui.ScreenToClient(int(hwnd), win32gui.GetCursorPos())
