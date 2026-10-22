import asyncio
import threading
import time
from unittest.mock import Mock

import pytest

from scouter import browser, session
from scouter import desktop_browser as desktop


def run(coroutine):
    return asyncio.run(coroutine)


def cookie(name="sc_tok", domain=".maplescouter.com", value="synthetic", **extra):
    return {"name": name, "domain": domain, "value": value, "path": "/", "expires": time.time() + 600, **extra}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(session, "_credentials", None)
    monkeypatch.setattr(desktop, "_configuration", None)
    monkeypatch.setattr(browser, "_native", True)
    monkeypatch.setattr(browser, "_origin", "http://127.0.0.1:5001")


def test_browser_launch_is_visible_isolated_muted_and_has_logon_workaround(tmp_path):
    args = desktop.arguments(tmp_path / "chrome.exe", tmp_path / "app-profile", 42001)
    assert f"--user-data-dir={tmp_path / 'app-profile'}" in args
    assert "--disable-features=AutofillAiWalletPrivatePasses" in args
    assert "--disable-background-mode" in args
    assert "--mute-audio" in args
    assert "--remote-debugging-address=127.0.0.1" in args
    assert "--remote-debugging-port=42001" in args
    assert args[-2:] == ["--new-window", desktop.PAGE]
    assert not any("headless" in a or "automation" in a for a in args)


@pytest.mark.parametrize("url", ["ws://evil.test:42001/devtools/browser/test", "ws://127.0.0.1:1/devtools/browser/test",
                                "wss://127.0.0.1:42001/devtools/browser/test", "ws://user@127.0.0.1:42001/devtools/browser/test",
                                "ws://127.0.0.1:42001/devtools/page/test"])
def test_only_owned_loopback_browser_endpoint_is_accepted(url):
    with pytest.raises(ValueError, match="Invalid local"):
        desktop._endpoint(url, 42001)


def test_cookie_scope_and_expiry():
    values = [cookie(), cookie(domain="api.maplescouter.com"), cookie(domain="maplescouter.com.evil.test")]
    assert desktop._cookies(values) == values[:2]
    assert desktop._verified(values[:1])
    assert not desktop._verified([cookie(expires=time.time() - 1)])
    assert not desktop._verified([cookie(name="cf_clearance")])


def test_cancelled_capture_never_opens_browser(monkeypatch):
    launch = Mock()
    monkeypatch.setattr(desktop.subprocess, "Popen", launch)
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ValueError, match="cancelled"):
        desktop.capture(cancelled)
    launch.assert_not_called()


@pytest.mark.parametrize("failure", [False, True, "socket"])
def test_capture_closes_owned_browser_before_install_and_cleans_up_errors(tmp_path, monkeypatch, failure):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(desktop, "executable", lambda: tmp_path / "chrome.exe")
    process = Mock()
    monkeypatch.setattr(desktop.subprocess, "Popen", Mock(return_value=process))
    closed = []
    monkeypatch.setattr(desktop, "_stop", lambda p: closed.append(p))
    async def capture(*args):
        assert not closed
        if failure == "socket":
            raise desktop.WebSocketError("Do not expose raw browser errors")
        if failure:
            raise ValueError("Browser closed")
        return {"api_key": "public"}, {"user_agent": "test", "cookies": [cookie()]}
    monkeypatch.setattr(desktop, "_capture", capture)
    original_install = session.install
    def install(credentials):
        assert closed == [process]
        original_install(credentials)
    monkeypatch.setattr(session, "install", install)
    if failure:
        with pytest.raises(ValueError, match="Could not connect" if failure == "socket" else "Browser closed"):
            desktop.capture(threading.Event())
        assert not session.available()
    else:
        assert desktop.capture(threading.Event()) == {"api_key": "public"}
        assert session.available()
        # Refreshing the public header cache doesn't reopen a working session.
        assert desktop.capture(threading.Event()) == {"api_key": "public"}
        desktop.subprocess.Popen.assert_called_once()
    assert closed == [process]


class FakeProtocol:
    def __init__(self, cookies, resources=None):
        self.cookies = iter(cookies)
        self.calls = []
        self.resources = resources or []
        self.tree_count = 0

    async def call(self, method, params=None, target=None):
        self.calls.append((method, params, target))
        if method == "Browser.getVersion":
            return {"userAgent": "test"}
        if method == "Storage.getCookies":
            return {"cookies": next(self.cookies)}
        if method == "Target.getTargets":
            return {"targetInfos": [{"type": "page", "url": desktop.PAGE, "targetId": "own-page"}]}
        if method == "Target.attachToTarget":
            return {"sessionId": "own-session"}
        if method == "Page.getResourceTree":
            self.tree_count += 1
            # The site token may be present before its client scripts load.
            return {"frameTree": {"frame": {"id": "frame", "url": desktop.PAGE},
                                  "resources": [] if self.tree_count == 1 else self.resources}}
        if method == "Page.getResourceContent":
            return {"content": '"api-key":"public";"https://api.maplescouter.com"'}
        return {}


def test_cold_profile_waits_for_human_session_then_loaded_configuration():
    protocol = FakeProtocol([[], [cookie()], [cookie(), cookie(domain="unrelated.test")]], [
        {"url": "https://unrelated.test/_next/static/chunks/secret.js"},
        {"url": desktop.SITE + "/_next/static/chunks/8153-public.js"},
    ])
    config, credentials = run(desktop._read_session(protocol, False))
    assert config == {"api_key": "public"}
    assert len(credentials["cookies"]) == 1
    methods = [c[0] for c in protocol.calls]
    assert methods.index("Target.attachToTarget") > methods.index("Storage.getCookies") + 1
    assert methods.index("Page.enable") < methods.index("Page.getResourceTree")
    assert all("Runtime" not in method for method in methods)
    reads = [params["url"] for method, params, _ in protocol.calls if method == "Page.getResourceContent"]
    assert reads == [desktop.SITE + "/_next/static/chunks/8153-public.js"]


def test_renewal_deletes_only_site_token_and_waits_for_new_session():
    old, fresh = cookie(value="old"), cookie(value="fresh")
    protocol = FakeProtocol([[old], [old], [], [fresh]], [
        {"url": desktop.SITE + "/_next/static/chunks/8153-public.js"},
    ])
    _, credentials = run(desktop._read_session(protocol, True))
    assert credentials["cookies"][0]["value"] == "fresh"
    deletes = [params for method, params, _ in protocol.calls if method == "Network.deleteCookies"]
    assert deletes == [{"name": "sc_tok", "domain": ".maplescouter.com", "path": "/"}]
    assert sum(method == "Page.reload" for method, _, _ in protocol.calls) == 1
    assert not any(method == "Storage.clearCookies" for method, _, _ in protocol.calls)


def test_protocol_cancellation_still_closes_browser():
    class Socket:
        def __init__(self):
            self.sent = []
        async def send_json(self, value):
            self.sent.append(value)
    ws = Socket()
    cancelled = threading.Event()
    cancelled.set()
    protocol = desktop.Protocol(ws, Mock(), cancelled, time.monotonic() + 10)
    with pytest.raises(ValueError, match="cancelled"):
        run(protocol.call("Storage.getCookies"))
    run(protocol.close())
    assert [m["method"] for m in ws.sent] == ["Browser.close"]


def test_config_and_verify_use_installed_browser_without_starting_webview(monkeypatch):
    capture = Mock(return_value={"api_key": "public"})
    monkeypatch.setattr(desktop, "capture", capture)
    launch = Mock()
    monkeypatch.setattr(browser, "_launch", launch)
    cancelled = threading.Event()
    assert browser.request("CONFIG", desktop.PAGE, {}, cancelled).json() == {"api_key": "public"}
    browser.verify(cancelled)
    assert capture.call_args_list[0].kwargs == {"renew": False}
    assert capture.call_args_list[1].kwargs == {"renew": True}
    launch.assert_not_called()
    assert not browser.status()
