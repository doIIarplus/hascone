"""Record OCR observations for regression fixtures from explicit local test captures."""
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from equipment_scan import hover, tooltip_bounds  # noqa: E402
from flaming.vision import PaddleRecognizer  # noqa: E402


def key(c):
    return str(c.shape) + hashlib.sha256(c.tobytes()).hexdigest()


if __name__ == '__main__':
    source = Path(sys.argv[1])
    dest = ROOT / 'tests/fixtures/equipment_hover'
    dest.mkdir(parents=True, exist_ok=True)
    reader = PaddleRecognizer(str(ROOT / 'models/PP-OCRv6_medium_rec'))
    readings = {}

    def record(crops):
        rows = reader(crops)
        for c, r in zip(crops, rows):
            readings[key(c)] = r
        return rows

    for slot in ('hat', 'gloves', 'weapon', 'ring_4', 'badge', 'medal'):
        original = cv2.imread(str(source / (slot + '.png')))
        x, y, b = tooltip_bounds(original)
        frame = np.zeros_like(original)
        frame[118:561, 904:1270] = original[118:561, 904:1270]
        frame[max(0, y - 135):b, x:x + 325] = original[max(0, y - 135):b, x:x + 325]
        cv2.imwrite(str(dest / (slot + '.png')), frame)
        result = hover(frame, record, slot)
        print(slot, json.dumps(result), flush=True)
    (dest / 'readings.json').write_text(json.dumps(readings), encoding='utf8')
    original = cv2.imread(str(source / 'equipment.png'))
    frame = np.zeros_like(original)
    frame[118:561, 904:1270] = original[118:561, 904:1270]
    cv2.imwrite(str(dest / 'grid.png'), frame)
