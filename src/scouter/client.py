"""Bounded client for the same public calculation API used by MapleScouter."""

import copy
import re
import threading
import time
from html.parser import HTMLParser
from urllib.parse import quote

import requests

SITE = "https://maplescouter.com"
API = "https://api.maplescouter.com"
_lock = threading.Lock()
_headers = None
_headers_at = 0
_previous = 0


def get_json(response):
    if response.status_code >= 400:
        raise ValueError(f"MapleScouter returned HTTP {response.status_code}. Please try again later.")
    try:
        value = response.json()
    except ValueError as exc:
        raise ValueError("MapleScouter returned an unreadable response") from exc
    if not isinstance(value, dict):
        raise ValueError("MapleScouter response format changed")
    return value


def public_headers(cancelled):
    global _headers, _headers_at
    if _headers and time.monotonic() - _headers_at < 3600:
        return _headers

    class Scripts(HTMLParser):
        def __init__(self):
            super().__init__()
            self.paths = []

        def handle_starttag(self, tag, attrs):
            src = dict(attrs).get("src", "")
            if tag == "script" and re.fullmatch(r"/_next/static/chunks/[A-Za-z0-9_./%\-]+\.js", src):
                self.paths.append(src)

    def download(url):
        if cancelled.is_set():
            raise ValueError("Calculation cancelled")
        response = requests.get(url, timeout=(10, 20), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError(f"Could not read MapleScouter client (HTTP {response.status_code})")
        return response.text

    scripts = Scripts()
    scripts.feed(download(SITE + "/en/input"))
    for path in sorted(set(scripts.paths), key=lambda p: ("/8153-" not in p, p))[:40]:
        content = download(SITE + path)
        match = re.search(r'"api-key"\s*:\s*"([^"\n]+)"', content)
        if match and API in content:
            _headers = {
                "Content-Type": "application/json",
                "Origin": SITE,
                "Referer": SITE + "/",
                "api-key": match[1],
            }
            _headers_at = time.monotonic()
            return _headers
    raise ValueError("MapleScouter client configuration changed; the integration needs an update")


def optimizer_body(user, result):
    user = copy.deepcopy(user)
    hexa = user["hexa"]
    hexa.update(
        character_class=user["stat"]["myClass"],
        hexaSkill={
            k: int(v) for k, v in hexa.items() if k.startswith(("skillCore", "masteryCore", "reinCore"))
        },
        hexaSkill_general={
            "generalCore1": 0,
            **{k: int(v) for k, v in hexa.items() if k.startswith("generalCore")},
        },
        hexaSkill_used={"sole_Erda": result["hexaUsed"][0], "sole_ErdaPrice": result["hexaUsed"][1]},
        hexaStat_opened=int(hexa.get("hexaStat", 0)) > 0,
    )
    return {
        "myHexa": hexa,
        "specEff": result["specEfficiency"],
        "sole": False,
        "merType": result.get("mercedesBuildType", 0),
        "start": True,
        "cycle": "3",
        "userStat": user,
        "id": "",
    }


def _post(endpoint, body, headers, cancelled):
    global _previous, _headers
    if cancelled.wait(max(0, 6 - (time.monotonic() - _previous))):
        raise ValueError("Calculation cancelled")
    _previous = time.monotonic()
    try:
        response = requests.post(
            API + endpoint, json=body, headers=headers, timeout=(10, 45), allow_redirects=False
        )
    except requests.RequestException as exc:
        raise ValueError("Could not reach MapleScouter. Your inputs are saved; try again later.") from exc
    if cancelled.is_set():
        raise ValueError("Calculation cancelled")
    if response.status_code in (401, 403):
        _headers = None
    return get_json(response)


def damage(user, cancelled):
    """One full-input calculation, without the unrelated HEXA order request."""
    with _lock:
        return _post("/api/calc/dmg", {"userStat": user}, public_headers(cancelled), cancelled)


def validate_score(result):
    if not isinstance(result, dict):
        raise ValueError("MapleScouter returned an unreadable calculation")
    score = result.get("boss380_hexaStat")
    if isinstance(score, (int, float)) and score < 0:
        messages = {
            -6: "MapleScouter requires 100% critical rate. Prepare your bossing preset and buffs, then rescan Character Info. Your scanned inputs are saved.",
            -2: "MapleScouter rejected the ignore-defense value. Review IED and the selected buffs.",
            -4: "MapleScouter rejected the inputs. Review the scanned stats and manual settings.",
            -5: "MapleScouter reports an impossible stat setup. Review the scanned stats and manual settings.",
        }
        raise ValueError(messages.get(score, f"MapleScouter rejected this setup (code {score}). Review the inputs."))
    if not all(k in result for k in ("boss380_hexaStat", "specEfficiency", "hexaUsed")):
        raise ValueError("MapleScouter did not return a supported HEXA score for these inputs")


def calculate(user, cancelled, progress):
    with _lock:
        headers = public_headers(cancelled)

        progress("Calculating HEXA score…")
        damage = _post("/api/calc/dmg", {"userStat": user}, headers, cancelled)
        result = damage.get("calculatedData")
        validate_score(result)
        progress("Calculating HEXA upgrade order…")
        # Preserve a successful score even if the second endpoint fails.
        try:
            order = _post(
                "/api/calc/hexa-order?class=" + quote(user["stat"]["myClass"]),
                optimizer_body(user, result),
                headers,
                cancelled,
            )
            if not isinstance(order.get("class_hexa"), list):
                raise ValueError("MapleScouter did not return an upgrade order")
            error = None
        except (ValueError, KeyError, TypeError) as exc:
            order, error = None, str(exc)
        if cancelled.is_set():
            raise ValueError("Calculation cancelled")
        return {"damage": damage, "order": order, "order_error": error}


def simulate(body, cancelled):
    with _lock:
        headers = public_headers(cancelled)
        return _post("/api/calc/dmg-simulator", body, headers, cancelled)
