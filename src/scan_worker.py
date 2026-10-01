"""Run capture and image checks in a scanner process that exists only while scanning.

The app process never loads OpenCV or Windows.Graphics.Capture. The first scan
step starts the scanner; it exits when the scan guide releases it, or once no
scan has used it for IDLE_SECONDS. Steps run on one connection in order, and
stop() uses a second so it can interrupt a step in progress. Tests and scripts
run the same steps in-process.
"""

import multiprocessing
import threading
from contextlib import contextmanager

# Long enough to keep the scanner between items in one guide, short enough
# that it closes soon after scanning stops.
IDLE_SECONDS = 30
# Every step finishes in a few seconds (a frame waits at most 3 s).
STEP_TIMEOUT = 30
# Stopping waits at most for the frame in progress; cancel holds the job lock meanwhile.
STOP_TIMEOUT = 5

_enabled = False
# Lock order: _steps, then _state, then _stopping.
_steps = threading.Lock()
_state = threading.RLock()
_stopping = threading.Lock()
_process = None
_conn = None
_control = None
_sessions = 0
_released = False
_idle = None


def enable():
    global _enabled
    _enabled = True


def running():
    with _state:
        return _process is not None and _process.is_alive()


def call(op, *args):
    """scan_steps.OP(*ARGS), in the scanner process when enabled."""
    if not _enabled:
        import scan_steps

        return getattr(scan_steps, op)(*args)
    return _request(op, args)


@contextmanager
def session():
    """Keep one capture session for a scan job (capture.session in the scanner)."""
    global _sessions
    if not _enabled:
        import capture

        with capture.session():
            yield
        return
    with _state:
        _sessions += 1
    try:
        _request("begin", ())
        yield
    finally:
        with _state:
            _sessions -= 1
        try:
            _request("end", (), start=False)
        except RuntimeError:
            pass


def stop():
    """Stop capture now, even during a step, and fail that scan's later frames (capture.stop)."""
    if not _enabled:
        import capture

        capture.stop()
        return
    with _state:
        if not running():
            return
        control = _control
    try:
        with _stopping:
            control.send(("stop", ()))
            if control.poll(STOP_TIMEOUT):
                control.recv()
    except (EOFError, OSError):
        pass


def release():
    """Close the scanner now; a scan still finishing closes it when its session ends."""
    global _released
    if not _enabled:
        return
    with _state:
        _released = True
    if _steps.acquire(blocking=False):
        try:
            with _state:
                if not _sessions:
                    _close()
        finally:
            _steps.release()


def _request(op, args, start=True):
    with _steps:
        with _state:
            _cancel_idle()
            if not running():
                if not start:
                    return None
                _open()
            conn = _conn
        try:
            conn.send((op, args))
            if not conn.poll(STEP_TIMEOUT):
                with _state:
                    _close()
                raise RuntimeError("The scanner stopped responding. Try again.")
            ok, value = conn.recv()
        except (EOFError, OSError):
            with _state:
                _close()
            raise RuntimeError("The scanner stopped unexpectedly. Try again.") from None
        finally:
            with _state:
                _after_request()
    if ok:
        return value
    raise _error(*value)


def _open():
    global _process, _conn, _control
    context = multiprocessing.get_context("spawn")
    steps, child_steps = context.Pipe()
    control, child_control = context.Pipe()
    _process = context.Process(target=_serve, args=(child_steps, child_control), daemon=True, name="hascone-scanner")
    _process.start()
    child_steps.close()
    child_control.close()
    _conn, _control = steps, control


def _close():
    """Disconnect; the scanner stops capture and exits when its connections close."""
    global _process, _conn, _control, _released
    _cancel_idle()
    _released = False
    if _process is None:
        return
    for conn in (_conn, _control):
        try:
            conn.close()
        except OSError:
            pass
    _process.join(timeout=3)
    if _process.is_alive():
        _process.terminate()
        _process.join(timeout=2)
    _process = _conn = _control = None


def _after_request():
    global _idle
    if _process is None or _sessions:
        return
    if _released:
        _close()
        return
    _idle = threading.Timer(IDLE_SECONDS, _close_if_idle)
    _idle.daemon = True
    _idle.start()


def _cancel_idle():
    global _idle
    if _idle is not None:
        _idle.cancel()
        _idle = None


def _close_if_idle():
    # A step in progress re-arms the timer when it finishes.
    if not _steps.acquire(blocking=False):
        return
    try:
        with _state:
            if not _sessions:
                _close()
    finally:
        _steps.release()


_ERRORS = ("ReadError", "ImportError", "AttributeError", "TypeError", "ValueError", "RuntimeError")


def _describe(exc):
    """Name EXC by a type the app process can rebuild without the scanner's libraries."""
    from flaming.stats import ReadError

    for kind in (ReadError, ImportError, AttributeError, TypeError, ValueError, RuntimeError):
        if isinstance(exc, kind):
            return kind.__name__, str(exc)
    return "RuntimeError", str(exc)


def _error(kind, message):
    from flaming.stats import ReadError

    types = {"ReadError": ReadError, "ImportError": ImportError, "AttributeError": AttributeError,
             "TypeError": TypeError, "ValueError": ValueError}
    return types.get(kind, RuntimeError)(message)


def _serve(steps, control):
    import capture
    import scan_steps

    threading.Thread(target=_serve_control, args=(control,), daemon=True).start()
    active = None
    try:
        while True:
            try:
                op, args = steps.recv()
            except (EOFError, OSError):
                return
            try:
                value = None
                if op == "begin":
                    if active is not None:
                        active.__exit__(None, None, None)
                    active = capture.session()
                    active.__enter__()
                elif op == "end":
                    if active is not None:
                        active, ending = None, active
                        ending.__exit__(None, None, None)
                else:
                    value = getattr(scan_steps, op)(*args)
                steps.send((True, value))
            except Exception as exc:
                steps.send((False, _describe(exc)))
    finally:
        capture.stop()


def _serve_control(control):
    import capture

    while True:
        try:
            control.recv()
        except (EOFError, OSError):
            return
        capture.stop()
        control.send((True, None))
