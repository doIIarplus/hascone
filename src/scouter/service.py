"""Background Scouter API and calculation jobs."""

import copy
import threading
import uuid

from scouter import browser, client, profiles
from scouter.boss_cuts import with_boss_cuts

_lock = threading.RLock()
_job = {"active": False, "status": "idle", "message": ""}
_cancelled = threading.Event()


def state():
    with _lock:
        result = copy.deepcopy(_job)
        if result["active"] and browser.status():
            result["message"] = browser.status()
        return result


def connect():
    global _cancelled, _job
    with _lock:
        if _job["active"]:
            raise ValueError("Wait for the running Scouter job to finish, or stop it first.")
        _cancelled = threading.Event()
        _job = {"active": True, "status": "connecting", "kind": "connection",
                "message": "Opening the MapleScouter verification browser..."}
        threading.Thread(target=_connect, args=(_cancelled,), daemon=True, name="ScouterBrowser").start()
        return state()


def _connect(cancelled):
    try:
        browser.verify(cancelled)
        with _lock:
            _job.update(status="complete", message="MapleScouter is connected. You can calculate now.")
    except Exception as exc:
        with _lock:
            _job.update(status="stopped" if cancelled.is_set() else "error", message=str(exc))
    finally:
        with _lock:
            _job["active"] = False


def stop():
    _cancelled.set()
    return state()


def delete_result(identifier, record):
    """Remove a saved calculation, with its simulations; never while a job may read it."""
    with _lock:
        if _job["active"]:
            raise ValueError("Wait for the running Scouter job to finish before deleting a calculation.")
        with profiles.lock:
            data = profiles.load(identifier)
            kept = [row for row in data["history"] if row["id"] != record]
            if len(kept) == len(data["history"]):
                raise ValueError("Calculation not found")
            data["history"] = kept
            profiles.write(identifier, data)


def delete_swap_run(identifier, record, run):
    """Remove one saved item swap from a calculation; its other swaps and simulations stay."""
    with profiles.lock:
        data = profiles.load(identifier)
        baseline = next((row for row in data["history"] if row["id"] == record), None)
        runs = (baseline or {}).get("swap_runs", [])
        kept = [row for row in runs if row["id"] != run]
        if len(kept) == len(runs):
            raise ValueError("Saved item swap not found")
        baseline["swap_runs"] = kept
        profiles.write(identifier, data)


def start(identifier):
    global _cancelled, _job
    with _lock:
        if _job["active"]:
            raise ValueError("A Scouter calculation is already running")
        data = profiles.load(identifier)
        user = profiles.payload(data)
        digest = profiles.fingerprint(profiles.effective(data))
        cached = next(
            (r for r in reversed(data["history"]) if r["fingerprint"] == digest and r.get("order")), None
        )
        # Failed boss estimates must not trap Calculate in the same cached
        # response. First attempt local recovery with the current client port;
        # fetch a fresh result only when that saved data still cannot be used.
        if cached and with_boss_cuts(cached)["boss_cuts"].get("available") is not False:
            _job = {
                "active": False,
                "status": "complete",
                "profile": identifier,
                "message": "Loaded the saved result for these inputs.",
                "result_id": cached["id"],
            }
            return state()
        _cancelled = threading.Event()
        _job = {
            "active": True,
            "status": "calculating",
            "profile": identifier,
            "message": "Connecting to MapleScouter…",
        }
        threading.Thread(
            target=_run, args=(identifier, user, digest, _cancelled), daemon=True, name="ScouterAPI"
        ).start()
        return state()


def _run(identifier, user, digest, cancelled):
    def progress(message):
        with _lock:
            _job["message"] = message

    try:
        response = client.calculate(user, cancelled, progress)
        with profiles.lock:
            data = profiles.load(identifier)
            record = {
                "id": uuid.uuid4().hex,
                "created": profiles.now(),
                "fingerprint": digest,
                "input": user,
                **response,
            }
            record = with_boss_cuts(record)
            data["history"].append(record)
            profiles.write(identifier, data)
        with _lock:
            _job.update(status="complete", message="Calculation saved.", result_id=record["id"])
    except Exception as exc:
        with _lock:
            _job.update(status="stopped" if cancelled.is_set() else "error", message=str(exc))
    finally:
        with _lock:
            _job["active"] = False


def start_simulation(identifier, request):
    from scouter import simulator

    if not isinstance(request, dict) or set(request) != {"result_id", "changes"}:
        raise ValueError("Choose a saved calculation and enter stat changes")
    changes = simulator.validate(request["changes"])
    return _start_simulation(identifier, request["result_id"], changes, "simulations", {},
                             "Simulating stat changes…")


def start_swap_simulation(identifier, request):
    """One MapleScouter call for all enabled slot swaps and custom stat groups, saved as a swap run."""
    from itemswap import swap

    if not isinstance(request, dict) or set(request) != {"result_id", "config"}:
        raise ValueError("Choose a saved calculation and set up the item swap")
    config = copy.deepcopy(request["config"])
    computed = swap.compute(profiles.load(identifier)["class_info"], config)
    if computed["blockers"]:
        raise ValueError(computed["blockers"][0])
    extra = {
        "config": config,
        "enabled_slots": swap.enabled_slots(config),
        "breakdown": {"slots": {k: v["delta"] for k, v in computed["slots"].items() if v["enabled"]},
                      "groups": [g for g in computed["groups"] if g["enabled"]]},
    }
    return _start_simulation(identifier, request["result_id"], computed["changes"], "swap_runs", extra,
                             "Simulating item swap…")


def _start_simulation(identifier, result_id, changes, bucket, extra, message):
    global _cancelled, _job
    from scouter import simulator

    with _lock:
        if _job["active"]:
            raise ValueError("A Scouter calculation is already running")
        data = profiles.load(identifier)
        record = next((r for r in data["history"] if r["id"] == result_id), None)
        if record is None or "input" not in record:
            raise ValueError("Choose an existing saved calculation")
        baseline = {k: copy.deepcopy(record[k]) for k in ("id", "input", "damage")}
        payload = simulator.body(baseline["input"], changes)
        _cancelled = threading.Event()
        _job = {
            "active": True,
            "status": "calculating",
            "kind": "simulation",
            "profile": identifier,
            "result_id": record["id"],
            "message": message,
        }
        threading.Thread(
            target=_run_simulation,
            args=(identifier, baseline, changes, payload, _cancelled, bucket, extra),
            daemon=True,
            name="ScouterSimulator",
        ).start()
        return state()


def _run_simulation(identifier, baseline, changes, payload, cancelled, bucket="simulations", extra=None):
    from scouter import simulator

    try:
        calculated = client.simulate(payload, cancelled)
        result = {
            "id": uuid.uuid4().hex,
            "created": profiles.now(),
            "changes": changes,
            "baseline_id": baseline["id"],
            "calculatedData": calculated,
            **(extra or {}),
            **simulator.comparison(baseline, calculated),
        }
        if cancelled.is_set():
            raise ValueError("Simulation cancelled")
        with profiles.lock:
            data = profiles.load(identifier)
            record = next((r for r in data["history"] if r["id"] == baseline["id"]), None)
            if record is None:
                raise ValueError("The original calculation is no longer available")
            record.setdefault(bucket, []).append(result)
            profiles.write(identifier, data)
        with _lock:
            _job.update(status="complete", message="Simulation saved.", simulation_id=result["id"])
    except Exception as exc:
        with _lock:
            _job.update(status="stopped" if cancelled.is_set() else "error", message=str(exc))
    finally:
        with _lock:
            _job["active"] = False


def start_suggestions(identifier):
    global _cancelled, _job
    from scouter import suggestions

    with _lock:
        if _job["active"]:
            raise ValueError("A Scouter calculation is already running")
        data = profiles.load(identifier)
        digest = profiles.fingerprint(profiles.effective(data))
        if not any(r.get("fingerprint") == digest for r in data["history"]):
            raise ValueError("Calculate Scouter with your current inputs before generating suggestions.")
        gear = suggestions.equipment(identifier)
        _cancelled = threading.Event()
        _job = {
            "active": True,
            "status": "calculating",
            "kind": "suggestions",
            "profile": identifier,
            "message": "Comparing flame, potential and Star Force upgrades…",
        }
        threading.Thread(
            target=_run_suggestions,
            args=(identifier, data, gear, _cancelled),
            daemon=True,
            name="ScouterSuggestions",
        ).start()
        return state()


def _run_suggestions(identifier, data, gear, cancelled):
    from scouter import suggestions

    def checkpoint():
        if cancelled.is_set():
            raise InterruptedError("Suggestions cancelled.")

    def progress(message):
        with _lock:
            _job["message"] = message

    try:
        result = suggestions.build(
            data, gear, checkpoint, progress, lambda user: client.damage(user, cancelled)
        )
        checkpoint()
        with profiles.lock:
            current = profiles.load(identifier)
            current["suggestions"] = result
            profiles.write(identifier, current)
        with _lock:
            _job.update(
                status="complete", message=f"Ranked {len(result['rows'])} upgrade options by FD per meso."
            )
    except Exception as exc:
        with _lock:
            _job.update(status="stopped" if cancelled.is_set() else "error", message=str(exc))
    finally:
        with _lock:
            _job["active"] = False


_suggestion_attempts = {}

def ensure_suggestions(identifier):
    """Start one comparison per saved baseline/gear/options revision, without repeat error loops."""
    from scouter import suggestions
    from starforce.cost import options
    with _lock:
        data = profiles.load(identifier)
        digest = profiles.fingerprint(profiles.effective(data))
        if not any(r.get("fingerprint") == digest for r in data["history"]):
            return {"active":False,"status":"needs_calculation","message":"Scan and calculate Scouter with your current inputs to unlock upgrade recommendations."}
        gear = suggestions.equipment(identifier)
        if not any(item.get("name") for item in gear.get("equipment",{}).values()):
            return {"active":False,"status":"needs_equipment","message":"Scan equipped gear to unlock upgrade recommendations."}
        sf = options(data.get("starforce_options"))
        key = profiles.fingerprint([digest,suggestions.signature(gear),sf,5])
        saved = data.get("suggestions") or {}
        if (saved.get("fingerprint")==digest and saved.get("gear_fingerprint")==suggestions.signature(gear)
            and saved.get("starforce_options")==sf and saved.get("model_version")==5):
            return {"active":False,"status":"complete","message":"Upgrade recommendations are up to date."}
        if _job["active"]:
            return {**state(),"status":"busy"}
        if _suggestion_attempts.get(identifier)==key:
            return {"active":False,"status":"needs_retry","message":_job.get("message") if _job.get("profile")==identifier else "Comparison was interrupted. Retry Compare upgrades."}
        _suggestion_attempts[identifier]=key
        return start_suggestions(identifier)
