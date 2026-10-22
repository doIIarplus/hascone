"""Scoped requests using the app's human-verified browser session.

The visible browser loads public client files and hands its same-site session
to the in-memory HTTP transport before closing. No hidden browser stays open.
"""

import json
import os
import re
import secrets
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests

SITE = "https://maplescouter.com"
API = "https://api.maplescouter.com"
TIMEOUT = 300
TOKEN = secrets.token_urlsafe(32)
_condition = threading.Condition()
_pending = {}
_origin = None
_enabled = False
_last_seen = 0
_message = ""
_consumer = None
_native = os.environ.get("HASCONE_NATIVE_SCOUTER") == "1"
NETWORK_PAUSED = Path("configs/scouter_network_paused")


def ensure_network_allowed():
    if NETWORK_PAUSED.exists():
        raise ValueError("MapleScouter network access is paused while the reported Windows account lockout is investigated. Saved results and Export remain available.")


def configure(origin):
    global _origin, _enabled
    parsed = urlsplit(origin)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port or parsed.path:
        raise ValueError("Invalid local browser bridge address")
    _origin = origin
    _enabled = _native


def _launch():
    ensure_network_allowed()
    print("HASCONE_SCOUTER_CONNECT " + TOKEN, flush=True)


def authorized(token):
    return isinstance(token, str) and secrets.compare_digest(token, TOKEN)


def connect(consumer):
    global _consumer, _last_seen
    if not isinstance(consumer, str) or not re.fullmatch(r"[A-Za-z0-9-]{16,64}", consumer):
        raise ValueError("Invalid browser connection")
    with _condition:
        if consumer != _consumer:
            for job in _pending.values():
                if job["delivered"] and job["result"] is None:
                    job["result"] = {"error": "The browser connection changed. Retry the calculation."}
        _consumer = consumer
        _last_seen = time.monotonic()
        _condition.notify_all()


def connected(consumer):
    return bool(consumer) and consumer == _consumer


def disconnect():
    global _consumer, _last_seen
    with _condition:
        _consumer = None
        _last_seen = 0
        for job in _pending.values():
            if job["result"] is None:
                job["result"] = {"error": "Browser connection stopped. Retry to reconnect."}
        _condition.notify_all()


def status():
    with _condition:
        return _message


def enabled():
    return _enabled


def allowed(method, url):
    parsed = urlsplit(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if parsed.fragment or parsed.username or parsed.password or ".." in unquote(parsed.path).split("/"):
        return False
    if method in {"SESSION", "CONFIG"}:
        return url == SITE + "/en/input"
    if method == "GET" and origin == SITE and not parsed.query:
        return parsed.path == "/en/input" or bool(
            re.fullmatch(r"/_next/static/chunks/[A-Za-z0-9_./%()\-]+\.js", parsed.path)
        )
    return method == "POST" and origin == API and parsed.path in {
        "/api/calc/dmg", "/api/calc/hexa-order", "/api/calc/dmg-simulator",
    }


def poll(timeout=20, consumer=None):
    """Deliver each request once. Lost POST responses must not cause a replay."""
    global _last_seen
    with _condition:
        consumer = consumer or _consumer
        _last_seen = time.monotonic()
        deadline = _last_seen + timeout
        while True:
            if consumer != _consumer:
                raise ValueError("The browser connection changed. Reconnect from Hascone.")
            for job in _pending.values():
                if not job["delivered"]:
                    job["delivered"] = True
                    return job["request"]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            _condition.wait(remaining)


def progress(identifier, verifying=False, consumer=None):
    global _message, _last_seen
    with _condition:
        if consumer is not None and consumer != _consumer:
            return False
        _last_seen = time.monotonic()
        job = _pending.get(identifier)
        if job is None or job["result"] is not None:
            return False
        if verifying:
            job["verifying"] = True
        _message = (
            "Complete verification in the MapleScouter window. Hascone will continue automatically."
            if verifying else "Connecting to MapleScouter through your browser..."
        )
        return True


def complete(identifier, result, consumer=None):
    if not isinstance(result, dict):
        raise ValueError("Invalid browser response")
    if "error" in result:
        if not isinstance(result["error"], str) or len(result["error"]) > 1000:
            raise ValueError("Invalid browser error")
        value = {"error": result["error"]}
    else:
        code, body = result.get("status"), result.get("text")
        # MapleScouter also uses nonstandard three-digit statuses (e.g. 888 for
        # incomplete input). Preserve them for the calculation error handler.
        if type(code) is not int or not 100 <= code <= 999 or not isinstance(body, str) or len(body) > 16_000_000:
            raise ValueError("Invalid browser response")
        value = {"status": code, "text": body}
    with _condition:
        if consumer is not None and consumer != _consumer:
            return False
        job = _pending.get(identifier)
        if job is None or job["result"] is not None or not job["delivered"]:
            return False
        job["result"] = value
        _condition.notify_all()
        return True


def request(method, url, headers, cancelled, body=None, force_connect=False):
    ensure_network_allowed()
    if method in {"CONFIG", "SESSION"}:
        return _desktop_request(method, url, cancelled, body)
    if method != "POST":
        return _browser_request(method, url, headers, cancelled, body, force_connect)
    from scouter import session
    if not allowed(method, url):
        raise ValueError("Unsupported MapleScouter browser request")
    if _origin is None or not _native:
        raise ValueError("Open the Hascone Windows app to verify MapleScouter, or use Export to MapleScouter.")
    renew = False
    for attempt in range(2):
        if not session.available():
            finish_client(cancelled, renew=renew)
        response = session.post(url, headers, body, cancelled)
        if not session.requires_verification(response):
            return response
        session.clear()
        renew = True
    raise ValueError("MapleScouter still requires verification. Retry or export your inputs to MapleScouter.")


def finish_client(cancelled, renew=False):
    """Close the browser once public configuration and the session are ready."""
    request("SESSION", SITE + "/en/input", {}, cancelled, {"renew": renew})


def _desktop_request(method, url, cancelled, body):
    from scouter import desktop_browser
    global _message
    if not allowed(method, url):
        raise ValueError("Unsupported MapleScouter browser request")
    if _origin is None or not _native:
        raise ValueError("Open the Hascone Windows app to verify MapleScouter, or use Export to MapleScouter.")
    with _condition:
        _message = "Complete verification in the MapleScouter browser. Close it to cancel; Hascone will continue automatically."
    try:
        configuration = desktop_browser.capture(cancelled, renew=bool(body and body.get("renew")))
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(configuration if method == "CONFIG" else {"ok": True}).encode("utf-8")
        response.encoding = "utf-8"
        return response
    finally:
        with _condition:
            _message = ""


def _browser_request(method, url, headers, cancelled, body=None, force_connect=False):
    global _enabled, _message
    ensure_network_allowed()
    if not allowed(method, url):
        raise ValueError("Unsupported MapleScouter browser request")
    if _origin is None or not _native:
        raise ValueError("Open the Hascone Windows app to verify MapleScouter, or use Export to MapleScouter.")
    if cancelled.is_set():
        raise ValueError("Calculation cancelled")
    identifier = uuid.uuid4().hex
    safe_headers = {k: v for k, v in headers.items() if k.lower() in {"api-key", "content-type", "accept"}}
    job = {
        "request": {"id": identifier, "method": method, "url": url, "headers": safe_headers, "body": body},
        "delivered": False, "result": None, "verifying": False,
    }
    with _condition:
        _enabled = True
        _pending[identifier] = job
        open_browser = force_connect or time.monotonic() - _last_seen > 30
        _message = "Connecting in the MapleScouter window. Close it to cancel."
        _condition.notify_all()
    try:
        if open_browser:
            _launch()
        deadline = time.monotonic() + TIMEOUT
        with _condition:
            while job["result"] is None:
                if cancelled.is_set():
                    raise ValueError("Calculation cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("MapleScouter verification timed out. Retry or use Export to MapleScouter.")
                _condition.wait(min(remaining, 0.25))
            result = job["result"]
        if cancelled.is_set():
            raise ValueError("Calculation cancelled")
        if "error" in result:
            raise ValueError(result["error"])
        response = requests.Response()
        response.status_code = result["status"]
        response._content = result["text"].encode("utf-8")
        response.encoding = "utf-8"
        return response
    finally:
        with _condition:
            _pending.pop(identifier, None)
            _message = ""


def verify(cancelled):
    finish_client(cancelled, renew=True)
