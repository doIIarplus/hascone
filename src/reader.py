"""Explicit screenshot-in, structured readings-out boundary."""

import os
import threading
from pathlib import Path

_reader = None
lock = threading.Lock()


def read(image, mode):
    global _reader
    from flaming.vision import PaddleRecognizer
    from game_resolution import validate_frame
    validate_frame(image)
    if mode == 'equipment':
        from equipment_scan import grid
        return grid(image)
    with lock:
        if _reader is None:
            model = Path(__file__).resolve().parents[1] / "models/PP-OCRv6_medium_rec"
            if model.is_dir():
                os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
            os.environ.setdefault("GLOG_minloglevel", "2")
            _reader = PaddleRecognizer(str(model.resolve()) if model.is_dir() else None)
        if mode.startswith('hover:'):
            from equipment_scan import hover
            return hover(image, _reader, mode.split(':')[1])
        from scouter.vision import scene

        return scene(image, _reader, mode)
