"""Reliable PNG writes, including Windows paths with non-ASCII characters."""
import os
import tempfile
from pathlib import Path

import cv2


def write_png(path, image):
    path = Path(path)
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise OSError("Could not encode the item image")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(encoded.tobytes())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
