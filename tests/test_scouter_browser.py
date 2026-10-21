import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
import requests

from scouter import browser, client


@pytest.fixture(autouse=True)
def bridge(monkeypatch):
    monkeypatch.setattr(browser, "_pending", {})
    monkeypatch.setattr(browser, "_last_seen", 0)
    monkeypatch.setattr(browser, "_enabled", False)
    monkeypatch.setattr(browser, "_origin", "http://127.0.0.1:5001")
    monkeypatch.setattr(browser, "_message", "")
    monkeypatch.setattr(browser, "_consumer", "unit-test-connection")
    monkeypatch.setattr(browser, "TIMEOUT", 2)
    monkeypatch.setattr(browser, "_native", True)
    monkeypatch.setattr(browser, "_launch", Mock())
    monkeypatch.setattr(client, "_headers", None)
    monkeypatch.setattr(client, "_previous", 0)


def response(code=200, text="{}", challenge=False):
    result = requests.Response()
    result.status_code = code
    result._content = text.encode()
    if challenge:
        result.headers["cf-mitigated"] = "challenge"
    return result


def test_bridge_delivers_once_and_keeps_cookies_out(monkeypatch):
    launched = threading.Event()
    monkeypatch.setattr(browser, "_launch", Mock(side_effect=launched.set))
    with ThreadPoolExecutor() as pool:
        future = pool.submit(browser._browser_request, "POST", browser.API + "/api/calc/dmg",
                             {"api-key": "public-key", "cookie": "private", "Authorization": "private"},
                             threading.Event(), {"userStat": {}})
        assert launched.wait(timeout=1)
        job = browser.poll(timeout=1)
        assert job["headers"] == {"api-key": "public-key"}
        assert browser.poll(timeout=0) is None
        assert browser.progress(job["id"], verifying=True)
        assert "verification" in browser.status()
        assert browser.complete(job["id"], {"status": 200, "text": '{"score":123}'})
        assert future.result().json() == {"score": 123}
        assert not browser.complete(job["id"], {"status": 200, "text": "{}"})
    assert not browser.status()
    assert not browser._pending
    browser._launch.assert_called_once_with()


def test_cancel_removes_pending_request_and_ignores_late_response():
    cancelled = threading.Event()
    with ThreadPoolExecutor() as pool:
        future = pool.submit(browser.request, "GET", browser.SITE + "/en/input", {}, cancelled)
        job = browser.poll(timeout=1)
        cancelled.set()
        with pytest.raises(ValueError, match="cancelled"):
            future.result(timeout=1)
        assert not browser.progress(job["id"])
        assert not browser.complete(job["id"], {"status": 200, "text": "late"})
    assert not browser._pending


def test_reconnect_rejects_stale_polls_and_does_not_replay_delivered_post():
    old = browser._consumer
    with ThreadPoolExecutor() as pool:
        poll = pool.submit(browser.poll, 2, old)
        browser.connect("new-browser-connection")
        with pytest.raises(ValueError, match="connection changed"):
            poll.result(timeout=3)
        future = pool.submit(browser._browser_request, "POST", browser.API + "/api/calc/dmg", {}, threading.Event(), {})
        job = browser.poll(timeout=1, consumer="new-browser-connection")
        browser.connect("replacement-connection")
        with pytest.raises(ValueError, match="connection changed"):
            future.result(timeout=1)
        assert browser.poll(timeout=0, consumer="replacement-connection") is None
        assert not browser.complete(job["id"], {"status": 200, "text": "{}"}, "new-browser-connection")


def test_timeout_cleans_up(monkeypatch):
    monkeypatch.setattr(browser, "TIMEOUT", 0)
    with pytest.raises(ValueError, match="timed out"):
        browser.request("GET", browser.SITE + "/en/input", {}, threading.Event())
    assert not browser._pending


def test_connected_webview_does_not_open_duplicate_windows(monkeypatch):
    monkeypatch.setattr(browser, "_last_seen", time.monotonic())
    with ThreadPoolExecutor() as pool:
        future = pool.submit(browser.request, "GET", browser.SITE + "/en/input", {}, threading.Event())
        job = browser.poll(timeout=1)
        browser.complete(job["id"], {"error": "Browser closed. Retry."})
        with pytest.raises(ValueError, match="Browser closed"):
            future.result()
    browser._launch.assert_not_called()


@pytest.mark.parametrize("method,url", [
    ("GET", "https://evil.test/en/input"),
    ("POST", browser.SITE + "/en/input"),
    ("POST", browser.API + "/api/account/delete"),
    ("GET", browser.SITE + "/_next/static/chunks/%2e%2e/private.js"),
    ("GET", "https://maplescouter.com.evil.test/en/input"),
    ("GET", "https://user@maplescouter.com/en/input"),
    ("GET", browser.SITE + "/en/input#secret"),
])
def test_bridge_rejects_unrelated_requests(method, url):
    with pytest.raises(ValueError, match="Unsupported"):
        browser.request(method, url, {}, threading.Event())
    browser._launch.assert_not_called()


@pytest.mark.parametrize("value", [{"status": True, "text": ""}, {"status": 200, "text": {}},
                                    {"error": {}}, None])
def test_response_validation(value):
    with pytest.raises(ValueError, match="Invalid browser"):
        browser.complete("unknown", value)


def test_client_switches_to_browser_for_challenge_and_keeps_session(monkeypatch):
    monkeypatch.setattr(browser, "finish_client", Mock())
    direct = Mock(return_value=response(403, "challenge", True))
    bridged = Mock(side_effect=[
        response(200, '<script src="/_next/static/chunks/8153-test.js"></script>'),
        response(200, '"api-key":"public";"https://api.maplescouter.com"'),
        response(200, '{"calculatedData":{}}'),
    ])
    def through_browser(*args, **kwargs):
        browser._enabled = True
        return bridged(*args, **kwargs)
    monkeypatch.setattr(client.requests, "get", direct)
    monkeypatch.setattr(browser, "request", through_browser)
    monkeypatch.setattr(client, "cookie_headers", lambda: {})
    post = Mock()
    monkeypatch.setattr(client.requests, "post", post)
    headers = client.public_headers(threading.Event())
    assert headers["api-key"] == "public"
    client._post("/api/calc/dmg", {}, headers, threading.Event())
    assert direct.call_count == 1
    assert [call.args[0] for call in bridged.call_args_list] == ["GET", "GET", "POST"]
    post.assert_not_called()


def test_plain_api_failure_never_replays_in_browser(monkeypatch):
    monkeypatch.setattr(client.requests, "post", lambda *a, **k: response(403))
    monkeypatch.setattr(client, "cookie_headers", lambda: {})
    bridged = Mock()
    monkeypatch.setattr(browser, "request", bridged)
    with pytest.raises(ValueError, match="HTTP 403"):
        client._post("/api/calc/dmg", {}, {}, threading.Event())
    bridged.assert_not_called()


def test_native_configuration_and_session_are_collected_in_one_request(monkeypatch):
    monkeypatch.setattr(browser, "_enabled", True)
    bridged = Mock(return_value=response(200, '{"api_key":"public-key"}'))
    monkeypatch.setattr(browser, "request", bridged)
    finish = Mock()
    monkeypatch.setattr(browser, "finish_client", finish)
    cancelled = threading.Event()
    assert client.public_headers(cancelled)["api-key"] == "public-key"
    assert client.public_headers(cancelled)["api-key"] == "public-key"
    bridged.assert_called_once_with("CONFIG", browser.SITE + "/en/input", {}, cancelled)
    finish.assert_not_called()
