import asyncio
import threading
from unittest.mock import Mock

import pytest
import requests

from scouter import browser, session

URL = browser.API + "/api/calc/dmg"
CREDENTIALS = {"user_agent": "test-agent", "cookies": [
    {"name": "session", "value": "synthetic", "domain": ".maplescouter.com", "path": "/"},
]}


def response(code=200, text="{}", challenge=False):
    result = requests.Response()
    result.status_code = code
    result._content = text.encode()
    if challenge:
        result.headers["cf-mitigated"] = "challenge"
    return result


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(session, "_credentials", None)
    monkeypatch.setattr(browser, "_native", True)
    monkeypatch.setattr(browser, "_origin", "http://127.0.0.1:5001")


def test_first_request_hands_off_session_and_later_requests_do_not_open_browser(monkeypatch):
    finish = Mock(side_effect=lambda *a, **kw: session.install(CREDENTIALS))
    monkeypatch.setattr(browser, "finish_client", finish)
    post = Mock(return_value=response())
    monkeypatch.setattr(session, "post", post)
    for _ in range(2):
        assert browser.request("POST", URL, {}, threading.Event(), {}).status_code == 200
    finish.assert_called_once()
    assert finish.call_args.kwargs == {"renew": False}
    assert post.call_count == 2


@pytest.mark.parametrize("failure", [response(401, '{"humanToken":"expired"}'), response(403, challenge=True)])
def test_expired_session_reopens_visible_verification_once(monkeypatch, failure):
    session.install(CREDENTIALS)
    finish = Mock(side_effect=lambda *a, **kw: session.install(CREDENTIALS))
    monkeypatch.setattr(browser, "finish_client", finish)
    post = Mock(side_effect=[failure, response()])
    monkeypatch.setattr(session, "post", post)
    assert browser.request("POST", URL, {}, threading.Event(), {}).status_code == 200
    finish.assert_called_once()
    assert finish.call_args.kwargs == {"renew": True}
    assert post.call_count == 2


@pytest.mark.parametrize("code", [401, 403, 503, 888])
def test_ordinary_api_failures_never_replay_or_reopen(monkeypatch, code):
    session.install(CREDENTIALS)
    finish = Mock()
    monkeypatch.setattr(browser, "finish_client", finish)
    post = Mock(return_value=response(code))
    monkeypatch.setattr(session, "post", post)
    assert browser.request("POST", URL, {}, threading.Event(), {}).status_code == code
    post.assert_called_once()
    finish.assert_not_called()


def test_persistent_challenge_stops_after_one_renewal(monkeypatch):
    session.install(CREDENTIALS)
    finish = Mock(side_effect=lambda *a, **kw: session.install(CREDENTIALS))
    monkeypatch.setattr(browser, "finish_client", finish)
    post = Mock(return_value=response(401, '{"humanToken":"expired"}'))
    monkeypatch.setattr(session, "post", post)
    with pytest.raises(ValueError, match="still requires verification"):
        browser.request("POST", URL, {}, threading.Event(), {})
    assert post.call_count == 2
    finish.assert_called_once()
    assert not session.available()


def fake_transport(monkeypatch, run):
    transport = Mock()
    class Transport:
        def __init__(self, **options):
            transport.options = options
            self.cookies = transport.cookies
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            transport.closed()
        async def post(self, url, **options):
            transport.post(url, **options)
            return await run()
    monkeypatch.setattr(session.requests, "AsyncSession", Transport)
    return transport


def test_http_transport_scopes_cookies_headers_and_disallows_redirects(monkeypatch):
    session.install(CREDENTIALS)
    async def run():
        return response()
    transport = fake_transport(monkeypatch, run)
    session.post(URL, {"api-key": "public", "cookie": "untrusted", "Authorization": "untrusted"}, {}, threading.Event())
    transport.cookies.set.assert_called_once_with("session", "synthetic", domain=".maplescouter.com", path="/")
    options = transport.post.call_args.kwargs
    assert options["allow_redirects"] is False
    assert options["headers"] == {"api-key": "public", "user-agent": "test-agent", "origin": browser.SITE, "referer": browser.SITE + "/"}
    transport.closed.assert_called_once()
    with pytest.raises(ValueError, match="Unsupported"):
        session.post("https://unrelated.test/api/calc/dmg", {}, {}, threading.Event())
    assert transport.post.call_count == 1


def test_stop_aborts_inflight_http_request(monkeypatch):
    session.install(CREDENTIALS)
    cancelled = threading.Event()
    aborted = []
    async def run():
        try:
            cancelled.set()
            await asyncio.sleep(10)
        finally:
            aborted.append(True)
    transport = fake_transport(monkeypatch, run)
    with pytest.raises(ValueError, match="cancelled"):
        session.post(URL, {}, {}, cancelled)
    assert aborted == [True]
    transport.post.assert_called_once()
    transport.closed.assert_called_once()


def test_network_failure_never_replays(monkeypatch):
    session.install(CREDENTIALS)
    async def run():
        raise session.requests.RequestsError("synthetic network failure")
    transport = fake_transport(monkeypatch, run)
    finish = Mock()
    monkeypatch.setattr(browser, "finish_client", finish)
    with pytest.raises(ValueError, match="Could not reach"):
        browser.request("POST", URL, {}, threading.Event(), {})
    transport.post.assert_called_once()
    finish.assert_not_called()


@pytest.mark.parametrize("value", [None, {}, {"user_agent": "agent\r\ninjected", "cookies": []},
    {"user_agent": "agent", "cookies": [{"name": "session", "value": "synthetic", "domain": ".example.com", "path": "/"}]}])
def test_handoff_rejects_invalid_or_unrelated_credentials(value):
    with pytest.raises(ValueError, match="Invalid MapleScouter session"):
        session.install(value)
    assert not session.available()
