import cv2
import numpy as np
import pytest
from test_app import ID, client, get
from test_resolution import frame, replay

from equipment_save import save
from equipment_scan import grid, hover, icons
from flaming import characters
from utils.image_files import write_png


def test_unicode_path_image_write(tmp_path):
    path = tmp_path / "\u6e2c\u8a66\ud504\ub85c\ud544" / "ring_1.png"
    pixels = np.full((34,34,3),87,np.uint8)
    write_png(path,pixels)
    decoded = cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    assert np.array_equal(decoded,pixels)


def test_missing_image_placeholder_is_not_cached(client):
    response=get(client,f"/api/characters/{ID}/equipment/ring_1/icon")
    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
    assert response.headers["Cache-Control"] == "no-store"


def test_direct_hover_captures_missing_icon_and_serves_it(client):
    image=frame("hat")
    result=hover(image,replay,"hat")
    save(characters.load(ID),result,icons(image,result))
    response=get(client,f"/api/characters/{ID}/equipment/hat/icon")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    icon=cv2.imdecode(np.frombuffer(response.data,np.uint8),cv2.IMREAD_COLOR)
    assert icon.shape == (34,34,3)
    assert icon.std()>20


def test_failed_icon_write_does_not_save_successful_equipment_scan(client,monkeypatch):
    def fail(*args):
        raise OSError("Disk full")
    monkeypatch.setattr("utils.image_files.write_bytes",fail)
    with pytest.raises(OSError,match="Disk full"):
        result=grid(frame("grid"))
        save(characters.load(ID),result,icons(frame("grid"),result))
    assert not characters.load(ID)["equipment"]
