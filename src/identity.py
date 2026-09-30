import re

from flaming.vision import ReadError

# Character Info cuts long names short with dots, e.g. "NotFamAny..". Names are
# letters and digits only, so OCR reading one or more trailing dots means a cut.
TRUNCATED = re.compile(r"(.+?)\s*(?:\.+|…)")


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
    lookalike = detected and any(character_name_key(detected) == character_name_key(name) for name in expected)
    cut = TRUNCATED.fullmatch(detected)
    prefix = character_name_key(cut[1]) if cut else ""
    shortened = len(prefix) >= 5 and any(
        character_name_key(name).startswith(prefix) and len(name) > len(cut[1]) for name in expected
    )
    if lookalike or shortened:
        # OCR-equivalent or cut-off IGNs can belong to different characters. Require
        # the independently read class as well before accepting the match.
        def class_key(value):
            return re.sub(r"[^a-z0-9]", "", value.casefold())

        detected_class = class_key(result.get("character_class", ""))
        if detected_class and detected_class in {
            class_key(character["class"]),
            class_key(data["class_info"]["name"]),
        }:
            return
        raise ReadError(
            "Character Info shows only the start of this long name, and its class could not be verified. Scan again."
            if shortened and not lookalike
            else "Character name has OCR lookalikes, but its class could not be verified. Scan again."
        )
    raise ReadError(
        f"Selected {character['name']}, but Character Info reads {detected or 'unknown'}. Select the logged-in character."
    )
