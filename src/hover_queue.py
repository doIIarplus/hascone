"""Background OCR for captured equipment and character panels.

Capturing a hover takes a fraction of a second; reading it takes much longer and
varies with the machine. Reads run here, one at a time, so the user can move to
the next item as soon as its tooltip is captured.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=1)
_lock = threading.Lock()
_state = {}
_working = {}


def _entry(character):
    return _state.setdefault(character, {"pending": [], "done": [], "failed": {}})


def reset(character):
    """Forget finished results; reads still in progress are kept."""
    with _lock:
        entry = _entry(character)
        entry["done"], entry["failed"] = [], {}


def status(character):
    with _lock:
        entry = _entry(character)
        return {"pending": list(entry["pending"]), "done": list(entry["done"]), "failed": dict(entry["failed"])}


def submit(character, slot, frame, save):
    """Queue FRAME for reading; SAVE(character, result, frame) stores a clean result."""
    with _lock:
        entry = _entry(character)
        if slot in entry["pending"]:
            raise ValueError("This item is already processing")
        entry["pending"].append(slot)
        entry["failed"].pop(slot, None)
        if slot in entry["done"]:
            entry["done"].remove(slot)
    _executor.submit(_read, character, slot, frame, save)


def submit_task(character, key, task):
    """Run a captured stat read independently of the live capture session."""
    with _lock:
        entry = _entry(character)
        if key in entry["pending"]:
            raise ValueError("This reading is already processing")
        entry["pending"].append(key)
        entry["failed"].pop(key, None)
        if key in entry["done"]:
            entry["done"].remove(key)
    _executor.submit(_run_task, character, key, task)


def _run_task(character, key, task):
    error = None
    with _lock:
        _working[character] = (key, time.monotonic())
    try:
        task()
    except Exception as exc:
        error = str(exc)
    with _lock:
        _working.pop(character, None)
        entry = _entry(character)
        entry["pending"].remove(key)
        if error:
            entry["failed"][key] = error
        else:
            entry["done"].append(key)


def all_status():
    with _lock:
        return {character: {"pending": list(entry["pending"]), "done": list(entry["done"]),
                            "failed": dict(entry["failed"]),
                            "active": _working.get(character, (None, 0))[0],
                            "elapsed": int(time.monotonic() - _working[character][1]) if character in _working else 0}
                for character, entry in _state.items()}


def _read(character, slot, frame, save):
    from ocr_worker import read

    error = None
    with _lock:
        _working[character] = (slot, time.monotonic())
    try:
        result = read(frame, "hover:" + slot)
        if result.get("errors"):
            error = result["errors"][0]
        else:
            result["slot_verified"] = True
            save(character, result, frame)
    except Exception as exc:  # reported to the guide per item
        error = str(exc)
    with _lock:
        _working.pop(character, None)
        entry = _entry(character)
        if slot in entry["pending"]:
            entry["pending"].remove(slot)
        if error:
            entry["failed"][slot] = error
        elif slot not in entry["done"]:
            entry["done"].append(slot)
