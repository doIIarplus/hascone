"""Background Scouter API and calculation jobs."""

import copy
import threading
import uuid

from scouter import client, profiles
from scouter.boss_cuts import with_boss_cuts

_lock = threading.RLock()
_job = {"active": False, "status": "idle", "message": ""}
_cancelled = threading.Event()


def state():
    with _lock:
        return copy.deepcopy(_job)


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
        if cached:
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
    global _cancelled, _job
    from scouter import simulator

    if not isinstance(request, dict) or set(request) != {"result_id", "changes"}:
        raise ValueError("Choose a saved calculation and enter stat changes")
    changes = simulator.validate(request["changes"])
    with _lock:
        if _job["active"]:
            raise ValueError("A Scouter calculation is already running")
        data = profiles.load(identifier)
        record = next((r for r in data["history"] if r["id"] == request["result_id"]), None)
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
            "message": "Simulating stat changes…",
        }
        threading.Thread(
            target=_run_simulation,
            args=(identifier, baseline, changes, payload, _cancelled),
            daemon=True,
            name="ScouterSimulator",
        ).start()
        return state()


def _run_simulation(identifier, baseline, changes, payload, cancelled):
    from scouter import simulator

    try:
        calculated = client.simulate(payload, cancelled)
        result = {
            "id": uuid.uuid4().hex,
            "created": profiles.now(),
            "changes": changes,
            "baseline_id": baseline["id"],
            "calculatedData": calculated,
            **simulator.comparison(baseline, calculated),
        }
        if cancelled.is_set():
            raise ValueError("Simulation cancelled")
        with profiles.lock:
            data = profiles.load(identifier)
            record = next((r for r in data["history"] if r["id"] == baseline["id"]), None)
            if record is None:
                raise ValueError("The original calculation is no longer available")
            record.setdefault("simulations", []).append(result)
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
