"""The shared PP-OCRv6 text reader. Stat parsing lives in flaming.stats."""

import hashlib
import json
import threading
from collections import OrderedDict

import cv2
import numpy as np

MODEL = "PP-OCRv6_medium_rec"
CACHE_ROWS = 2048


def text_mask(image):
    """Keep native glyph pixels, then enlarge black text on white by 3x."""
    mask = (image.min(axis=2) > 105).astype(np.uint8) * 255
    mask = 255 - cv2.resize(mask, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)


def row_key(crop):
    """Exact native glyph mask; never use approximate matching for text reuse."""
    mask = crop.min(axis=2) > 105
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    ink = mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    return f"{ink.shape[0]}x{ink.shape[1]}:" + hashlib.sha256(ink.tobytes()).hexdigest()


def _cache_lookup(keys, cache, use_cache):
    return [tuple(cache[k]) if use_cache and k in cache else None for k in keys]


def _predict(model, images):
    """Read IMAGES in batches of similar width; a batch pads every row to its widest."""
    order = sorted(range(len(images)), key=lambda i: images[i].shape[1] / images[i].shape[0])
    results = [None] * len(images)
    for i, result in zip(order, model.predict([images[i] for i in order], batch_size=8), strict=True):
        results[i] = result
    return results


def _infer_missing(model, crops, missing, output):
    images = []
    for i in missing:
        c = crops[i]
        xs = np.flatnonzero((c.min(axis=2) > 105).any(axis=0))
        if len(xs):
            c = c[:, max(0, xs[0] - 3) : min(c.shape[1], xs[-1] + 4)]
        images.append(text_mask(c))
    if not images:
        return
    for i, result in zip(missing, _predict(model, images), strict=True):
        output[i] = (result["rec_text"], float(result["rec_score"]))
    uncertain = [i for i in missing if output[i][1] < 0.90]
    if uncertain:
        retry = _predict(model, [text_mask(crops[i]) for i in uncertain])
        for i, result in zip(uncertain, retry, strict=True):
            output[i] = (result["rec_text"], float(result["rec_score"]))


def _remember_confident(cache, keys, missing, output, use_cache):
    added = 0
    for i in missing:
        key = keys[i]
        if use_cache and key is not None and output[i][1] >= 0.90:
            cache[key] = output[i]
            added += 1
            if len(cache) > CACHE_ROWS:
                cache.popitem(last=False)
    return added


def load_cache(path):
    """Readings saved by save_cache for this model; empty if missing or unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf8"))
        if data.get("model") != MODEL:
            return OrderedDict()
        return OrderedDict((key, (text, score)) for key, text, score in data["rows"][-CACHE_ROWS:])
    except (OSError, ValueError, KeyError, TypeError):
        return OrderedDict()


def save_cache(path, cache):
    from utils.image_files import write_bytes

    rows = [[key, text, score] for key, (text, score) in cache.items()]
    write_bytes(path, json.dumps({"model": MODEL, "rows": rows}).encode("utf8"))


class PaddleRecognizer:
    """PP-OCRv6 with an exact-glyph cache for repeated row images.

    With CACHE_PATH the cache is kept on disk, so a new OCR process starts with
    every row it has already read instead of reading them all again.
    """

    def __init__(self, model_dir=None, cache_path=None):
        from paddleocr import TextRecognition  # pyrefly: ignore [missing-import] -- isolated OCR runtime

        self._lock = threading.Lock()
        self.cache_path = cache_path
        self.cache = load_cache(cache_path) if cache_path else OrderedDict()
        self.model = TextRecognition(
            model_name=MODEL,
            model_dir=model_dir,
            device="cpu",
            cpu_threads=4,
            enable_mkldnn=True,
        )

    def __call__(self, crops, *, use_cache=True):
        with self._lock:
            keys = [row_key(c) for c in crops]
            output = _cache_lookup(keys, self.cache, use_cache)
            missing = [i for i, v in enumerate(output) if v is None]
            _infer_missing(self.model, crops, missing, output)
            if _remember_confident(self.cache, keys, missing, output, use_cache) and self.cache_path:
                try:
                    save_cache(self.cache_path, self.cache)
                except OSError:
                    pass  # The reading stands; only the next process's head start is lost.
            return output


