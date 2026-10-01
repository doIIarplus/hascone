"""Reconcile SHINE VI skill levels across the list's top and bottom captures.

Kept free of image libraries so the app process can save guided SHINE scans;
reading the list itself is in shine_scan.
"""

from flaming.stats import ReadError

CLASSES = {"sia_astelle", "erel_light"}


def aliases(slug):
    from scouter.profiles import class_info

    if slug not in CLASSES:
        raise ReadError("This VI scanner is for Sia Astelle and Erel Light.")
    info = class_info(slug)
    result = {}
    for key, core in info["cores"].items():
        if not core.get("url") or key in ("masteryCore3", "masteryCore4", "generalCore3"):
            continue
        for name in core["english_title"].split("/"):
            result[name] = (name, "hexa." + key)
            if key.startswith("rein"):
                result[name + " Boost"] = (name, "hexa." + key)
    result["SHINE Tree of Stars"] = ("SHINE Tree of Stars", "hexa.generalCore3")
    result["Sol Janus"] = ("Sol Janus", "huntSkill.solJanus")
    for name in ("Sol Janus: Dawn", "Sol Janus: Dusk", "Sol Hecate: Styx", "Sol Hecate: Charon",
                 "Sol Hecate: Phlegethon", "Sol Hecate: Pactum", "Erda Link Stats"):
        result[name] = (name, None)
    return result


def row_values(rows):
    values = {}
    for row in rows:
        path = row["path"]
        if path is None:
            continue
        value = {key: row[key] for key in ("value", "confidence", "text")}
        if path in values and values[path]["value"] != value["value"]:
            raise ReadError("Shared mastery skill levels disagree. Rescan the VI list.")
        if path not in values or value["confidence"] < values[path]["confidence"]:
            values[path] = value
    return values


def merge_pages(top, bottom):
    if top["class"] != bottom["class"] or not top["top"] or not bottom["bottom"]:
        raise ReadError("Capture the top and bottom of the same character's VI list.")
    a, b = top["rows"], bottom["rows"]
    names_a, names_b = [r["name"] for r in a], [r["name"] for r in b]
    if top["bottom"]:
        if names_a != names_b:
            raise ReadError("VI skill list changed between captures; rescan both pages.")
        overlap = len(a)
    else:
        overlaps = [n for n in range(2, min(len(a), len(b)) + 1, 2) if names_a[-n:] == names_b[:n]]
        if not overlaps:
            raise ReadError("VI pages do not overlap. Rescan both ends of the list; do not hide or rearrange skills.")
        overlap = max(overlaps)
    for first, second in zip(a[-overlap:], b[:overlap], strict=True):
        if first["value"] != second["value"]:
            raise ReadError("VI levels changed between captures; rescan both pages.")
    combined = a + b[overlap:]
    values = row_values(combined)
    # Absence only means inactive after proving that the whole list was read.
    for _, path in aliases(top["class"]).values():
        if path and path not in values:
            values[path] = {"value": "0", "confidence": 1, "text": "Inactive in the complete Erda Link VI list"}
    return values


def prepare_save(data, page, session, baseline):
    """Reconcile only pages from one guided scan, preserving intervening edits."""
    if not isinstance(session, str) or not session or len(session) > 128:
        raise ReadError("Start a guided SHINE scan to capture the top and bottom together.")
    if page["class"] != data["class_info"]["slug"]:
        raise ReadError("VI skill list does not match the selected character class.")
    if page["position"] == "top":
        state = {"session": session, "top": page, "baseline": baseline, "complete": page["bottom"]}
        values = merge_pages(page, page) if page["bottom"] else row_values(page["rows"])
    else:
        state = data.get("shine_levels", {})
        if state.get("session") != session or not state.get("top"):
            raise ReadError("The top of this VI list was not verified. Rescan both SHINE steps.")
        values = merge_pages(state["top"], page)
        state = {**state, "bottom": page, "complete": True}
        baseline = state["baseline"]
    if any(data.get("manual_versions", {}).get(key) != baseline.get(key) for key in values):
        raise ReadError("HEXA inputs changed during the VI scan. Rescan both SHINE steps.")
    return values, state
