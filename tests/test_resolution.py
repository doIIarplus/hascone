import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from equipment_scan import grid, hover, tooltip_bounds
from flaming.stats import ReadError
from game_resolution import normalize_scan, scan_point, validate_frame

FIXTURES = Path(__file__).parent / "fixtures/resolution_1366"

def frame(name):
    return cv2.imread(str(FIXTURES / (name + ".png")))

def replay(crops, **kwargs):
    data = json.loads((FIXTURES / "readings.json").read_text())
    return [data[str(c.shape) + hashlib.sha256(c.tobytes()).hexdigest()] for c in crops]

@pytest.mark.parametrize("size", [(2560,1440),(1920,1080),(1366,768)])
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

@pytest.mark.parametrize("size", [(1280,720),(1360,768),(3440,1440)])
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


def test_native_panels_at_1440p_use_panel_relative_coordinates():
    from scouter.hexa_scan import read_matrix
    from scouter.vision import origin, verify_hover

    def moved(name):
        return cv2.warpAffine(frame(name), np.float32([[1, 0, 700], [0, 1, 400]]), (2560, 1440))

    assert len(grid(moved("grid"))["slots"]) == 25
    assert origin(moved("stats")) == (1148, 430)
    verify_hover(moved("int"), (1361, 797), "INT")
    result = read_matrix(moved("hexa"))
    assert result["values"]["hexa.masteryCore1"]["value"] == "9"
    assert result["values"]["hexa.skillCore1"]["value"] == "1"


@pytest.mark.parametrize("scale", [1, 2])
def test_1440p_detects_panel_scale_and_maps_hover_coordinates(scale):
    from scouter.vision import origin, verify_hover

    # Reuse only the existing Character Info panel, without introducing a new
    # screenshot containing player names. Position it on an even pixel origin.
    panel = frame("int")[30:712, 448:921]
    image = np.zeros((1440, 2560, 3), np.uint8)
    panel = cv2.resize(panel, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    image[40:40 + panel.shape[0], 200:200 + panel.shape[1]] = panel
    normalized, detected = normalize_scan(image, "tooltip:mainStat")
    assert detected == scale
    assert origin(normalized) == (200 // scale, 40 // scale)
    point = (200 + (661 - 448) * scale, 40 + (397 - 30) * scale)
    verify_hover(normalized, scan_point(point, detected), "INT")


def test_1080p_capture_is_not_resampled():
    image = np.zeros((1080, 1920, 3), np.uint8)
    normalized, scale = normalize_scan(image, "overview")
    assert normalized is image
    assert scale == 1


def filtered_frame(name):
    # Simulate the game's filtered stretch using existing fixtures only.
    return cv2.resize(frame(name), (2560, 1440), interpolation=cv2.INTER_LINEAR)


def test_1440p_filtered_grid_and_hover_coordinates():
    from equipment_scan import hovered_slot

    normalized, scale = normalize_scan(filtered_frame("grid"), "equipment")
    assert normalized.shape == (768, 1366, 3)
    assert len(grid(normalized)["slots"]) == 25
    # Horizontal and vertical divisors differ; a uniform 1.875 scale drifts.
    sx, sy = scale
    assert sx == 2560 / 1366 and sy == 1440 / 768
    point = scan_point((int(775 * sx), int(166 * sy)), scale)
    assert hovered_slot(normalized, point) == "hat"
    normalized[200:400, 740:855] = 0
    with pytest.raises(ReadError, match="overlapping"):
        grid(normalized)


def test_1440p_filtered_stats_and_tooltip_alignment():
    from scouter.vision import origin, verify_hover

    normalized, scale = normalize_scan(filtered_frame("int"), "tooltip:mainStat")
    assert origin(normalized) == (448, 30)
    sx, sy = scale
    verify_hover(normalized, scan_point((round(661 * sx), round(397 * sy)), scale), "INT")
    with pytest.raises(ReadError):
        verify_hover(normalized, scan_point((round(661 * sx), round(353 * sy)), scale), "INT")


def test_1440p_filtered_tooltip_footer_stays_bounded():
    normalized, _ = normalize_scan(filtered_frame("hat"), "hover:hat")
    # The real fixture is flush with the bottom. Do not invent extra screen
    # space that would let a clipped tooltip masquerade as a complete one.
    assert tooltip_bounds(normalized, allow_clipped_footer=True)[2] <= 768
    normalized[680:] = 0
    with pytest.raises(ReadError, match="bottom edge"):
        tooltip_bounds(normalized)


def test_live_and_uploaded_1440p_capture_use_same_reader_coordinates(monkeypatch):
    import base64

    import app
    import capture
    import scan_steps

    image = filtered_frame("grid")
    point = (int(775.5 * 2560 / 1366), int(166.5 * 1440 / 768))
    monkeypatch.setattr(capture, "frame", lambda window: image)
    monkeypatch.setattr(capture, "pointer", lambda window: point)
    body = {"window": 1, "mode": "hover:hat"}
    live, before = app._acquire_scan_image(body)
    assert before == scan_steps._pointer(body, body["_scan_scale"])
    assert before == (775, 166)
    scan_steps.verify(body, live, before, None)

    encoded = base64.b64encode(cv2.imencode(".png", image)[1]).decode("ascii")
    uploaded, pointer = app._acquire_scan_image({"image": encoded, "mode": "hover:hat"})
    assert pointer is None
    assert np.array_equal(live, uploaded)


@pytest.mark.parametrize("fixture", ["hexa", "demon_slayer_hexa"])
def test_1440p_filtered_matrix_preserves_verified_levels_and_pending_nodes(fixture):
    from scouter.hexa_scan import read_matrix

    if fixture == "hexa":
        original = frame("hexa")
    else:
        panel = cv2.imread(str(FIXTURES.parent / "demon_slayer_hexa.png"))
        original = np.zeros((768, 1366, 3), np.uint8)
        original[50:660, 200:1056] = panel
    expected = read_matrix(original)
    stretched = cv2.resize(original, (2560, 1440), interpolation=cv2.INTER_LINEAR)
    normalized, scale = normalize_scan(stretched, "hexa")
    assert scale == (2560 / 1366, 1440 / 768)
    actual = read_matrix(normalized)
    assert actual["pending"] == expected["pending"]
    assert {k: v["value"] for k, v in actual["values"].items()} == {
        k: v["value"] for k, v in expected["values"].items()
    }
