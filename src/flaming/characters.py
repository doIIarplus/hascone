"""Independent character registry. Stores scanner profiles locally."""

import io
import json
import os
import re
import tempfile
import threading
import unicodedata
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

PROFILE_DIR = Path("configs/characters")
lock = threading.RLock()


def checked(identifier):
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise ValueError("Invalid character identifier")
    return identifier


def portrait_path(identifier):
    return PROFILE_DIR / (checked(identifier) + ".png")


def load(identifier):
    path = PROFILE_DIR / (checked(identifier) + ".json")
    if not path.exists():
        raise ValueError("Choose an existing character")
    data = json.loads(path.read_text(encoding="utf8"))
    # Unified hover scans predate the legacy flame status field.
    for item in data.get("equipment", {}).values():
        if item.get("hover_scanned") and "stats" in item and item.get("flameable") is not False:
            item.setdefault("status", "scanned")
    return data


def write(data):
    checked(data["id"])
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=PROFILE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, PROFILE_DIR / (data["id"] + ".json"))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


ORDER_PATH = Path("configs/character_order.json")


def _saved_order():
    try:
        order = json.loads(ORDER_PATH.read_text(encoding="utf8"))
        return [i for i in order if isinstance(i, str)] if isinstance(order, list) else []
    except (OSError, ValueError):
        return []


def listing():
    """Profiles in the user's saved order; new characters follow, oldest file name first."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    ids = [p.stem for p in sorted(PROFILE_DIR.glob("*.json"))]
    rank = {identifier: i for i, identifier in enumerate(_saved_order())}
    ids.sort(key=lambda identifier: rank.get(identifier, len(rank)))
    return [load(identifier) for identifier in ids]


def save_order(order):
    ids = {p.stem for p in PROFILE_DIR.glob("*.json")}
    if not isinstance(order, list) or len(set(order)) != len(order) or set(order) != ids:
        raise ValueError("The character order must list every saved character once.")
    ORDER_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=ORDER_PATH.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf8") as f:
            json.dump(order, f)
        os.replace(temporary, ORDER_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def add(name):
    from flaming.profiles import classes
    from scouter.profiles import class_info

    name = unicodedata.normalize("NFC", str(name).strip())
    if not 2 <= len(name) <= 16 or not name.isalnum():
        raise ValueError("Enter a MapleStory character name (2–16 letters or numbers)")
    row = _ranking(name)

    def key(v):
        return re.sub("[^a-z0-9]", "", v.casefold())

    api_job = row["jobName"]
    job_key = key(api_job)
    aliases = {
        "archmagefp": "FirePoison",
        "archmageil": "IceLightning",
        "archmagefirepoison": "FirePoison",
        "archmageicelightning": "IceLightning",
        "cannonmaster": "Cannoneer",
        "blademaster": "DualBlade",
    }
    info = class_info(aliases.get(job_key, api_job))
    job = next((c for c in classes() if key(c) == key(info["name"])), None)
    if job not in classes():
        raise ValueError("This class is not yet supported: " + row["jobName"])
    with lock:
        old = next((p for p in listing() if unicodedata.normalize("NFC", p["name"]).casefold() == name.casefold()), None)
        if old:
            return old
        data = {
            "id": uuid.uuid4().hex,
            "name": row["characterName"],
            "class": job,
            "level": row.get("level"),
            "equipment": {},
            "version": 1,
        }
        write(data)
    try:
        _save_portrait(row.get("characterImgURL", ""), data["id"])
    except (requests.RequestException, OSError, ValueError):
        pass  # The profile remains usable if the public avatar CDN is unavailable.
    return data


def _ranking(name):
    """The one public ranking row for this exact character name."""
    response = requests.get(
        "https://www.nexon.com/api/maplestory/no-auth/ranking/v2/na",
        params={"type": "overall", "id": "weekly", "character_name": name},
        timeout=(10, 20),
    )
    response.raise_for_status()
    rows = response.json().get("ranks", [])
    rows = [r for r in rows if unicodedata.normalize("NFC", r.get("characterName", "")).casefold() == name.casefold()]
    if len(rows) != 1:
        raise ValueError(
            "Nexon did not return one exact character. Check the spelling and ranking availability."
        )
    return rows[0]


def _save_portrait(url, identifier):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not re.fullmatch(r"msavatar\d+\.nexon\.net", parsed.hostname or ""):
        raise ValueError("Nexon did not provide a character image")
    image = requests.get(url, timeout=(10, 20), allow_redirects=False)
    image.raise_for_status()
    if len(image.content) > 5_000_000:
        raise ValueError("Portrait too large")
    Image.open(io.BytesIO(image.content)).convert("RGBA").save(portrait_path(identifier))


def refresh(identifier):
    """Fetch the character's current sprite and level from Nexon's public rankings."""
    name = load(identifier)["name"]
    try:
        row = _ranking(unicodedata.normalize("NFC", name))
        _save_portrait(row.get("characterImgURL", ""), identifier)
    except (requests.RequestException, OSError) as exc:
        raise ValueError("Could not get the character image from Nexon. Try again later.") from exc
    with lock:
        data = load(identifier)
        if isinstance(row.get("level"), int):
            data["level"] = row["level"]
        write(data)
    return data
