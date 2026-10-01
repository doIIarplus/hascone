"""Run OCR in a separate, lower-priority process that exists only while reading.

Capturing and checking a hover must stay fast on every machine, so reading
(PaddleOCR plus tooltip parsing) never competes with it: the desktop app sends
screenshots to one worker process that runs below normal priority and works
through them at its own pace. The worker starts on the first read and exits
once it has been idle for IDLE_SECONDS, or when the scan guide closes with no
reads left. Tests and scripts read in-process.
"""

import multiprocessing
import threading

# Reloading the model takes a few seconds, so stay open through short pauses.
IDLE_SECONDS = 60
# A read() mode that only loads the model.
WARM = "warm"

_enabled = False
_lock = threading.Lock()
_process = None
_conn = None
_idle = None


def enable():
    global _enabled
    _enabled = True


def running():
    process = _process
    return process is not None and process.is_alive()


def read(image, mode):
    """reader.read(IMAGE, MODE), in the worker process when enabled."""
    if not _enabled:
        from reader import read as read_here

        return read_here(image, mode)
    global _process, _conn
    with _lock:
        _cancel_idle()
        if not running():
            _close()
            parent, child = multiprocessing.get_context("spawn").Pipe()
            _process = multiprocessing.get_context("spawn").Process(target=_serve, args=(child,), daemon=True)
            _process.start()
            child.close()
            _conn = parent
        try:
            _conn.send((image, mode))
            if not _conn.poll(180):
                _close()
                raise RuntimeError("OCR timed out after 3 minutes. Scan this step again.")
            ok, value = _conn.recv()
        except (EOFError, OSError, BrokenPipeError):
            _close()
            raise RuntimeError("The OCR reader stopped unexpectedly. Try again.") from None
        finally:
            _schedule_idle()
    if ok:
        return value
    kind, message = value
    if kind == "ReadError":
        from flaming.stats import ReadError

        raise ReadError(message)
    raise ValueError(message)


def warm():
    """Start the worker and load the model in the background, before the first read needs it."""
    if _enabled and not running():
        threading.Thread(target=_warm, daemon=True, name="ocr-warm").start()


def _warm():
    try:
        read(None, WARM)
    except Exception:
        pass  # The first real read reports the same failure.


def release():
    """Close the worker now unless a read is in progress; that read's idle timer closes it."""
    if _lock.acquire(blocking=False):
        try:
            _close()
        finally:
            _lock.release()


def _close():
    """Disconnect; the worker exits when its connection closes."""
    global _process, _conn
    _cancel_idle()
    if _process is None:
        return
    try:
        _conn.close()
    except OSError:
        pass
    _process.join(timeout=2)
    if _process.is_alive():
        _process.terminate()
        _process.join(timeout=2)
    _process = _conn = None


def _schedule_idle():
    global _idle
    _cancel_idle()
    if _process is None:
        return
    _idle = threading.Timer(IDLE_SECONDS, release)
    _idle.daemon = True
    _idle.start()


def _cancel_idle():
    global _idle
    if _idle is not None:
        _idle.cancel()
        _idle = None


def _serve(conn):
    import sys

    if sys.platform == "win32":
        import win32api
        import win32process

        win32process.SetPriorityClass(win32api.GetCurrentProcess(), win32process.BELOW_NORMAL_PRIORITY_CLASS)
    from reader import read as read_here
    from reader import warm

    while True:
        try:
            image, mode = conn.recv()
        except (EOFError, OSError):
            return
        try:
            conn.send((True, warm() if mode == WARM else read_here(image, mode)))
        except Exception as exc:
            conn.send((False, (type(exc).__name__, str(exc))))
