"""Reliable PNG writes, including Windows paths with non-ASCII characters."""
import os
import tempfile
from pathlib import Path


def encode_png(image):
    import cv2

    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise OSError("Could not encode the item image")
    return encoded.tobytes()


def write_png(path, image):
    write_bytes(path, encode_png(image))


def write_bytes(path, data):
    """Atomically replace PATH with DATA; needs no image library."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(data)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
