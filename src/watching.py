"""Validation for repeated screenshot scans."""

import hashlib
import json


def signature(result):
    def semantic(value):
        if isinstance(value, dict):
            return {k: semantic(v) for k, v in value.items()
                    if k not in ("confidence", "text", "origin", "errors", "pending")}
        if isinstance(value, list):
            return [semantic(v) for v in value]
        return value
    return hashlib.sha256(json.dumps(semantic(result), sort_keys=True).encode()).hexdigest()


def acceptable(result):
    if result.get("errors"):
        return False
    return bool(result.get("values") or result.get("links") or result.get("slots") or result.get("kind") == "hover")


def scan_can_save(body, result):
    if result.get("errors"):
        return False
    mode = body["mode"]
    if mode == 'equipment':
        return True
    if mode.startswith('hover:'):
        return bool(result.get('slot_verified'))
    if mode.startswith("tooltip:"):
        return bool(result.get("slot_verified"))
    if mode == "weapon":
        return bool(result.get("slot_verified"))
    return True
