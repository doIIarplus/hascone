import pytest
from test_app import BASE, ID, client, get  # noqa: F401

import app
import hover_queue
from flaming import characters
from scouter import profiles, service


def remove(client, identifier=ID):
    return client.delete(f"/api/characters/{identifier}", base_url=BASE,
                         headers={"X-Hascone-Token": app.TOKEN})


def test_delete_removes_only_selected_character_and_saved_data(client, tmp_path, monkeypatch):
    monkeypatch.setattr(characters, "ORDER_PATH", tmp_path / "order.json")
    monkeypatch.setattr(service, "_job", {"active": False})
    monkeypatch.setattr(hover_queue, "_state", {})
    other = "b" * 32
    characters.write({"id": other, "name": "Other", "class": "Shadower", "equipment": {}})
    characters.save_order([ID, other])
    profiles.write(ID, profiles.load(ID))
    characters.portrait_path(ID).write_bytes(b"portrait")
    folder = characters.PROFILE_DIR / ID
    folder.mkdir()
    (folder / "hat.png").write_bytes(b"scan")
    assert remove(client).status_code == 200
    assert not folder.exists()
    assert not characters.portrait_path(ID).exists()
    assert not (profiles.DIRECTORY / f"{ID}.json").exists()
    assert get(client, "/api/characters").json["default_character"] == other
    assert characters._saved_order() == [other]
    assert characters.load(other)["name"] == "Other"
    assert remove(client, other).status_code == 200
    assert get(client, "/api/characters").json["default_character"] is None
    assert characters._saved_order() == []


@pytest.mark.parametrize("busy", ["capture", "ocr", "scouter"])
def test_cannot_delete_during_processing(client, monkeypatch, busy):
    monkeypatch.setattr(hover_queue, "_state", {ID: {"pending": ["overview"] if busy == "ocr" else [], "done": [], "failed": {}}})
    monkeypatch.setattr(service, "_job", {"active": busy == "scouter", "profile": ID})
    monkeypatch.setattr(app, "job", {"active": busy == "capture"})
    assert remove(client).status_code == 409
    assert characters.load(ID)["name"] == "Example"


def test_delete_requires_token_and_existing_identifier(client):
    assert client.delete(f"/api/characters/{ID}", base_url=BASE).status_code == 403
    assert remove(client, "not-a-character").status_code == 400
    assert remove(client, "d" * 32).status_code == 400
    assert characters.load(ID)["name"] == "Example"


def test_delete_one_scouter_calculation(client, monkeypatch):
    monkeypatch.setattr(service, "_job", {"active": False})
    data = profiles.load(ID)
    data["history"] = [{"id": "old", "created": "2026-09-01T00:00:00Z", "simulations": [{"id": "s"}]},
                       {"id": "new", "created": "2026-09-02T00:00:00Z"}]
    profiles.write(ID, data)
    path = f"/api/scouter/characters/{ID}/history/"
    headers = {"X-Hascone-Token": app.TOKEN}
    assert client.delete(path + "old", base_url=BASE).status_code == 403
    assert client.delete(path + "old", base_url=BASE, headers=headers).status_code == 200
    assert [r["id"] for r in profiles.load(ID)["history"]] == ["new"]
    assert client.delete(path + "old", base_url=BASE, headers=headers).status_code == 400
    # A running calculation, simulation or comparison may still read saved results.
    monkeypatch.setattr(service, "_job", {"active": True})
    assert client.delete(path + "new", base_url=BASE, headers=headers).status_code == 400
    assert [r["id"] for r in profiles.load(ID)["history"]] == ["new"]
