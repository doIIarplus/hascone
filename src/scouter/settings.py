"""Small persistent MapleScouter connection settings."""
import json
import os
import tempfile
import threading
from pathlib import Path

PATH = Path("configs/scouter_settings.json")
MAX_COOKIE = 8192
_lock = threading.RLock()


def read():
    with _lock:
        if not PATH.exists():
            return {"cookie": ""}
        try:
            data = json.loads(PATH.read_text(encoding="utf8"))
        except (OSError, ValueError):
            return {"cookie": ""}
        cookie = data.get("cookie", "") if isinstance(data, dict) else ""
        return {"cookie": cookie if isinstance(cookie, str) else ""}


def save(cookie):
    """Store the browser cookie sent with MapleScouter API requests.

    Optional: only needed when Cloudflare starts blocking requests that carry
    just the public api-key. An empty value disables the header.
    """
    if not isinstance(cookie, str) or len(cookie) > MAX_COOKIE:
        raise ValueError("The cookie must be text up to 8192 characters")
    cookie = cookie.strip()
    with _lock:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=PATH.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf8") as stream:
                json.dump({"cookie": cookie}, stream)
            os.replace(name, PATH)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    return {"cookie": cookie}
