from test_app import ID, client, get, post  # noqa: F401

from flaming import characters

OTHER = "b" * 32
THIRD = "c" * 32


def ids(client):
    return [p["id"] for p in get(client, "/api/characters").json["profiles"]]


def test_saved_order_drives_listing_and_new_characters_follow(client, tmp_path, monkeypatch):
    monkeypatch.setattr(characters, "ORDER_PATH", tmp_path / "character_order.json")
    for identifier in (OTHER, THIRD):
        characters.write({"id": identifier, "name": "X" + identifier[:3], "class": "Shadower", "equipment": {}})
    assert ids(client) == [ID, OTHER, THIRD]
    r = post(client, "/api/characters/order", {"order": [THIRD, ID, OTHER]})
    assert r.status_code == 200 and r.json["order"] == [THIRD, ID, OTHER]
    assert ids(client) == [THIRD, ID, OTHER]
    assert get(client, "/api/characters").json["default_character"] == THIRD
    fourth = "d" * 32
    characters.write({"id": fourth, "name": "New", "class": "Shadower", "equipment": {}})
    assert ids(client) == [THIRD, ID, OTHER, fourth]


def test_order_must_list_every_character_once(client, tmp_path, monkeypatch):
    monkeypatch.setattr(characters, "ORDER_PATH", tmp_path / "character_order.json")
    characters.write({"id": OTHER, "name": "Other", "class": "Shadower", "equipment": {}})
    for bad in ([ID], [ID, ID], [ID, OTHER, THIRD], "nope"):
        assert post(client, "/api/characters/order", {"order": bad}).status_code == 400
    assert ids(client) == [ID, OTHER]
