import json
import threading
from collections import OrderedDict

import numpy as np

from flaming import vision


class Model:
    def __init__(self):
        self.calls = 0

    def predict(self, images, batch_size=8):
        self.calls += 1
        return [{"rec_text": "STR +10", "rec_score": 0.99} for _ in images]


def recognizer(path):
    # Built without __init__ so the test never loads Paddle.
    reader = vision.PaddleRecognizer.__new__(vision.PaddleRecognizer)
    reader._lock = threading.Lock()
    reader.cache_path = path
    reader.cache = vision.load_cache(path) if path else OrderedDict()
    reader.model = Model()
    return reader


def row():
    crop = np.zeros((22, 120, 3), np.uint8)
    crop[6:16, 10:60] = 255
    return crop


def test_a_new_ocr_process_reuses_rows_read_before(tmp_path):
    path = tmp_path / "cache" / "ocr-glyphs.json"
    first = recognizer(path)
    assert first([row()]) == [("STR +10", 0.99)]
    assert first.model.calls == 1
    second = recognizer(path)
    assert second([row()]) == [("STR +10", 0.99)]
    assert second.model.calls == 0


def test_unreadable_or_other_model_cache_starts_empty(tmp_path):
    path = tmp_path / "ocr-glyphs.json"
    assert vision.load_cache(path) == {}
    path.write_text("not json")
    assert vision.load_cache(path) == {}
    path.write_text(json.dumps({"model": "another", "rows": [["key", "text", 1.0]]}))
    assert vision.load_cache(path) == {}
    path.write_text(json.dumps({"model": vision.MODEL, "rows": [["key", "text", 1.0]]}))
    assert vision.load_cache(path) == {"key": ("text", 1.0)}


def test_rows_are_batched_by_width_but_returned_in_order(tmp_path):
    class Widths(Model):
        def predict(self, images, batch_size=8):
            self.order = [image.shape[1] for image in images]
            return [{"rec_text": str(image.shape[1]), "rec_score": 0.99} for image in images]

    reader = recognizer(None)
    reader.model = Widths()
    crops = []
    for width in (300, 60, 180):
        crop = np.zeros((22, width + 20, 3), np.uint8)
        crop[6:16, 10:10 + width] = 255
        crops.append(crop)
    widths = [int(text) for text, _ in reader(crops)]
    assert reader.model.order == sorted(widths)
    assert widths[1] < widths[2] < widths[0]
