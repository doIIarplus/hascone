import re

from flaming.vision import ReadError


def character_name_key(name):
    """Only fold known OCR lookalikes; do not allow edits or missing letters."""
    return name.strip().casefold().translate(str.maketrans({"i": "l", "1": "l", "|": "l", "0": "o"}))


def verify_character(result, data):
    character = data["character"]
    detected = result.get("character_name", "").strip()
    expected = [character.get(key, "").strip() for key in ("name", "login_name")]
    expected = [name for name in expected if name]
    if detected and any(detected.casefold() == name.casefold() for name in expected):
        return
    if detected and any(character_name_key(detected) == character_name_key(name) for name in expected):
        # OCR-equivalent IGNs can belong to different characters. Require the
        # independently read class as well before accepting a lookalike match.
        def class_key(value):
            return re.sub(r"[^a-z0-9]", "", value.casefold())

        detected_class = class_key(result.get("character_class", ""))
        if detected_class and detected_class in {
            class_key(character["class"]),
            class_key(data["class_info"]["name"]),
        }:
            return
        raise ReadError("Character name has OCR lookalikes, but its class could not be verified. Scan again.")
    raise ReadError(
        f"Selected {character['name']}, but Character Info reads {detected or 'unknown'}. Select the logged-in character."
    )
