"""Explicit screenshot-in, structured readings-out boundary."""

import os
import threading
from pathlib import Path

_reader = None
lock = threading.Lock()
# Relative to the data directory, like the rest of the app's saved state.
GLYPH_CACHE = Path("cache/ocr-glyphs.json")


def _recognizer():
    """The shared text reader, loading the model on first use. Call with LOCK held."""
    global _reader
    if _reader is None:
        from flaming.vision import PaddleRecognizer

        model = Path(__file__).resolve().parents[1] / "models/PP-OCRv6_medium_rec"
        if model.is_dir():
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        os.environ.setdefault("GLOG_minloglevel", "2")
        _reader = PaddleRecognizer(str(model.resolve()) if model.is_dir() else None, cache_path=GLYPH_CACHE)
    return _reader


def warm():
    """Load the model now, so the first read of a scan does not wait for it."""
    with lock:
        _recognizer()


def read(image, mode):
    from game_resolution import validate_frame
    validate_frame(image)
    if mode == 'equipment':
        from equipment_scan import grid
        return grid(image)
    with lock:
        reader = _recognizer()
        if mode.startswith('hover:'):
            from equipment_scan import hover
            return hover(image, reader, mode.split(':')[1])
        from scouter.vision import scene

        return scene(image, reader, mode)
