"""Run OCR in a separate, lower-priority process.

Capturing and checking a hover must stay fast on every machine, so reading
(PaddleOCR plus tooltip parsing) never competes with it: the desktop app sends
screenshots to one worker process that runs below normal priority and works
through them at its own pace. Tests and scripts read in-process.
"""

import multiprocessing
import threading

_enabled = False
_lock = threading.Lock()
_process = None
_conn = None


def enable():
    global _enabled
    _enabled = True


def read(image, mode):
    """reader.read(IMAGE, MODE), in the worker process when enabled."""
    if not _enabled:
        from reader import read as read_here

        return read_here(image, mode)
    global _process, _conn
    with _lock:
        if _process is None or not _process.is_alive():
            parent, child = multiprocessing.get_context("spawn").Pipe()
            _process = multiprocessing.get_context("spawn").Process(target=_serve, args=(child,), daemon=True)
            _process.start()
            child.close()
            _conn = parent
        try:
            _conn.send((image, mode))
            ok, value = _conn.recv()
        except (EOFError, OSError, BrokenPipeError):
            _process = None
            raise RuntimeError("The OCR reader stopped unexpectedly. Try again.") from None
    if ok:
        return value
    kind, message = value
    if kind == "ReadError":
        from flaming.vision import ReadError

        raise ReadError(message)
    raise ValueError(message)


def _serve(conn):
    import sys

    if sys.platform == "win32":
        import win32api
        import win32process

        win32process.SetPriorityClass(win32api.GetCurrentProcess(), win32process.BELOW_NORMAL_PRIORITY_CLASS)
    from reader import read as read_here

    while True:
        try:
            image, mode = conn.recv()
        except (EOFError, OSError):
            return
        try:
            conn.send((True, read_here(image, mode)))
        except Exception as exc:
            conn.send((False, (type(exc).__name__, str(exc))))
