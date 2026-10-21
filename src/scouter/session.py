"""In-memory MapleScouter session used after closing the verification browser."""
import asyncio
import contextlib
import threading

from curl_cffi import requests

_lock = threading.Lock()
_credentials = None


def install(value):
    global _credentials
    if not isinstance(value, dict):
        raise ValueError("Invalid MapleScouter session")
    agent, cookies = value.get("user_agent"), value.get("cookies")
    if not isinstance(agent, str) or not 1 <= len(agent) <= 1000 or "\r" in agent or "\n" in agent:
        raise ValueError("Invalid MapleScouter session")
    if not isinstance(cookies, list) or len(cookies) > 100:
        raise ValueError("Invalid MapleScouter session")
    safe = []
    for cookie in cookies:
        keys = ("name", "value", "domain", "path")
        if not isinstance(cookie, dict) or any(not isinstance(cookie.get(k), str) for k in keys):
            raise ValueError("Invalid MapleScouter session")
        if cookie["domain"].lstrip(".") not in {"maplescouter.com", "api.maplescouter.com"}:
            raise ValueError("Invalid MapleScouter session domain")
        if not cookie["name"] or not cookie["path"].startswith("/") or any(len(cookie[k]) > 16000 or "\r" in cookie[k] or "\n" in cookie[k] for k in keys):
            raise ValueError("Invalid MapleScouter session cookie")
        safe.append({k: cookie[k] for k in keys})
    with _lock:
        _credentials = (agent, safe)


def available():
    with _lock:
        return _credentials is not None


def clear():
    global _credentials
    with _lock:
        _credentials = None


def requires_verification(response):
    if response.headers.get("cf-mitigated") == "challenge":
        return True
    if response.status_code == 401:
        try:
            body = response.json()
            return isinstance(body, dict) and isinstance(body.get("humanToken"), str)
        except ValueError:
            pass
    return False


def post(url, headers, body, cancelled):
    from scouter.browser import allowed, ensure_network_allowed
    ensure_network_allowed()
    if not allowed("POST", url):
        raise ValueError("Unsupported MapleScouter request")
    if cancelled.is_set():
        raise ValueError("Calculation cancelled")
    with _lock:
        credentials = _credentials
    if credentials is None:
        raise ValueError("MapleScouter needs verification")
    agent, cookies = credentials
    safe_headers = {k: v for k, v in headers.items() if k.lower() in {"api-key", "content-type", "accept"}}
    safe_headers.update({"user-agent": agent, "origin": "https://maplescouter.com", "referer": "https://maplescouter.com/"})
    # Each request owns its transport. No hidden WebView stays running. Network
    # failures never replay a calculation, and credentials are never persisted.
    async def send():
        async with requests.AsyncSession(impersonate="chrome") as client:
            for cookie in cookies:
                client.cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"])
            task = asyncio.create_task(client.post(url, headers=safe_headers, json=body, timeout=45, allow_redirects=False))
            try:
                while not task.done():
                    if cancelled.is_set():
                        raise ValueError("Calculation cancelled")
                    await asyncio.wait({task}, timeout=0.25)
                return await task
            finally:
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
    try:
        # A selector loop also works in the calculation worker on Windows,
        # without a hidden browser or a helper event-loop thread.
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            response = runner.run(send())
    except requests.RequestsError as exc:
        raise ValueError("Could not reach MapleScouter. Your inputs are saved; try again later.") from exc
    if cancelled.is_set():
        raise ValueError("Calculation cancelled")
    if len(response.content) > 16_000_000:
        raise ValueError("MapleScouter response is too large")
    return response
