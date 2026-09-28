import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from equipment_scan import grid, hover, tooltip_bounds
from flaming.vision import ReadError
from game_resolution import validate_frame

FIXTURES = Path(__file__).parent / "fixtures/resolution_1366"

def frame(name):
    return cv2.imread(str(FIXTURES / (name + ".png")))

def replay(crops, **kwargs):
    data = json.loads((FIXTURES / "readings.json").read_text())
    return [data[str(c.shape) + hashlib.sha256(c.tobytes()).hexdigest()] for c in crops]

@pytest.mark.parametrize("size", [(1920,1080),(1366,768)])
def test_capture_and_reader_accept_native_sizes(monkeypatch, size):
    import capture
    import reader
    from utils import wgc_camera
    image = np.zeros((size[1],size[0],3),np.uint8)
    camera = Mock()
    camera.grab_fresh.return_value = image
    monkeypatch.setattr(wgc_camera,"WgcCamera",Mock(return_value=camera))
    monkeypatch.setattr(capture,"windows",lambda:[{"id":1}])
    monkeypatch.setattr(capture,"_camera",None)
    monkeypatch.setattr(capture,"_camera_hwnd",None)
    assert capture.frame(1).shape == image.shape
    monkeypatch.setattr("equipment_scan.grid",lambda f: f.shape)
    assert reader.read(image,"equipment") == image.shape

@pytest.mark.parametrize("size", [(1280,720),(1360,768),(2560,1440)])
def test_unsupported_sizes_not_silently_resized(size):
    with pytest.raises(ValueError,match="1366"):
        validate_frame(np.zeros((size[1],size[0],3),np.uint8))

def test_equipment_grid_native_resolution_and_clipping():
    image = frame("grid")
    assert len(grid(image)["slots"]) == 25
    moved = cv2.warpAffine(image,np.float32([[1,0,0],[0,1,500]]),(1366,768))
    with pytest.raises(ReadError,match="whole Equipment"):
        grid(moved)

def test_hat_complete_native_read():
    result = hover(frame("hat"),replay,"hat")
    assert result["required_level"] == 150
    assert result["starforce"]["stars"] == 17
    assert result["potential"]["line_tiers"] == ["Legendary"] * 3
    assert next(s["value"] for s in result["stats"] if s["name"] == "INT") == 68

def test_clipped_weapon_footer_keeps_complete_data():
    image = frame("weapon")
    with pytest.raises(ReadError,match="bottom edge"):
        tooltip_bounds(image)
    result = hover(image,replay,"weapon")
    assert result["starforce"]["stars"] == 18
    assert result["required_level"] == 200
    assert result["weapon_attack"] == {"ATT":327,"MATT":642}
    assert result["potential"]["lines"] == ["Boss Damage +35%","Boss Damage +35%","Boss Damage +30%"]
    assert next(s["value"] for s in result["stats"] if s["name"] == "Magic Attack") == 126

def test_clipped_potential_line_still_rejected():
    image = frame("weapon")
    image[680:] = 0
    with pytest.raises(ReadError,match="clipped"):
        hover(image,replay,"weapon")

def test_scouter_native_anchors_and_matrix():
    from scouter.hexa_scan import read_matrix
    from scouter.vision import origin, verify_hover
    assert origin(frame("stats")) == (448,30)
    verify_hover(frame("int"),(661,397),"INT")
    result = read_matrix(frame("hexa"))
    assert result["values"]["hexa.masteryCore1"]["value"] == "9"
    assert result["values"]["hexa.skillCore1"]["value"] == "1"
