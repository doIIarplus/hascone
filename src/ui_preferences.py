"""Small persistent UI preferences shared across native backend ports."""
import json
import os
import tempfile
import threading
from pathlib import Path

PATH = Path("configs/ui_sections.json")
lock = threading.RLock()


def read():
    with lock:
        if not PATH.exists():
            return {}
        data = json.loads(PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}


def update(key, collapsed):
    if not isinstance(key, str) or not 1 <= len(key) <= 240 or type(collapsed) is not bool:
        raise ValueError("Invalid section preference")
    with lock:
        data = read()
        if collapsed:
            data[key] = True
        else:
            data.pop(key, None)
        PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=PATH.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream)
            os.replace(name, PATH)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return data
