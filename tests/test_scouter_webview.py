"""Run the production WebView2 bridge against intercepted, local fake responses."""
import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from werkzeug.serving import make_server

import app
from scouter import browser, client, service, session

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows WebView2")


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    sdk = root / ".build/webview2-sdk/sdk"
    if not sdk.exists():
        pytest.skip("Build the native launcher to install the WebView2 SDK")
    folder = tmp_path_factory.mktemp("scouter-native")
    libraries = [sdk / "lib/net462" / name for name in (
        "Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll")]
    for path in libraries + [sdk / "runtimes/win-x64/native/WebView2Loader.dll"]:
        shutil.copyfile(path, folder / path.name)
    output = folder / "ScouterChecks.exe"
    subprocess.run([
        str(Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"),
        "/nologo", "/target:winexe", "/platform:x64", f"/out:{output}",
        "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll",
        "/reference:System.Web.Extensions.dll", *[f"/reference:{p}" for p in libraries],
        str(root / "native/ScouterBrowser.cs"), str(root / "tests/native/ScouterChecks.cs"),
    ], check=True, capture_output=True, text=True)
    return output


def wait_for(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("WebView2 test did not reach the expected state")


@pytest.mark.parametrize("mode", ["valid", "success", "interactive", "slow-resource", "failure", "invalid-input", "session-expired", "session-loop", "cancel", "close"])
def test_webview_session_and_window_lifecycle(harness, tmp_path, monkeypatch, mode):
    monkeypatch.setattr(session, "_credentials", None)
    posts = []
    def http_post(url, headers, body, cancelled):
        assert session.available()
        # The actual WebView must be disposed before any calculation request.
        assert (tmp_path / "closed.txt").read_text() == (tmp_path / "windows.txt").read_text()
        posts.append(url)
        response = requests.Response()
        response.status_code = 503 if mode == "failure" else 888 if mode == "invalid-input" else 200
        response._content = b'{"calculatedData":{"score":123}}'
        if mode == "session-loop" or (mode == "session-expired" and len(posts) == 1):
            response.status_code = 401
            response._content = b'{"humanToken":"expired"}'
        return response
    monkeypatch.setattr(session, "post", http_post)
    monkeypatch.setattr(browser, "_pending", {})
    monkeypatch.setattr(browser, "_last_seen", 0)
    monkeypatch.setattr(browser, "_consumer", None)
    monkeypatch.setattr(browser, "_native", True)
    monkeypatch.setattr(browser, "_enabled", True)
    monkeypatch.setattr(browser, "_launch", Mock())
    monkeypatch.setattr(browser, "TIMEOUT", 35)
    monkeypatch.setattr(client, "_headers", None)
    monkeypatch.setattr(client, "_previous", 0)
    busy = [False]
    monkeypatch.setattr(service, "state", lambda: {"active": busy[0]})
    server = make_server("127.0.0.1", 0, app.app, threaded=True)
    monkeypatch.setattr(app, "SERVER_PORT", server.server_port)
    monkeypatch.setattr(browser, "_origin", f"http://127.0.0.1:{server.server_port}")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    process = subprocess.Popen([str(harness), browser._origin, browser.TOKEN, str(tmp_path), mode])
    cancelled = threading.Event()
    try:
        wait_for(lambda: browser._consumer is not None)
        # A connected worker must not load a website until there is work.
        assert not (tmp_path / "initialized.txt").exists()
        with ThreadPoolExecutor() as pool:
            def calculate():
                headers = client.public_headers(cancelled)
                return client._post("/api/calc/dmg", {"userStat": {"example": 1}}, headers, cancelled)
            busy[0] = True
            future = pool.submit(calculate)
            wait_for(lambda: (tmp_path / "initialized.txt").exists())
            if mode == "cancel":
                cancelled.set()
            if mode in {"cancel", "close", "failure", "invalid-input", "session-loop"}:
                expected = {"cancel": "cancelled", "close": "closed|disconnected|stopped", "failure": "HTTP 503",
                            "invalid-input": "HTTP 888", "session-loop": "still requires verification"}[mode]
                with pytest.raises(ValueError, match=expected):
                    future.result(timeout=30)
            else:
                assert future.result(timeout=30)["calculatedData"]["score"] == 123
            busy[0] = False
            assert (tmp_path / "initialized.txt").read_text() == "muted"
            assert (tmp_path / "shown.txt").read_text() == "controllable"
            wait_for(lambda: (tmp_path / "closed.txt").exists())
            assert not (tmp_path / "hidden-work.txt").exists()
            expected_posts = 0 if mode in {"cancel", "close"} else 2 if mode.startswith("session-") else 1
            assert len(posts) == expected_posts
            assert not (tmp_path / "posts.txt").exists(), "Calculations must not run in the webpage"
            if mode == "slow-resource":
                assert not (tmp_path / "page-loaded.txt").exists(), "Do not wait for unrelated page assets"
            if mode in {"valid", "success", "slow-resource"}:
                assert (tmp_path / "script-requests.txt").read_text().splitlines() == ["script"], "Reuse the script already loaded by the webpage"
            if mode in {"success", "valid"}:
                # A completed operation must dispose the actual window. Later
                # work creates a visible window and reuses the profile on disk.
                assert (tmp_path / "windows.txt").read_text() == "1"
                (tmp_path / "closed.txt").unlink()
                busy[0] = True
                browser.verify(threading.Event())
                busy[0] = False
                wait_for(lambda: (tmp_path / "closed.txt").exists())
                assert (tmp_path / "windows.txt").read_text() == "2"
                assert (tmp_path / "shown.txt").read_text() == "controllable"
                assert not (tmp_path / "hidden-work.txt").exists()
                # Repeated calculations reuse the HTTP session without reopening.
                result = client._post("/api/calc/dmg", {}, {}, threading.Event())
                assert result["calculatedData"]["score"] == 123
                assert (tmp_path / "windows.txt").read_text() == "2"
    finally:
        busy[0] = False
        cancelled.set()
        (tmp_path / "stop").touch()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        server.shutdown()
