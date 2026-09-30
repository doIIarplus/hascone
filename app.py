"""Hascone: MapleStory equipment scanning and Scouter."""

import base64
import copy
import io
import os
import secrets
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get("HASCONE_DATA_DIR", str(ROOT))).resolve()
DATA_ROOT.mkdir(parents=True, exist_ok=True)
os.chdir(DATA_ROOT)
SERVER_PORT = int(os.environ.get("HASCONE_PORT", "5001"))
sys.path.insert(0, str(ROOT / "src"))

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from flaming import characters
from scouter import profiles, service
from utils.payload_data import read_payload_json

app = Flask(__name__, static_folder="web", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
TOKEN = secrets.token_urlsafe(32)
scan_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scanner")
job_lock = threading.RLock()
job = {"active": False, "status": "idle"}
preview = None
generation = 0
_scan_identities = {}
LAYOUT = read_payload_json("src/flaming_data/equipment_layout.json")


@app.before_request
def local_only():
    if request.host not in (f"127.0.0.1:{SERVER_PORT}", f"localhost:{SERVER_PORT}"):
        return jsonify(error="Invalid local host"), 403
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-Hascone-Token") != TOKEN:
        return jsonify(error="Refresh the app to reconnect"), 403


@app.errorhandler(Exception)
def error(exc):
    if isinstance(exc, HTTPException):
        return jsonify(error=exc.description), exc.code
    if isinstance(exc, profiles.RevisionConflict):
        return jsonify(error=str(exc)), 409
    app.logger.info("%s: %s", type(exc).__name__, exc)
    return jsonify(error=str(exc)), 400


@app.get("/")
def index():
    return send_from_directory(ROOT / "web", "index.html")


@app.get("/api/session")
def session():
    return jsonify(token=TOKEN)


@app.get("/api/characters/<identifier>/scouter-preset")
def scouter_preset(identifier):
    from scouter.preset import export
    response=jsonify(export(identifier))
    response.headers['Cache-Control']='no-store'
    return response


@app.route("/api/ui/sections", methods=["GET", "POST"])
def section_preferences():
    import ui_preferences
    if request.method == "GET":
        return jsonify(ui_preferences.read())
    body=request.get_json() or {}
    return jsonify(ui_preferences.update(body.get("key"),body.get("collapsed")))


@app.get("/api/health")
def health():
    return jsonify(application="hascone", version="1.1.7")


@app.route("/api/characters", methods=["GET", "POST"])
def registry():
    if request.method == "POST":
        return jsonify(characters.add(request.json.get("name", "")))
    rows = characters.listing()
    return jsonify(profiles=rows, default_character=rows[0]["id"] if rows else None, layout=LAYOUT)


@app.post("/api/characters/order")
def character_order():
    with characters.lock:
        characters.save_order((request.get_json(silent=True) or {}).get("order"))
    return jsonify(order=[row["id"] for row in characters.listing()])


@app.get("/api/characters/<identifier>/portrait")
def portrait(identifier):
    path = characters.portrait_path(identifier)
    if not path.exists():
        return send_from_directory(ROOT / "web", "avatar.svg")
    return send_from_directory(path.parent.resolve(), path.name)


@app.delete("/api/characters/<identifier>")
def delete_character(identifier):
    import hover_queue

    with job_lock, service._lock, characters.lock, profiles.lock:
        characters.load(identifier)
        if job.get("active") or hover_queue.status(identifier)["pending"]:
            return jsonify(error="Wait for scanning and processing to finish before deleting this character."), 409
        calculation = service.state()
        if calculation.get("active") and calculation.get("profile") == identifier:
            return jsonify(error="Wait for this character's Scouter calculation to finish before deleting it."), 409
        folder = characters.PROFILE_DIR / identifier
        parent = characters.PROFILE_DIR.resolve()
        if folder.is_symlink() or folder.resolve() != parent / identifier:
            raise ValueError("Invalid character data folder")
        if folder.exists():
            shutil.rmtree(folder)
        (profiles.DIRECTORY / f"{identifier}.json").unlink(missing_ok=True)
        characters.portrait_path(identifier).unlink(missing_ok=True)
        (characters.PROFILE_DIR / f"{identifier}.json").unlink()
        characters.save_order([row["id"] for row in characters.listing()])
        hover_queue.reset(identifier)
    return jsonify(deleted=identifier)


@app.get("/api/characters/<identifier>/equipment/<slot>/icon")
def icon(identifier, slot):
    characters.load(identifier)
    if slot not in LAYOUT["slots"]:
        raise ValueError("Unknown equipment slot")
    folder = (characters.PROFILE_DIR / identifier).resolve()
    if not (folder / (slot + ".png")).is_file():
        response = send_from_directory(ROOT / "web", "item-placeholder.svg")
        response.headers["Cache-Control"] = "no-store"
        return response
    return send_from_directory(folder, slot + ".png", max_age=0)


@app.get("/api/characters/<identifier>")
def character(identifier):
    from cubing.item_database import item_metadata
    from cubing.scoring import current_score
    from flaming.character_score import scoring
    from flaming.score import flame_score
    from flaming.vision import Stat

    data = characters.load(identifier)
    score, data["flame_scoring"] = scoring(data)
    from cubing.character_score import scoring as potential_scoring
    cube_score, attack_score, data["potential_scoring"] = potential_scoring(data)
    for slot, item in data["equipment"].items():
        if "stats" in item:
            item["flame_score"] = round(
                float(flame_score([Stat(**s) for s in item["stats"]], score)), 1
            )
        if item.get("potential"):
            item["equivalent"] = current_score(
                slot,
                data["class"],
                item["potential"],
                score=cube_score, attack_score=attack_score,
                item_level=(item_metadata(slot, item) or {}).get("level"),
            )
    return jsonify(data)


@app.get("/api/characters/<identifier>/equipment/<slot>/flame-tiers")
def flame_tiers(identifier, slot):
    from flaming.breakdown import breakdown
    if slot not in LAYOUT["slots"]:
        raise ValueError("Unknown equipment slot")
    return jsonify(breakdown(characters.load(identifier)["equipment"].get(slot, {}), slot))


@app.post("/api/characters/<identifier>/equipment/<slot>/flame")
def edit_flame(identifier, slot):
    from flaming.vision import PERCENT_STATS, STAT_NAMES
    if slot not in LAYOUT["slots"]:
        raise ValueError("Unknown equipment slot")
    body = request.get_json() or {}
    values = body.get("values")
    if not isinstance(values, dict) or set(values) - set(STAT_NAMES.values()):
        raise ValueError("Choose valid flame stats")
    stats = []
    for name, value in values.items():
        if type(value) is not int or value < 0 or value > 999999:
            raise ValueError("Flame values must be nonnegative whole numbers")
        if name in PERCENT_STATS and value > 100:
            raise ValueError("Flame percentages cannot exceed 100")
        if value:
            stats.append({"name": name, "value": -value if name == "Reduced level requirement" else value, "percent": name in PERCENT_STATS})
    with characters.lock:
        data = characters.load(identifier)
        item = data["equipment"].get(slot)
        if not item or not item.get("name"):
            raise ValueError("Scan this item before editing its flame")
        if body.get("item") != item["name"] or body.get("updated") != item.get("updated"):
            raise ValueError("This item changed. Reopen the editor and try again.")
        if item.get("flameable", LAYOUT["slots"][slot].get("flameable", True)) is False:
            raise ValueError("This item cannot have flames")
        item.update(stats=stats, status="scanned", updated=profiles.now())
        characters.write(data)
    return character(identifier)


@app.post("/api/characters/<identifier>/equipment/<slot>/starforce-modes")
def item_starforce_modes(identifier, slot):
    """Fix this item's Star Force enhancement modes, or clear them to optimize per star."""
    from starforce.cost import item_modes

    modes = item_modes((request.get_json(silent=True) or {}).get("modes"))
    with characters.lock:
        data = characters.load(identifier)
        item = data["equipment"].get(slot)
        if slot not in LAYOUT["slots"] or not isinstance(item, dict):
            raise ValueError("Scan this item first")
        if modes:
            item["starforce_modes"] = modes
        else:
            item.pop("starforce_modes", None)
        characters.write(data)
    return character(identifier)


@app.post("/api/characters/<identifier>/scoring")
def character_scoring(identifier):
    from flaming.character_score import scoring
    from flaming.score import normalize_score

    body = request.get_json(silent=True) or {}
    source = body.get("source")
    if source not in ("default", "scouter", "custom"):
        return jsonify(error="Choose default, Scouter or custom weights"), 400
    with characters.lock:
        data = characters.load(identifier)
        _, info = scoring(data)
        if source == "scouter" and info["scouter_weights"] is None:
            return jsonify(error="Calculate Scouter for this character first."), 400
        if source == "custom":
            # Start from the weights in effect; unlisted stats keep the class defaults.
            weights = body.get("weights") or data.get("flame_custom_weights") or info["weights"]
            data["flame_custom_weights"] = normalize_score({"class": data["class"], "weights": weights})["weights"]
        data["flame_weight_source"] = source
        data.pop("flame_all_stat_source", None)
        characters.write(data)
    return character(identifier)


@app.post("/api/characters/<identifier>/potential-scoring")
def potential_scoring_source(identifier):
    from cubing.character_score import scoring
    source = (request.get_json(silent=True) or {}).get("source")
    if source not in ("default", "scouter"):
        return jsonify(error="Choose default or Scouter weights"), 400
    with characters.lock:
        data = characters.load(identifier)
        _, _, info = scoring(data)
        if source == "scouter" and info["scouter_weights"] is None:
            return jsonify(error=info["reason"]), 400
        data["potential_weight_source"] = source
        characters.write(data)
    return character(identifier)


@app.get("/api/characters/<identifier>/enhancement-analysis")
def enhancement_analysis(identifier):
    from enhancement_analysis import snapshot
    return jsonify(snapshot(characters.load(identifier)))


@app.route("/api/scouter/characters/<identifier>", methods=["GET", "POST"])
def scouter_profile(identifier):
    return jsonify(
        profiles.snapshot(identifier)
        if request.method == "GET"
        else profiles.save_inputs(identifier, request.json)
    )


@app.post("/api/scouter/characters/<identifier>/calculate")
def calculate(identifier):
    return jsonify(service.start(identifier))


@app.post("/api/scouter/characters/<identifier>/simulate")
def simulate(identifier):
    return jsonify(service.start_simulation(identifier, request.json))


@app.post("/api/scouter/characters/<identifier>/suggestions")
def suggestions(identifier):
    return jsonify(service.start_suggestions(identifier))


@app.post("/api/scouter/characters/<identifier>/starforce-options")
def starforce_options(identifier):
    return jsonify(profiles.save_starforce_options(identifier, request.json))


@app.get("/api/scouter/characters/<identifier>/history/<record>")
def history(identifier, record):
    from scouter.boss_cuts import with_boss_cuts

    return jsonify(with_boss_cuts(next(r for r in profiles.load(identifier)["history"] if r["id"] == record)))


@app.post("/api/scouter/characters/<identifier>/history/<record>/name")
def name_snapshot(identifier, record):
    name = (request.get_json() or {}).get("name")
    if not isinstance(name, str) or len(name.strip()) > 80:
        raise ValueError("Snapshot names must be text up to 80 characters")
    with profiles.lock:
        data = profiles.load(identifier)
        saved = next((row for row in data["history"] if row["id"] == record), None)
        if saved is None:
            raise ValueError("Snapshot not found")
        saved["name"] = name.strip()
        profiles.write(identifier, data)
    return jsonify(name=saved["name"])


@app.get("/api/scouter/icons/<name>")
def scouter_icon(name):
    return send_from_directory(ROOT / "src/scouter/data/icons", name)


@app.get("/api/scouter/state")
def calculation_state():
    return jsonify(service.state())


@app.post("/api/scouter/cancel")
def cancel_calculation():
    return jsonify(service.stop())


@app.get("/api/summary")
def summary():
    rows=[]
    for character in characters.listing():
        data=profiles.load(character["id"])
        digest=profiles.fingerprint(profiles.effective(data))
        latest=next(iter(reversed(data["history"])),None)
        current=next((r for r in reversed(data["history"]) if r.get("fingerprint")==digest),None)
        result=current or latest
        calculated=(result or {}).get("damage",{}).get("calculatedData",{})
        equipment=character.get("equipment",{})
        rows.append({"id":character["id"],"name":character["name"],"class":character["class"],"level":character.get("level"),
            "hexa":calculated.get("boss380_hexaStat"),"result_created":(result or {}).get("created"),"stale":bool(result and not current),
            "scanned":sum(bool(item.get("hover_scanned")) for item in equipment.values()),"equipped":len(equipment),
            "stars":sum(item.get("starforce",{}).get("stars",0) for item in equipment.values() if item.get("starforce",{}).get("status")=="scanned")})
    return jsonify(profiles=rows)


@app.post("/api/characters/<identifier>/progression")
def ensure_progression(identifier):
    return jsonify(service.ensure_suggestions(identifier))


@app.route("/api/potential-weights", methods=["GET", "POST"])
def potential_weights():
    from cubing import profiles as weights

    if request.method == "GET":
        return jsonify(weights.catalog())
    return jsonify(weights.save(request.json["settings"], request.json["revision"]))


@app.get("/api/windows")
def windows():
    import capture

    return jsonify(capture.windows())


def modes(identifier, *, recommended_only=True):
    info = profiles.load(identifier)["class_info"]
    result = [
        {
            "mode": "overview",
            "label": "Character stats",
            "instruction": "Open Character Info (L by default), expand Details, and keep the entire stats panel visible. Let temporary buffs settle.",
        }
    ]
    for role, stat in [("mainStat", info["main"]), ("subStat", info["sub"]), ("ssubStat", info.get("sub2"))]:
        if stat:
            result.append(
                {
                    "mode": "tooltip:" + role,
                    "label": stat + " breakdown",
                    "instruction": f"Hover anywhere on the {stat} row in Character Info. Keep the Base Value / % Value tooltip open until capture finishes.",
                }
            )
    result += [
        {
            "mode": "tooltip:atk",
            "label": "Attack breakdown",
            "instruction": "Hover anywhere on your "
            + ("Magic ATT" if info["main"] == "INT" else "Attack Power")
            + " row in Character Info. Keep its breakdown tooltip visible.",
        },
        {
            "mode": "weapon",
            "label": "Weapon attack",
            "instruction": "Open Equipment and hover your equipped weapon. Keep its full stat tooltip visible.",
        },
        {
            "mode": "links",
            "label": "Equipped link skills",
            "instruction": "Open Skills → Beginner → Link Manager. Show the equipped links at the top and move the cursor clear of their names and levels.",
        },
        {
            "mode": "hexa",
            "label": "HEXA levels",
            "instruction": "Open Skills → HEXA Matrix → HEXA Skills. Keep the full matrix visible; hover any unread nodes in the following steps.",
        },
    ]
    for key, core in info["cores"].items():
        if core.get("url") and key in profiles.HEXA_INPUTS:
            result.append(
                {
                    "mode": "hexa_hover:" + key,
                    "label": core.get("english_title") or key,
                    "instruction": "In HEXA Skills, hover "
                    + (core.get("english_title") or key)
                    + " and show its [Level] tooltip. Skip this if the matrix scan already read it.",
                }
            )
    result.append(
        {
            "mode": "hexa_hover:solJanus",
            "label": "Sol Janus",
            "instruction": "Hover Sol Janus in HEXA Skills so its [Level] tooltip is visible. Skip if already read.",
        }
    )
    if recommended_only and characters.load(identifier)["equipment"].get("weapon",{}).get("weapon_attack"):
        result = [step for step in result if step["mode"] != "weapon"]
    if info.get("shine"):
        result = [step for step in result if not step["mode"].startswith("hexa")]
        result += [{
            "mode": f"shine:{info['slug']}:{position}",
            "label": "Erda Link skills · " + position,
            "instruction": "Scroll the VI skill list all the way to the " + position
            + ". Open Skills → VI (Erda Link), move the cursor off the skill rows, and leave the full list visible. "
            + ("After capture, scroll to the bottom for the next step." if position == "top"
               else "If the whole list fits without scrolling, leave it as it is."),
        } for position in ("top", "bottom")]
    return result


@app.get("/api/characters/<identifier>/steps")
def steps(identifier):
    return jsonify(modes(identifier))


@app.get("/api/scan")
def scan_state():
    with job_lock:
        return jsonify(job)


@app.get("/api/scan/image")
def scan_image():
    from flask import send_file

    with job_lock:
        if preview is None:
            raise ValueError("No capture available")
        return send_file(io.BytesIO(preview["png"]), mimetype="image/png", max_age=0)


@app.get("/api/scan/queue/<identifier>")
def hover_queue_state(identifier):
    import hover_queue

    return jsonify(hover_queue.status(identifier))


@app.get("/api/scan/queues")
def scan_queues():
    import hover_queue
    return jsonify(hover_queue.all_status())


@app.post("/api/scan/queue/<identifier>/reset")
def hover_queue_reset(identifier):
    import hover_queue

    hover_queue.reset(identifier)
    return jsonify(hover_queue.status(identifier))


@app.post("/api/scan/cancel")
def cancel_scan():
    global generation, preview, job
    import capture

    with job_lock:
        generation += 1
        capture.stop()
        preview = None
        job = {"active": False, "status": "cancelled", "message": "Capture discarded."}
        return jsonify(job)


@app.post("/api/scan")
def start_scan():
    global generation, preview, job
    body = request.json
    identifier, mode = body["character"], body["mode"]
    characters.load(identifier)
    import hover_queue
    pending = hover_queue.status(identifier)["pending"]
    if (mode == "equipment" and pending) or mode in pending or body.get("slot") in pending:
        raise ValueError("This character's captured readings are still processing. Scan another character meanwhile.")
    # Background OCR may finish after the guide loads. A completed step is
    # still supported even when a newly generated guide would omit it.
    if mode not in ["equipment", "hover:any"] + ["hover:"+slot for slot in LAYOUT["slots"]] + [s["mode"] for s in modes(identifier, recommended_only=False)]:
        raise ValueError("Unknown scan step")
    if mode.startswith("shine:") and (not isinstance(body.get("session"), str) or not 1 <= len(body["session"]) <= 128):
        raise ValueError("Start a guided SHINE scan to capture the top and bottom together.")
    slot = body.get("slot")
    if mode == "hover:any":
        if not body.get("watch") or not body.get("slots") or set(body["slots"]) - set(LAYOUT["slots"]):
            raise ValueError("Choose the equipment slots to scan")
    elif mode.startswith("hover:") and slot not in LAYOUT["slots"]:
        raise ValueError("Choose an equipment slot")
    delay = 0 if body.get("watch") else float(body.get("delay", 5))
    if not 0 <= delay <= 15:
        raise ValueError("Countdown must be between 0 and 15 seconds")
    # Bind the preview to the selected profile and its current revision.
    stamp = profiles.fingerprint(
        characters.load(identifier)
        if (mode == "equipment" or mode.startswith("hover:"))
        else profiles.load(identifier)["inputs"]
    )
    with job_lock:
        characters.load(identifier)
        if job.get("active"):
            raise ValueError("A capture is already running")
        generation += 1
        token = generation
        preview = None
        job = {
            "active": True,
            "status": "watching" if body.get("watch") else "countdown",
            "message": "Watching for the requested panel..." if body.get("watch") else f"Capturing in {delay:g} seconds. Follow the prompt in game.",
        }
        scan_executor.submit(perform, copy.deepcopy(body), token, stamp, delay)
        return jsonify(job)


@dataclass
class WatchStep:
    previous: object
    partial_since: float | None
    current: object
    message: str
    stable: bool


def _watch_step(body, preview, previous, partial_since, started):
    """Decide whether the latest preview is a confirmed, stable match."""
    from watching import acceptable, signature

    if preview is None:
        message = "Watching: " + job.get("message", "Waiting for the requested panel.")
        return WatchStep(None, None, None, message, False)
    result = preview["result"]
    current = signature(result)
    partial = bool(result.get("values") and result.get("errors"))
    if partial and partial_since is None:
        partial_since = started
    elif not partial:
        partial_since = None
    settling = partial and started - partial_since < 10
    if not ((acceptable(result) or (partial and not settling)) and current != body.get("exclude")):
        message = ("Waiting for a clear reading; move the cursor off panel text. " + result["errors"][0]
                   if settling else "Waiting for the requested panel or a different item.")
        return WatchStep(None, partial_since, current, message, False)
    if previous == current:
        return WatchStep(previous, partial_since, current, "", True)
    return WatchStep(current, partial_since, current, "Recognized; checking a second frame?", False)


def _finish_stable_scan(body, result, current):
    global job
    from watching import scan_can_save

    if not scan_can_save(body, result):
        job["message"] = "Recognized. Confirm the slot or stat identity before saving."
        return
    try:
        with app.app_context():
            save_scan()
        job["signature"] = current
        job["result"] = result
    except Exception as exc:
        job = {"active": False, "status": "error", "message": str(exc)}


def _save_hover_capture(character, result, frame):
    from equipment_scan import save

    with characters.lock, profiles.lock:
        save(characters.load(character), result, frame)


def _hover_watch(body, token):
    """Capture a hovered item's tooltip the moment it appears; OCR runs in the background queue.

    "hover:any" accepts whichever of body["slots"] is hovered, in any order.
    """
    global job
    import capture
    import hover_queue
    from equipment_scan import hover_capture_ready, hover_target

    requested = body["mode"].split(":")[1]
    slots = body["slots"] if requested == "any" else [requested]
    while True:
        with job_lock:
            if token != generation:
                return
        try:
            # Check one frame cheaply; only a promising one gets a second frame.
            raw_pointer = capture.pointer(body["window"])
            first = _scan_frame(body)
            from game_resolution import scan_point
            pointer = scan_point(raw_pointer, body.get("_scan_scale", 1))
            slot, origin, bounds = hover_target(first, pointer, slots)
            second = _scan_frame(body)
            hover_capture_ready(first, second, slot, origin, bounds, _scan_pointer(body))
        except (ImportError, AttributeError, TypeError) as exc:
            with job_lock:
                if token == generation:
                    job = {"active": False, "status": "error", "fatal": True, "message": str(exc)}
            return
        except Exception as exc:
            with job_lock:
                if token != generation:
                    return
                job = {"active": True, "status": "watching", "message": str(exc)}
            # About 8 checks a second keeps the game smooth on slower machines.
            time.sleep(0.12)
            continue
        with job_lock:
            if token != generation:
                return
            hover_queue.submit(body["character"], slot, second, _save_hover_capture)
            job = {
                "active": False,
                "status": "captured",
                "slot": slot,
                "message": "Captured. Reading in the background; hover the next item.",
            }
        return


def _process_character_capture(body, image, baseline, result=None):
    mode = body["mode"]
    session_key = (body["character"], body.get("session"))
    if body.get("session"):
        if mode == "overview":
            # Following captures must not overwrite a character if its identity
            # check failed. The shared queue processes the overview first.
            _scan_identities[session_key] = False
        elif _scan_identities.get(session_key) is False:
            raise ValueError("Character stats could not be verified. Rescan Character Info before this step.")
    if result is None:
        from ocr_worker import read
        result = read(image, "tooltip" if mode.startswith("tooltip:") else mode)
    # Live panel/cursor checks happened before the frame entered the queue.
    result = _finalize_result(mode, {**body, "image": True}, image, None, result)
    if mode == "overview" and body.get("session"):
        # Identity validation succeeded even if a separate numeric field needs
        # a rescan. Do not misreport those failures as a different character.
        _scan_identities[session_key] = True
    if result.get("errors"):
        raise ValueError("; ".join(result["errors"]))
    if not result.get("values") and not result.get("links"):
        raise ValueError("No readings found. Scan this step again.")
    _save_character_result(body, result, baseline)


def _save_character_result(body, result, baseline=None):
    with profiles.lock:
        current = profiles.load(body["character"])
        if baseline is None:
            baseline = copy.deepcopy(current.get("manual_versions", {}))
        values, shine = result.get("values", {}), None
        if result.get("shine_page"):
            from scouter.shine_scan import prepare_save
            values, shine = prepare_save(current, result["shine_page"], body.get("session"), baseline)
        if any(current.get("manual_versions", {}).get(key) != baseline.get(key) for key in values):
            raise ValueError("These inputs changed during processing. Scan this step again.")
        profiles.save_scan(body["character"], values, result.get("errors", []), profiles.now(),
                           links=result.get("links"), shine=shine)


def _character_watch(body, token):
    global job
    import hover_queue
    from scouter.capture_ready import regions, stable

    while True:
        with job_lock:
            if token != generation:
                return
        try:
            profile = profiles.load(body["character"])
            first = _scan_frame(body)
            crops = regions(first, body["mode"], _scan_pointer(body), profile["class_info"])
            time.sleep(0.15)
            second = _scan_frame(body)
            stable(crops, regions(second, body["mode"], _scan_pointer(body), profile["class_info"]))
            result = None
            if body["mode"] == "hexa":
                from scouter.hexa_scan import read_matrix
                result = read_matrix(second)
            with job_lock:
                if token != generation:
                    return
                baseline = copy.deepcopy(profile.get("manual_versions", {}))
                hover_queue.submit_task(body["character"], body["mode"],
                                        lambda: _process_character_capture(body, second, baseline, result))
                job = {"active": False, "status": "captured", "message": "Captured. Processing in the background.", "result": result}
            return
        except Exception as exc:
            with job_lock:
                if token != generation:
                    return
                fatal = isinstance(exc, (ImportError, AttributeError, TypeError))
                job = {"active": not fatal, "status": "error" if fatal else "watching", "message": str(exc)}
            if fatal:
                return
            time.sleep(0.2)


def perform(body, token, stamp, delay):
    import capture

    with capture.session():
        _perform(body, token, stamp, delay)


def _perform(body, token, stamp, delay):
    global job, preview

    watching = bool(body.get("watch")) and not body.get("image")
    if watching and body["mode"].startswith("hover:"):
        _hover_watch(body, token)
        return
    if watching and body.get("background") and body["mode"] != "equipment":
        _character_watch(body, token)
        return
    previous = None
    partial_since = None
    while True:
        started = time.monotonic()
        with job_lock:
            if token != generation:
                return
        perform_once(body, token, stamp, delay)
        with job_lock:
            if token != generation:
                return
            if not watching or job.get("fatal"):
                return
            step = _watch_step(body, preview, previous, partial_since, started)
            previous, partial_since = step.previous, step.partial_since
            if step.stable:
                job.update(active=False, status="review", signature=step.current)
                _finish_stable_scan(body, preview["result"], step.current)
                return
            preview = None
            job = {"active": True, "status": "watching", "message": step.message}
        # One worker, no queued frames. Slow OCR delays the next capture.
        while time.monotonic() - started < 0.25:
            with job_lock:
                if token != generation:
                    return
            time.sleep(0.05)
        delay = 0


def _wait_out_delay(token, delay):
    """Sleep until the countdown ends. Returns True if this attempt went stale meanwhile."""
    end = time.monotonic() + delay
    while time.monotonic() < end:
        with job_lock:
            if token != generation:
                return True
        time.sleep(0.05)
    return False


def _scan_frame(body):
    import capture
    from game_resolution import normalize_scan

    image, scale = normalize_scan(capture.frame(body["window"]), body["mode"])
    body["_scan_scale"] = scale
    return image


def _scan_pointer(body):
    import capture
    from game_resolution import scan_point

    return scan_point(capture.pointer(body["window"]), body.get("_scan_scale", 1))


def _acquire_scan_image(body):
    """Capture or decode the source frame, verifying the expected hover slot stayed put."""
    if body.get("image"):
        from game_resolution import normalize_scan
        image = cv2.imdecode(
            np.frombuffer(base64.b64decode(body["image"], validate=True), dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        image, body["_scan_scale"] = normalize_scan(image, body["mode"])
        return image, None
    import capture

    mode = body["mode"]
    from game_resolution import scan_point
    raw_pointer = capture.pointer(body["window"]) if mode.startswith(("hover:", "tooltip:")) else None
    image = _scan_frame(body)
    before_pointer = scan_point(raw_pointer, body.get("_scan_scale", 1))
    if mode.startswith("hover:"):
        from equipment_scan import hovered_slot

        expected = mode.split(":")[1]
        if hovered_slot(image, before_pointer) != expected or hovered_slot(image, _scan_pointer(body)) != expected:
            raise ValueError("Hover your " + expected.replace("_", " ") + " in Equipment.")
    return image, before_pointer


def _verify_hover_settled(mode, body, image):
    from equipment_scan import hovered_slot

    expected = mode.split(":")[1]
    if hovered_slot(image, _scan_pointer(body)) != expected:
        raise ValueError("The cursor moved before the reading finished. Hold it over " + expected + ".")


def _verify_tooltip_hover(mode, body, image, before_pointer):
    from scouter.vision import verify_hover

    info = profiles.load(body["character"])["class_info"]
    key = mode.split(":")[1]
    stat = {"mainStat": info["main"], "subStat": info["sub"], "ssubStat": info.get("sub2"),
            "atk": "MATT" if info["main"] == "INT" else "ATT"}[key]
    verify_hover(image, before_pointer, stat)
    verify_hover(image, _scan_pointer(body), stat)


def _tooltip_values(mode, values):
    prefix = mode.split(":")[1]
    return {
        "stat." + prefix + suffix: values[source]
        for suffix, source in [
            ("Base", "base"),
            ("Percent" if prefix == "atk" else "Per", "percent"),
            ("Abs", "unaffected"),
        ]
        if source in values
    }


def _verify_weapon_hover(body, image):
    from equipment_scan import hovered_slot

    if hovered_slot(image, _scan_pointer(body)) != "weapon":
        raise ValueError("Hover your equipped weapon.")


def _weapon_values(body, values):
    attack = "MATT" if profiles.load(body["character"])["class_info"]["main"] == "INT" else "ATT"
    if attack not in values:
        raise ValueError("Weapon attack was not readable")
    return {"stat.weaponAtk": values[attack]}


def _hexa_values(body, values):
    info = profiles.load(body["character"])["class_info"]
    allowed = profiles.input_paths(info)
    return {k: v for k, v in values.items() if k in allowed}


def _finalize_result(mode, body, image, before_pointer, result):
    """Apply mode-specific hover verification and value reshaping to a raw read()."""
    live = not body.get("image")
    if mode.startswith("hover:") and live:
        _verify_hover_settled(mode, body, image)
        result["slot_verified"] = True
    if mode == "overview":
        from identity import verify_character

        verify_character(result, profiles.load(body["character"]))
    if mode.startswith("tooltip:") and live:
        _verify_tooltip_hover(mode, body, image, before_pointer)
        result["slot_verified"] = True
    if mode.startswith("tooltip:"):
        result["values"] = _tooltip_values(mode, result["values"])
    if mode == "weapon" and live:
        _verify_weapon_hover(body, image)
        result["slot_verified"] = True
    if mode == "weapon":
        result["values"] = _weapon_values(body, result["values"])
    if mode == "hexa" or mode.startswith(("hexa_hover:", "shine:")):
        result["values"] = _hexa_values(body, result["values"])
    return result


def perform_once(body, token, stamp, delay):
    global job, preview
    try:
        if _wait_out_delay(token, delay):
            return
        image, before_pointer = _acquire_scan_image(body)
        with job_lock:
            if token != generation:
                return
            job.update(
                status="reading",
                message="Reading cropped regions. First use loads the OCR model and takes longer.",
            )
        from ocr_worker import read

        mode = body["mode"]
        result = read(image, "tooltip" if mode.startswith("tooltip:") else mode)
        result = _finalize_result(mode, body, image, before_pointer, result)
        png = cv2.imencode(".png", image)[1].tobytes()
        with job_lock:
            if token != generation:
                return
            preview = {"body": body, "result": result, "stamp": stamp, "png": png}
            job.update(
                active=bool(body.get("watch")),
                status="reading" if body.get("watch") else "review",
                message="Review the captured item and readings before saving.",
                result=result,
            )
    except Exception as exc:
        with job_lock:
            if token == generation:
                fatal = isinstance(exc, (ImportError, AttributeError, TypeError))
                job = {"active": bool(body.get("watch")) and not fatal,
                       "status": "error" if fatal or not body.get("watch") else "watching",
                       "fatal": fatal, "message": str(exc)}


@app.post("/api/scan/save")
def save_scan():
    global preview, job
    with job_lock, characters.lock, profiles.lock:
        if preview is None or job["status"] != "review":
            raise ValueError("Capture and review a scan first")
        body, result = preview["body"], preview["result"]
        identifier, mode = body["character"], body["mode"]
        gear = mode == "equipment" or mode.startswith("hover:")
        current = characters.load(identifier) if gear else profiles.load(identifier)["inputs"]
        if profiles.fingerprint(current) != preview["stamp"]:
            raise ValueError("Profile changed after capture. Capture again before saving.")
        if gear:
            from equipment_scan import save

            frame = cv2.imdecode(np.frombuffer(preview["png"], np.uint8), cv2.IMREAD_COLOR)
            save(current, result, frame)
            message = "Equipment readings saved."
        else:
            _save_character_result(body, result)
            message = "Readings saved."
        preview = None
        job = {"active": False, "status": "saved", "message": message}
        return jsonify(job)


if __name__ == "__main__":
    import logging
    import urllib.request

    logging.basicConfig(level=logging.WARNING)
    if "--desktop" in sys.argv:
        from werkzeug.serving import make_server

        import ocr_worker

        # OCR runs in its own lower-priority process; capture stays responsive.
        ocr_worker.enable()

        server = make_server("127.0.0.1", SERVER_PORT, app, threaded=True)
        SERVER_PORT = server.server_port
        print(f"HASCONE_READY {SERVER_PORT}", flush=True)
        server.serve_forever()
        sys.exit(0)
    # Clicking the launcher again opens the existing application.
    try:
        with urllib.request.urlopen("http://127.0.0.1:5001/api/health", timeout=1) as response:
            running = b'"hascone"' in response.read()
    except OSError:
        running = False
    if running:
        if "--no-browser" not in sys.argv:
            import webbrowser

            webbrowser.open("http://127.0.0.1:5001")
        sys.exit(0)
    if "--no-browser" not in sys.argv:
        import webbrowser

        threading.Timer(1, lambda: webbrowser.open("http://127.0.0.1:5001")).start()
    app.run(host="127.0.0.1", port=5001, debug=False, threaded=True)
