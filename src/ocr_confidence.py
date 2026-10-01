"""Verify uncertain numeric OCR without inflating its reported confidence."""

import re

import cv2

from flaming.stats import ReadError

AUTO_CONFIDENCE = 0.97
AGREEMENT_CONFIDENCE = 0.90


def padded(crop):
    return cv2.copyMakeBorder(crop, 8, 8, 8, 8, cv2.BORDER_CONSTANT)


def numeric_row(text):
    """Compare the whole label, numbers, signs and units; ignore spacing only."""
    if not re.search(r"\d", text):
        raise ReadError("No numeric value")
    return re.sub(r"\s+", "", text).casefold()


def verify(reader, crop, reading, parse=numeric_row, *, variants=None):
    """Return (reading, accepted). Fresh variants must agree on parsed values.

    A high-confidence retry can recover an unreadable original, but a valid
    conflicting value is never replaced. Two readings at >=90% may agree;
    confidence stays at the lower score instead of being promoted to 97%.
    """
    def value(result):
        try:
            return parse(result[0])
        except (ReadError, ValueError):
            return None

    original = value(reading)
    if reading[1] >= AUTO_CONFIDENCE:
        return reading, original is not None
    seen = original
    supporting = reading if original is not None and reading[1] >= AGREEMENT_CONFIDENCE else None
    for candidate in variants if variants is not None else [padded(crop)]:
        retry = list(reader([candidate], use_cache=False))[0]
        recovered = value(retry)
        if recovered is None:
            continue
        if seen is not None and recovered != seen:
            return reading, False
        seen = recovered
        if retry[1] >= AUTO_CONFIDENCE:
            return retry, True
        if retry[1] >= AGREEMENT_CONFIDENCE:
            if supporting is not None:
                return min((supporting, retry), key=lambda result: result[1]), True
            supporting = retry
    return reading, False
