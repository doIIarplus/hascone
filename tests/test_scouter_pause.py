import threading
from unittest.mock import Mock

import pytest

from scouter import browser, client, session


@pytest.mark.parametrize("entry", ["configuration", "calculation", "browser", "session", "launch"])
def test_paused_integration_never_starts_network_or_browser(tmp_path, monkeypatch, entry):
    marker = tmp_path / "paused"
    marker.write_text("Investigating account lockout")
    monkeypatch.setattr(browser, "NETWORK_PAUSED", marker)
    monkeypatch.setattr(client, "_headers", None)
    direct_get, direct_post, transport, bridge = Mock(), Mock(), Mock(), Mock()
    monkeypatch.setattr(client.requests, "get", direct_get)
    monkeypatch.setattr(client.requests, "post", direct_post)
    monkeypatch.setattr(session.requests, "AsyncSession", transport)
    monkeypatch.setattr(browser, "_pending", {})
    monkeypatch.setattr(browser, "_native", True)
    monkeypatch.setattr(browser, "_origin", "http://127.0.0.1:5001")
    monkeypatch.setattr(browser, "poll", bridge)
    cancelled = threading.Event()
    with pytest.raises(ValueError, match="network access is paused"):
        if entry == "configuration":
            client.public_headers(cancelled)
        elif entry == "calculation":
            client._post("/api/calc/dmg", {}, {}, cancelled)
        elif entry == "browser":
            browser.request("GET", browser.SITE + "/en/input", {}, cancelled)
        elif entry == "session":
            session.post(browser.API + "/api/calc/dmg", {}, {}, cancelled)
        else:
            browser._launch()
    direct_get.assert_not_called()
    direct_post.assert_not_called()
    transport.assert_not_called()
    bridge.assert_not_called()
    assert not browser._pending
