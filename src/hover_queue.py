"""Background OCR for captured equipment hovers.

Capturing a hover takes a fraction of a second; reading it takes much longer and
varies with the machine. Reads run here, one at a time, so the user can move to
the next item as soon as its tooltip is captured.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=1)
_lock = threading.Lock()
_state = {}


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
        entry["pending"].append(slot)
        entry["failed"].pop(slot, None)
    _executor.submit(_read, character, slot, frame, save)


def _read(character, slot, frame, save):
    from ocr_worker import read

    error = None
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
        entry = _entry(character)
        if slot in entry["pending"]:
            entry["pending"].remove(slot)
        if error:
            entry["failed"][slot] = error
        elif slot not in entry["done"]:
            entry["done"].append(slot)
