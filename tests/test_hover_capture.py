import time
from pathlib import Path

import cv2
import numpy as np
import pytest

import hover_queue
from equipment_scan import hover_capture_ready, hover_target, tooltip_bounds
from flaming.stats import ReadError

FIXTURES = Path(__file__).parent / "fixtures/equipment_hover"
HAT = (1175, 240)


def frame(slot):
    return cv2.imread(str(FIXTURES / (slot + ".png")))


def ready(first, second, slots, pointers):
    slot, origin, bounds = hover_target(first, pointers[0], slots)
    hover_capture_ready(first, second, slot, origin, bounds, pointers[1])
    return slot


def test_settled_hat_tooltip_is_ready():
    image = frame("hat")
    assert ready(image, image.copy(), ["hat"], (HAT, HAT)) == "hat"
    assert ready(image, image.copy(), ["gloves", "hat"], (HAT, HAT)) == "hat"


def test_wrong_slot_or_moving_cursor_is_not_ready():
    image = frame("hat")
    with pytest.raises(ReadError, match="Hover your gloves"):
        ready(image, image.copy(), ["gloves"], (HAT, HAT))
    with pytest.raises(ReadError, match="highlighted"):
        ready(image, image.copy(), ["gloves", "top"], (HAT, HAT))
    with pytest.raises(ReadError):
        ready(image, image.copy(), ["hat"], (HAT, (600, 200)))


def test_tooltip_that_moved_with_the_cursor_is_ready():
    image = frame("hat")
    moved = np.roll(image, (2, 3), axis=(0, 1))
    ready(image, moved, ["hat"], (HAT, (HAT[0] + 3, HAT[1] + 2)))


def test_changing_tooltip_is_not_ready():
    image = frame("hat")
    x, ay, bottom = tooltip_bounds(image, allow_clipped_footer=True)
    changed = image.copy()
    changed[ay + 60 : bottom - 20, x + 20 : x + 300] = 255 - changed[ay + 60 : bottom - 20, x + 20 : x + 300]
    with pytest.raises(ReadError, match="finish drawing"):
        ready(image, changed, ["hat"], (HAT, HAT))


def _wait(character):
    for _ in range(200):
        if not hover_queue.status(character)["pending"]:
            return hover_queue.status(character)
        time.sleep(0.01)
    raise AssertionError("queue did not drain")


def test_queue_saves_clean_reads_and_reports_failures(monkeypatch):
    import reader

    saved = []
    results = {"hat": {"kind": "hover", "item": "Hat", "errors": []}, "top": {"kind": "hover", "errors": ["unclear"]}}

    def read(frame, mode):
        slot = mode.split(":")[1]
        if slot == "shoes":
            raise ReadError("Tooltip is clipped")
        return dict(results[slot])

    monkeypatch.setattr(reader, "read", read)
    hover_queue.reset("c1")
    for slot in ("hat", "top", "shoes"):
        hover_queue.submit("c1", slot, None, lambda c, r: saved.append((c, r["item"], r["slot_verified"])))
    state = _wait("c1")
    assert saved == [("c1", "Hat", True)]
    assert state["done"] == ["hat"]
    assert state["failed"] == {"top": "unclear", "shoes": "Tooltip is clipped"}
    hover_queue.reset("c1")
    assert hover_queue.status("c1") == {"pending": [], "done": [], "failed": {}}


def test_hover_watch_captures_and_queues(monkeypatch):
    import app
    import capture

    image = frame("hat")
    queued = []
    monkeypatch.setattr(capture, "pointer", lambda window: HAT)
    monkeypatch.setattr(capture, "frame", lambda window: image.copy())
    monkeypatch.setattr(hover_queue, "submit", lambda character, slot, frame, save: queued.append((character, slot)))
    app.generation += 1
    app.perform({"character": "c2", "mode": "hover:hat", "slot": "hat", "window": 1, "watch": True}, app.generation, "", 0)
    assert app.job["status"] == "captured"
    assert queued == [("c2", "hat")]


def test_hover_any_captures_whichever_remaining_slot_is_hovered(monkeypatch):
    import app
    import capture

    image = frame("hat")
    queued = []
    monkeypatch.setattr(capture, "pointer", lambda window: HAT)
    monkeypatch.setattr(capture, "frame", lambda window: image.copy())
    monkeypatch.setattr(hover_queue, "submit", lambda character, slot, frame, save: queued.append(slot))
    app.generation += 1
    body = {"character": "c3", "mode": "hover:any", "slots": ["gloves", "hat"], "window": 1, "watch": True}
    app.perform(body, app.generation, "", 0)
    assert app.job["status"] == "captured" and app.job["slot"] == "hat"
    assert queued == ["hat"]
