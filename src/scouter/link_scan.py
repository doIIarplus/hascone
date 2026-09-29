"""Read the equipped Link Manager rows, never the available-skills grid.

GMS names: https://maplestorywiki.net/w/Link_Skill, plus observed GMS labels.
Passive links without a Scouter field are already reflected in scanned stats.
"""

import re

import cv2

from flaming.vision import ReadError
from ocr_confidence import verify
from scouter.vision import anchor

LINKS = {
    "Solus": "ark",
    "Tide of Battle": "illium",
    "Unfair Advantage": "kadena",
    "Time to Prepare": "kain",
    "Empirical Knowledge": "magician",
    "Thief's Cunning": "thief",
    "Terms and Conditions": "angel",
    "Bravado": "hoyoung",
    "Qi Cultivation": "mukhyun",
    "Knight's Watch": "mihile",
    "Iron Will": "kaiser",
    "Moonlit Blade Learnings": "hayato",
    "Elementalism": "kanna",
}
PASSIVE = (
    "Invincible Belief",
    "Adventurer's Curiosity",
    "Pirate Blessing",
    "Cygnus Blessing",
    "Combo Kill Blessing",
    "Rune Persistence",
    "Light Wash",
    "Elven Blessing",
    "Phantom Instinct",
    "Close Call",
    "Spirit of Freedom",
    "Hybrid Logic",
    "Fury Unleashed",
    "Wild Rage",
    "Rhinne's Blessing",
    "Guiding Stars",
    "Judgment",
    "Noble Fire",
    "Innate Gift",
    "Nature's Friend",
    "Grounded Body",
    "Focus Spirit",
    "Spirit Guide Blessing",
)


def link_name(text):
    def normalize(value):
        return re.sub(r"[^a-z]", "", value.casefold())

    value = normalize(text)
    names = [
        name
        for name in (*LINKS, *PASSIVE)
        if normalize(name) == value
        or (len(value) >= 8 and text.rstrip().endswith((".", "…")) and normalize(name).startswith(value))
    ]
    if len(names) != 1:
        raise ReadError(f"Unrecognized equipped link: {text or 'unreadable'}")
    return names[0]


def links_origin(frame):
    x, y = anchor(frame, "links_applied")
    ox, oy = x - 699, y - 320
    # Both panels must be present and aligned, including the character's own link.
    sx, sy = anchor(frame, "links_own", masked=True)
    if abs(sx - (498 + ox)) > 1 or abs(sy - (322 + oy)) > 1:
        raise ReadError("Link Manager is obscured or its panels are misaligned")
    if ox + 475 < 0 or oy + 281 < 0 or ox + 1445 > frame.shape[1] or oy + 552 > frame.shape[0]:
        raise ReadError("Link Manager is clipped; move it fully inside the game")
    return ox, oy


def _link_crops(frame, ox, oy, slots):
    crops, originals = [], []
    for i, (x, y) in enumerate(slots):
        x, y = x + ox, y + oy
        pair = [frame[y : y + 22, x : x + 111], frame[y + 24 : y + 42, x + 32 : x + 87]]
        originals.extend(pair)
        # Applied rows have a pale background; thresholding isolates white text.
        # The own-link panel is dark, and its native antialiasing reads better.
        crops.extend(
            pair
            if i == 0
            else [
                cv2.cvtColor((crop.min(axis=2) > 210).astype("uint8") * 255, cv2.COLOR_GRAY2BGR)
                for crop in pair
            ]
        )
    return crops, originals


def _retry_uncertain(reader, results, originals):
    # A second mask retains the faint antialiasing of truncated Windows labels.
    # Retry only uncertain applied rows; keep the confidence/identity checks.
    confirmed = set()
    for index, (_, confidence) in enumerate(results):
        if index % 2:
            results[index], accepted = verify(reader, originals[index], results[index])
            if accepted:
                confirmed.add(index)
            continue
        if index >= 2 and confidence < 0.97:
            retry_crop = cv2.cvtColor(
                (originals[index].min(axis=2) > 180).astype("uint8") * 255, cv2.COLOR_GRAY2BGR
            )
            retry = list(reader([retry_crop]))[0]
            if retry[1] > confidence:
                results[index] = retry
    return confirmed


def _parse_link_slot(i, name, nc, level, lc, values, equipped, *, confirmed=False):
    if nc < 0.97 or lc < (0.90 if confirmed else 0.97):
        raise ReadError(f"Could not confidently read equipped link slot {i + 1}")
    name = link_name(name)
    match = re.fullmatch(r"Lv\.?\s*(\d{1,2})", level.strip(), re.I)
    if not match or not 1 <= int(match[1]) <= 15:
        raise ReadError(f"Could not read {name} level: {level}")
    key = LINKS.get(name)
    if key and int(match[1]) > (9 if key in ("thief", "magician") else 3):
        raise ReadError(f"Unexpected {name} level: {level}")
    equipped.append({"name": name, "level": int(match[1]), "own": i == 0})
    if key:
        if f"linkSkill.{key}" in values:
            raise ReadError(f"Duplicate equipped link: {name}")
        values[f"linkSkill.{key}"] = {
            "value": match[1],
            "confidence": min(nc, lc),
            "text": f"{name} {level}",
        }


def read_links(frame, reader):
    ox, oy = links_origin(frame)
    slots = [(537, 355)] + [(748 + 183 * col, 355 + 57 * row) for row in range(3) for col in range(4)]
    crops, originals = _link_crops(frame, ox, oy, slots)
    results = list(reader(crops))
    confirmed = _retry_uncertain(reader, results, originals)
    values, errors, equipped = {}, [], []
    for i in range(len(slots)):
        (name, nc), (level, lc) = results[i * 2 : i * 2 + 2]
        try:
            _parse_link_slot(i, name, nc, level, lc, values, equipped, confirmed=i * 2 + 1 in confirmed)
        except ReadError as exc:
            errors.append(str(exc))
    # Only a complete scan can prove a link absent. Unknown/occluded rows never
    # overwrite a prior link with an invented zero.
    if not errors:
        for key in LINKS.values():
            values.setdefault(f"linkSkill.{key}", {"value": "0", "confidence": 1.0, "text": "Not equipped"})
    return {"kind": "scouter", "values": values, "errors": errors, "links": equipped}
