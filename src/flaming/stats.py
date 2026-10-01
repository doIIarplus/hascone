"""Flame stat names, parsing and the shared ReadError.

Kept free of image libraries: the app process imports this for scoring and
editing, and only the scanner and OCR processes load OpenCV and Paddle.
"""

import re
from dataclasses import dataclass

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
