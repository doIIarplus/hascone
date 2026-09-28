"""Flame stat parsing and the shared PP-OCRv6 text reader.

Unknown text/layouts raise ReadError.
"""

import hashlib
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass

import cv2
import numpy as np

STAT_NAMES = {
    "str": "STR",
    "dex": "DEX",
    "int": "INT",
    "luk": "LUK",
    "maxhp": "Max HP",
    "maxmp": "Max MP",
    "attackpower": "Attack Power",
    "magicatt": "Magic Attack",
    "magicattack": "Magic Attack",
    "magicattackpower": "Magic Attack",
    "defense": "Defense",
    "speed": "Speed",
    "jump": "Jump",
    "reducedlevelrequirement": "Reduced level requirement",
    "allstats": "All Stats",
    "damage": "Damage",
    "bossdamage": "Boss Damage",
}
PERCENT_STATS = {"All Stats", "Damage", "Boss Damage"}


class ReadError(ValueError):
    """The scene cannot be read reliably."""


@dataclass(frozen=True)
class Stat:
    name: str
    value: int
    percent: bool


def text_mask(image):
    """Keep native glyph pixels, then enlarge black text on white by 3x."""
    mask = (image.min(axis=2) > 105).astype(np.uint8) * 255
    mask = 255 - cv2.resize(mask, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)


def parse_stat(text):
    normalized = "".join(text.split()).lower()
    match = re.fullmatch(r"([a-z]+)([+-])(\d{1,6})(%?)", normalized)
    if not match or match[1] not in STAT_NAMES:
        raise ReadError(f"Unrecognized stat: {text!r}")
    name = STAT_NAMES[match[1]]
    percent = bool(match[4])
    expected_sign = "-" if name == "Reduced level requirement" else "+"
    if match[2] != expected_sign:
        raise ReadError(f"Unexpected stat sign: {text!r}")
    if percent != (name in PERCENT_STATS):
        raise ReadError(f"Missing or unexpected percent sign: {text!r}")
    return Stat(name, int(match[2] + match[3]), percent)


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
    predictions = list(model.predict(images, batch_size=8))
    for i, result in zip(missing, predictions, strict=True):
        output[i] = (result["rec_text"], float(result["rec_score"]))
    uncertain = [i for i in missing if output[i][1] < 0.90]
    if uncertain:
        retry = model.predict([text_mask(crops[i]) for i in uncertain], batch_size=8)
        for i, result in zip(uncertain, retry, strict=True):
            output[i] = (result["rec_text"], float(result["rec_score"]))


def _remember_confident(cache, keys, missing, output, use_cache):
    for i in missing:
        key = keys[i]
        if use_cache and key is not None and output[i][1] >= 0.90:
            cache[key] = output[i]
            if len(cache) > 2048:
                cache.popitem(last=False)


class PaddleRecognizer:
    """PP-OCRv6 with an exact-glyph cache for repeated row images."""

    def __init__(self, model_dir=None):
        from paddleocr import TextRecognition  # pyrefly: ignore [missing-import] -- isolated OCR runtime

        self._lock = threading.Lock()
        self.cache = OrderedDict()
        self.model = TextRecognition(
            model_name="PP-OCRv6_medium_rec",
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
            _remember_confident(self.cache, keys, missing, output, use_cache)
            return output


