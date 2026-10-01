"""Potential line parsing."""

import re

from flaming.stats import ReadError

LABELS = {
    **{s: s + " %" for s in ("STR", "DEX", "INT", "LUK")},
    "ALL STATS": "All Stats %",
    "ALL STAT": "All Stats %",
    "MAX HP": "Max HP %",
    "ATT": "ATT %",
    "ATTACK POWER": "ATT %",
    "MATT": "MATT %",
    "MAGIC ATT": "MATT %",
    "MAGIC ATTACK": "MATT %",
    "BOSS DAMAGE": "Boss Damage",
    "DAMAGE TO BOSS MONSTERS": "Boss Damage",
    "IGNORE ENEMY DEFENSE": "Ignore Enemy Defense %",
    "IGNORE DEFENSE": "Ignore Enemy Defense %",
    "IGNORE MONSTER DEF": "Ignore Enemy Defense %",
    "CRITICAL DAMAGE": "Critical Damage %",
    "CRIT DAMAGE": "Critical Damage %",
    "ITEM DROP RATE": "Item Drop Rate %",
    "MESOS OBTAINED": "Meso Amount %",
}


def parse_line(text):
    """Keep percentages separate from flat stats; never guess unknown OCR text."""
    normalized = re.sub(r"\s+", " ", text.strip()).upper().replace("\u00ab", "<").replace("\u00bb", ">")
    match = re.fullmatch(r"(.+?)\s*:?\s*\+?\s*(\d+(?:\.\d+)?)\s*%", normalized)
    if match and match[1].strip(" :") in LABELS:
        return LABELS[match[1].strip(" :")], float(match[2])
    cooldown = re.fullmatch(
        r"(?:SKILL )?COOLDOWNS?(?: REDUCTION)?\s*:?\s*-?\s*(\d+)\s*(?:SEC\.?|SECONDS?)(?:\s*REDUCTION)?",
        normalized,
    )
    if cooldown:
        return "Skill Cooldown Reduction", int(cooldown[1])
    # These utility families have no supported target contribution. Preserve
    # their text in the scan, but don't reject an otherwise readable potential.
    # Decent skill names don't affect any supported target. The game can clip
    # the trailing "skill" label, so recognize the utility family by its prefix.
    decent = r"ENABLES THE <DECENT [A-Z ]+> SKIL(?:L)?\.?\.?"
    chance_effect = r"\d+(?:\.\d+)?% CHANCE (?:TO|OF) .+"
    skill_levels = r"(?:ALL )?SKILL LEVELS?\s*:?\s*\+?\d+"
    if any(re.fullmatch(pattern, normalized) for pattern in (decent, chance_effect, skill_levels)):
        return "Junk", 0
    # Known irrelevant lines (including clipped utility descriptions) cannot
    # contribute to any supported target. Unknown or broken relevant text is an error.
    junk = (
        r"(?:MAX MP|DEF|DEFENSE|CRITICAL CHANCE|CRITICAL RATE|DAMAGE|SPEED|JUMP|"
        r"SKILL MP COST|HP RECOVERY ITEMS|MP RECOVERY ITEMS|MESO GUARD|DECENT |"
        r"CHANCE TO|WHEN HIT|WHEN ATTACKING|INCREASE INVINCIBILITY|INVINCIBILITY)\b.*"
    )
    flat = r"(?:STR|DEX|INT|LUK|MAX HP|ATT|ATTACK POWER|MATT|MAGIC ATT|MAGIC ATTACK)\s*:?\s*\+?\d+"
    if re.fullmatch(junk, normalized) or re.fullmatch(flat, normalized):
        return "Junk", 0
    raise ReadError(f"Unrecognized potential line: {text}")
