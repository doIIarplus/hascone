"""Resolve this application's bundled assets."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _find_on_disk(name):
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Invalid asset path")
    return path if path.is_file() else None


def read_payload_bytes(name):
    path = _find_on_disk(name)
    if path is None:
        raise FileNotFoundError(name)
    return path.read_bytes()


def read_payload_json(name):
    return json.loads(read_payload_bytes(name))
