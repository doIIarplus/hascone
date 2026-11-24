"""Record OCR readings for the Quanah tooltip fixtures in tests/fixtures/quanah.

Run after adding a screenshot there: every crop the reader asks about (including
verification retries) is read once with the real model and saved to
readings.json, so tests replay them without PaddleOCR.

    .venv/Scripts/python tools/record_quanah_fixtures.py
"""

import hashlib
import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from flaming.vision import PaddleRecognizer  # noqa: E402
from quanah.vision import read_piece  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/quanah"


def key(crop):
    return str(crop.shape) + hashlib.sha256(crop.tobytes()).hexdigest()


if __name__ == "__main__":
    reader = PaddleRecognizer(str(ROOT / "models/PP-OCRv6_medium_rec"))
    readings = {}

    def record(crops, use_cache=True):
        rows = reader(crops, use_cache=use_cache)
        for crop, row in zip(crops, rows, strict=True):
            readings[key(crop)] = [row[0], float(row[1])]
        return rows

    for path in sorted(FIXTURES.glob("*.png")):
        try:
            print(path.name, read_piece(cv2.imread(str(path)), record))
        except Exception as exc:  # noqa: BLE001 - report every fixture
            print(path.name, "ERROR", exc)
    (FIXTURES / "readings.json").write_text(json.dumps(readings, indent=0, sort_keys=True), encoding="utf-8")
