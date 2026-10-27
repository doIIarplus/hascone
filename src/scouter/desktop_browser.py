"""Human verification in an installed browser, using only Hascone's own profile.

The site handles its challenge normally. After verification, the local browser
protocol reads the site's session and already-loaded public configuration. No
scripts are injected, and the browser closes before any calculation is sent.
"""

import asyncio
import base64
import contextlib
import ctypes
import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from curl_cffi import requests
from curl_cffi.const import CurlOpt
from curl_cffi.requests.websockets import WebSocketError, WebSocketTimeout

from scouter import session

SITE = "https://maplescouter.com"
PAGE = SITE + "/en/input"
# MapleScouter redirects the legacy input page to its manual-input route.
INPUT_PAGES = frozenset({PAGE, SITE + "/en/manual/input"})
TIMEOUT = 280
_lock = threading.Lock()
_configuration = None


def executable():
    """Prefer the default browser when it supports the Chromium protocol."""
    candidates = []
    if os.name == "nt":
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        # ASSOCF_IS_PROTOCOL, ASSOCSTR_EXECUTABLE. Never parse a shell command.
        if ctypes.windll.shlwapi.AssocQueryStringW(0x1000, 2, "https", "open", buffer, ctypes.byref(size)) == 0:
            candidates.append(Path(buffer.value))
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            candidates.extend(Path(root) / tail for tail in (
                "Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe",
            ))
    for candidate in candidates:
        if candidate.name.lower() in {"chrome.exe", "msedge.exe"} and candidate.is_file():
            return candidate
    raise ValueError("Install Chrome or Microsoft Edge to verify MapleScouter, or use Export to MapleScouter.")


def arguments(browser, profile, port):
    return [
        str(browser), f"--user-data-dir={profile}", f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        # Chromium's blank-password probe caused local Windows account lockouts.
        # Keep this on EVERY browser launch, including Edge and warm profiles.
        "--disable-features=AutofillAiWalletPrivatePasses",
        "--no-first-run", "--no-default-browser-check", "--disable-background-mode",
        "--mute-audio", "--new-window", PAGE,
    ]


def _check(cancelled, process=None, deadline=None):
    if cancelled.is_set():
        raise ValueError("Calculation cancelled")
    if process is not None and process.poll() is not None:
        raise ValueError("The MapleScouter browser was closed. Retry to verify again.")
    if deadline is not None and time.monotonic() >= deadline:
        raise ValueError("MapleScouter verification timed out. Retry or use Export to MapleScouter.")


def _stop(process):
    """Only stop the process tree we launched with the dedicated app profile."""
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=5, check=False)
        else:
            process.kill()
        process.wait(timeout=5)


def capture(cancelled, renew=False):
    """Return public configuration; install the session only after closing."""
    from scouter.browser import ensure_network_allowed
    global _configuration
    ensure_network_allowed()
    _check(cancelled)
    while not _lock.acquire(timeout=0.1):
        _check(cancelled)
    try:
        if not renew and _configuration and session.available():
            return _configuration
        browser = executable()
        profile = (Path("cache") / ("scouter-browser-" + browser.stem.lower())).resolve()
        profile.mkdir(parents=True, exist_ok=True)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        _check(cancelled)
        process = subprocess.Popen(arguments(browser, profile, port),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                configuration, credentials = runner.run(_capture(process, port, cancelled, renew))
        finally:
            _stop(process)
        _check(cancelled)
        session.install(credentials)
        _configuration = configuration
        return configuration
    except (OSError, requests.RequestsError, WebSocketError, TimeoutError) as exc:
        # Browser protocol errors can include storage data; never surface them.
        raise ValueError("Could not connect to the MapleScouter browser. Retry or use Export to MapleScouter.") from exc
    finally:
        _lock.release()


class ProtocolError(Exception):
    pass


class Protocol:
    def __init__(self, ws, process, cancelled, deadline):
        self.ws, self.process, self.cancelled, self.deadline = ws, process, cancelled, deadline
        self.identifier = 0

    async def call(self, method, params=None, target=None):
        _check(self.cancelled, self.process, self.deadline)
        self.identifier += 1
        message = {"id": self.identifier, "method": method, "params": params or {}}
        if target:
            message["sessionId"] = target
        await asyncio.wait_for(self.ws.send_json(message), timeout=5)
        deadline = min(self.deadline, time.monotonic() + 8)
        while True:
            _check(self.cancelled, self.process, deadline)
            try:
                response = await self.ws.recv_json(timeout=0.25)
            except WebSocketTimeout:
                continue
            if response.get("id") == self.identifier:
                if "error" in response:
                    raise ProtocolError("The browser could not read the MapleScouter page.")
                return response.get("result", {})

    async def close(self):
        # Closing must work after cancellation, timeouts, and normal completion.
        self.identifier += 1
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.ws.send_json({"id": self.identifier, "method": "Browser.close"}), 1)


def _endpoint(value, port):
    parsed = urlsplit(value)
    if (parsed.scheme != "ws" or parsed.hostname != "127.0.0.1" or parsed.port != port
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not re.fullmatch(r"/devtools/browser/[A-Za-z0-9-]+", parsed.path)):
        raise ValueError("Invalid local verification browser address")
    return value


def _cookies(values):
    return [c for c in values if c.get("domain", "").lstrip(".") in {
        "maplescouter.com", "api.maplescouter.com",
    }]


def _verified(cookies):
    return any(c.get("name") == "sc_tok" and c.get("value")
               and c.get("expires", 0) > time.time() + 60 for c in cookies)


def _input_page(url):
    # Anchors and query parameters don't change the page's trusted origin/path.
    return urlsplit(url)._replace(query="", fragment="").geturl() in INPUT_PAGES


async def _configuration_from_page(protocol, target):
    from scouter.browser import allowed
    tree = (await protocol.call("Page.getResourceTree", target=target))["frameTree"]
    if not _input_page(tree.get("frame", {}).get("url", "")):
        return None
    resources = {r["url"] for r in tree.get("resources", []) if allowed("GET", r["url"])
                 and urlsplit(r["url"]).path.endswith(".js")}
    for url in sorted(resources, key=lambda u: ("/8153-" not in u, u))[:40]:
        try:
            resource = await protocol.call("Page.getResourceContent", {
                "frameId": tree["frame"]["id"], "url": url,
            }, target)
        except ProtocolError:
            continue  # A script can appear before its response finishes loading.
        content = resource.get("content", "")
        if resource.get("base64Encoded"):
            content = base64.b64decode(content, validate=True).decode("utf-8")
        match = re.search(r'"api-key"\s*:\s*"([^"\n]+)"', content)
        if match and "https://api.maplescouter.com" in content:
            key = match[1]
            if len(key) <= 1000 and "\r" not in key:
                return {"api_key": key}
    return None


async def _read_session(protocol, renew):
    version = await protocol.call("Browser.getVersion")
    target = None
    configuration = None
    renewed = not renew
    while True:
        # Before verification, only inspect cookie metadata and page addresses;
        # don't enable script debugging or interfere with the human challenge.
        cookies = _cookies((await protocol.call("Storage.getCookies")).get("cookies", []))
        if not target and _verified(cookies):
            pages = (await protocol.call("Target.getTargets")).get("targetInfos", [])
            page = next((p for p in pages if p.get("type") == "page" and _input_page(p.get("url", ""))), None)
            if page:
                target = (await protocol.call("Target.attachToTarget", {
                    "targetId": page["targetId"], "flatten": True,
                }))["sessionId"]
                await protocol.call("Page.enable", target=target)
        if target:
            if not configuration:
                configuration = await _configuration_from_page(protocol, target)
            if configuration and not renewed:
                # Renew only this app profile's site token. The site's own page
                # runs verification again; no challenge interaction is scripted.
                await protocol.call("DOMStorage.removeDOMStorageItem", {
                    "storageId": {"securityOrigin": SITE, "isLocalStorage": True}, "key": "sc_tok_exp",
                }, target)
                for cookie in cookies:
                    if cookie["name"] == "sc_tok":
                        await protocol.call("Network.deleteCookies", {
                            "name": "sc_tok", "domain": cookie["domain"], "path": cookie["path"],
                        }, target)
                await protocol.call("Page.reload", {"ignoreCache": True}, target)
                renewed = True
                cookies = []
            if configuration and _verified(cookies):
                credentials = {"user_agent": version["userAgent"], "cookies": [
                    {k: c[k] for k in ("name", "value", "domain", "path")} for c in cookies
                ]}
                return configuration, credentials
        await asyncio.sleep(0.2)


async def _capture(process, port, cancelled, renew):
    deadline = time.monotonic() + TIMEOUT
    async with requests.AsyncSession(curl_options={CurlOpt.PROXY: ""}) as client:
        while True:
            _check(cancelled, process, deadline)
            try:
                response = await client.get(f"http://127.0.0.1:{port}/json/version", timeout=0.5,
                                            allow_redirects=False)
                response.raise_for_status()
                endpoint = _endpoint(response.json()["webSocketDebuggerUrl"], port)
                break
            except requests.RequestsError:
                await asyncio.sleep(0.1)
        async with client.ws_connect(endpoint, timeout=3, max_message_size=16_000_000,
                                     curl_options={CurlOpt.PROXY: ""}) as ws:
            protocol = Protocol(ws, process, cancelled, deadline)
            try:
                return await _read_session(protocol, renew)
            except ProtocolError as exc:
                raise ValueError("Could not read MapleScouter in the browser. Retry verification.") from exc
            finally:
                await protocol.close()
