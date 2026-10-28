"""Build the Item swap catalog from a saved whackybeanz/wiki snapshot plus a hand-kept overlay.

    python tools/build_swap_items.py --fetch   # refresh the snapshot (1 request per second)
    python tools/build_swap_items.py           # rebuild src/itemswap/data/items.json offline

The app never calls these sites at runtime; the generated file is committed.
"""

import argparse
import copy
import gzip
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "tools/data/swap_items_snapshot.json.gz"
OVERLAY = ROOT / "src/itemswap/data/overlay.json"
OUTPUT = ROOT / "src/itemswap/data/items.json"
API = "https://www.whackybeanz.com/api/getEquips/{group}/{cls}"
WIKI = "https://maplestorywiki.net/w/{page}?action=raw"
JOBS = ("warrior", "magician", "archer", "thief", "pirate")
STAT_KEYS = ("str", "dex", "int", "luk", "att", "matt")
# Only the fields the build reads are kept, so the snapshot stays small.
KEEP = ("id", "name", "jobType", "charType", "setType", "equipType", "level", "stats")
SLOTS = {"ring", "belt", "face", "eye", "earring", "pendant", "pocket", "secondary", "emblem", "medal", "heart", "badge",
         "hat", "top", "bottom", "shoulder", "cape", "gloves", "shoes"}


def _get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Hascone item catalog build"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def fetch(overlay):
    classes = json.loads((ROOT / "src/flaming_data/catalog_sources.json").read_text(encoding="utf-8"))["classes"]
    api, wiki = {}, {}
    for group, cls, _ in classes:
        url = API.format(group=group, cls=cls)
        body = _get(url)
        data = json.loads(body)
        items = [
            {k: e[k] for k in KEEP if k in e}
            for kind in data["equipByType"].values()
            for e in kind["equips"]
            if e.get("equipType") in SLOTS
        ]
        api[f"{group}/{cls}"] = {"url": url, "sha256": hashlib.sha256(body).hexdigest(), "items": items}
        print(f"{url}: {len(items)} items", file=sys.stderr)
        time.sleep(1)
    for page in sorted({a["page"] for a in overlay["astra"].values()}):
        url = WIKI.format(page=urllib.parse.quote(page.replace(" ", "_")))
        body = _get(url)
        wiki[page] = {"url": url, "sha256": hashlib.sha256(body).hexdigest(), "text": body.decode("utf-8")}
        print(f"{url}: {len(body)} bytes", file=sys.stderr)
        time.sleep(1)
    snapshot = {"fetched": time.strftime("%Y-%m-%d"), "api": api, "wiki": wiki}
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=0).encode("utf-8")
    SNAPSHOT.write_bytes(gzip.compress(raw, mtime=0))


def load_snapshot():
    return json.loads(gzip.decompress(SNAPSHOT.read_bytes()))


# --- wiki parsing -------------------------------------------------------------------------------

def _templates(text):
    """Yield the body of every {{Equipment ...}} template, keeping nested templates intact."""
    start = 0
    while (start := text.find("{{Equipment", start)) >= 0:
        depth, i = 0, start
        while i < len(text):
            if text.startswith("{{", i):
                depth, i = depth + 1, i + 2
            elif text.startswith("}}", i):
                depth, i = depth - 1, i + 2
                if depth == 0:
                    break
            else:
                i += 1
        yield text[start:i]
        start = i


def _fields(template):
    result = {}
    for line in template.splitlines():
        match = re.match(r"\|(\w+)=(.*)", line)
        if match:
            result[match[1]] = match[2].strip()
    return result


def _number(value):
    """Wiki cells read "30", "30%" or "Non-GMS: 9<br />GMS: 10"; GMS wins when both are given."""
    if not value:
        return 0
    gms = re.search(r"(?<!Non-)GMS:\s*(\d+)", value)
    match = gms or re.search(r"(\d[\d,]*)", value)
    return int(match[1].replace(",", "")) if match else 0


def _gms_tab(block):
    """A <tabber> holds KMS and Non-KMS copies; GMS uses Non-KMS. Untabbed blocks have one copy."""
    tabs = re.split(r"\|-\|", block)
    for tab in tabs:
        if tab.startswith("Non-KMS="):
            return tab
    return block


def parse_astra(text, section=None):
    """Return {(version, stage): wiki fields} from an Astra item page.

    Headings read "Stage 1", "Version 2: Stage 1" or "Demon Slayer Version 1: Stage 1"; `section`
    keeps only headings that name it (pages shared by two classes)."""
    result = {}
    pieces = re.split(r"^=+\s*(.*?)\s*=+\s*$", text, flags=re.M)
    for title, body in zip(pieces[1::2], pieces[2::2]):
        stage = re.search(r"Stage\s*(\d)", title)
        if not stage or (section and section not in title):
            continue
        version = re.search(r"Version\s*(\d)", title)
        templates = list(_templates(_gms_tab(body)))
        if not templates:
            continue
        result[(int(version[1]) if version else 1, int(stage[1]))] = _fields(templates[0])
    if not result:
        raise ValueError("No Astra stages found on the wiki page")
    return result


def _wiki_base(fields):
    base = {
        "str": _number(fields.get("incSTR")),
        "dex": _number(fields.get("incDEX")),
        "int": _number(fields.get("incINT")),
        "luk": _number(fields.get("incLUK")),
        "att": _number(fields.get("incWAttack")),
        "matt": _number(fields.get("incMAttack")),
        "bossDmg": _number(fields.get("incBossDamage")) + _number(fields.get("incDamage")),
        "ignoreGuard": _number(fields.get("incIgnoredDefense")),
    }
    return {k: v for k, v in base.items() if v}


# --- catalog ------------------------------------------------------------------------------------

def _api_base(stats):
    return {k: stats[k] for k in STAT_KEYS if stats.get(k)}


def _slot(item):
    return item["equipType"]


def collect(snapshot):
    """Group API records by id; identical copies across job groups become one record."""
    seen = {}
    for key, source in sorted(snapshot["api"].items()):
        for item in source["items"]:
            seen.setdefault(item["id"], {}).setdefault(item["jobType"], [])
            copies = seen[item["id"]][item["jobType"]]
            if item not in copies:
                copies.append(item)
    return seen


def _merge_copies(api_id, by_job):
    for job, copies in by_job.items():
        if len(copies) > 1:
            raise ValueError(f"{api_id} has conflicting {job} records in the API snapshot")
    records = {job: copies[0] for job, copies in by_job.items()}
    first = next(iter(records.values()))
    identical = all(
        (r["name"], r.get("stats"), r.get("charType"), r["level"])
        == (first["name"], first.get("stats"), first.get("charType"), first["level"])
        for r in records.values()
    )
    if identical and (set(records) >= set(JOBS) or "common" in records):
        return {"common": first}
    if identical and first.get("charType"):
        # Class items (Xenon's controllers) appear in more than one job group's endpoint.
        return {sorted(records)[0]: first}
    return records


def gms_names():
    """SEA -> GMS name pairs already kept by the flaming catalog."""
    names = {}
    aliases = json.loads((ROOT / "src/flaming_data/item_aliases.json").read_text(encoding="utf-8"))["aliases"]
    for sea, gms in aliases.items():
        names.setdefault(sea, []).extend(gms)
    items = json.loads((ROOT / "src/flaming_data/items.json").read_text(encoding="utf-8"))["items"]
    for item in items:
        if item.get("aliases"):
            names.setdefault(item["name"], []).extend(item["aliases"])
    return {k: list(dict.fromkeys(v)) for k, v in names.items()}


def flameable():
    items = json.loads((ROOT / "src/flaming_data/items.json").read_text(encoding="utf-8"))["items"]
    return {(i.get("source_id"), i["job_group"]): i for i in items if i.get("source_id")}


def _record(api_id, job, item, overlay, names, flames, layout):
    slot = _slot(item)
    key = api_id if job == "common" else f"{job}:{api_id}"
    patch = {**overlay["items"].get(api_id, {}), **overlay["items"].get(key, {})}
    catalog = flames.get((api_id, job)) or flames.get((api_id, "common")) or {}
    gms = names.get(item["name"], [])
    rule = overlay["gms_name_rules"].get(item.get("setType"), {})
    generated = None
    if rule and slot in rule.get("slots", []):
        generated = f"{rule['prefix']} {rule['jobs'][job]} {rule['slots'][slot]}"
    name = patch.get("name") or generated or (gms[0] if gms else item["name"])
    aliases = [n for n in dict.fromkeys([item["name"], *gms, *patch.get("aliases", [])]) if n != name]
    item_set = item.get("setType") if item.get("setType") not in (None, "none") else None
    base = patch.get("base") or _api_base(item.get("stats") or {})
    base = {**base, **overlay["set_extra"].get(item_set, {}).get(slot, {}), **patch.get("base_extra", {})}
    # Upgrade flags: item patch, then slot rule, then the flame catalog, then the slot layout.
    layout_flags = layout["slots"].get(slot) or layout["slots"].get(f"{slot}_1") or {}
    rule = overlay["slot_flags"].get(slot, {})
    record = {
        "id": key,
        "source_id": api_id,
        "name": name,
        "aliases": aliases,
        "slot": slot,
        "level": patch.get("level", item["level"]),
        "set": item_set,
        "job": job,
        "classes": sorted(item.get("charType") or []),
        "base": base,
        "flame": patch.get("flame", rule.get("flame", catalog.get("flameable", layout_flags.get("flameable", True)))),
        "potential": patch.get("potential", rule.get("potential", layout_flags.get("cubeable", True))),
        "starforce": patch.get("starforce", rule.get("starforce", True)),
        "flame_advantaged": patch.get("flame_advantaged", catalog.get("flame_advantaged")),
    }
    if item_set in overlay["set_labels"]:
        record["set_label"] = overlay["set_labels"][item_set]
    for optional in ("max_stars", "addons", "weapon_like", "unmodifiable", "note"):
        if optional in patch:
            record[optional] = patch[optional]
    return record


def _included(api_id, item, overlay):
    slot = _slot(item)
    if api_id in overlay["exclude"]:
        return False
    if api_id in overlay["include"].get(slot, []):
        return True
    if item.get("setType") in overlay["include_sets"].get(slot, []):
        return True
    if slot == "secondary":
        return item["level"] >= overlay["secondary_min_level"] and api_id not in overlay["astra"]
    return False


def astra_records(snapshot, overlay, by_id):
    records = []
    for api_id, entry in sorted(overlay["astra"].items()):
        page = snapshot["wiki"][entry["page"]]["text"]
        stages = parse_astra(page, entry.get("section"))
        api = next(iter(by_id[api_id].values()))[0] if api_id in by_id else None
        variants = []
        for (version, stage), fields in sorted(stages.items()):
            variants.append({
                "stage": stage,
                "version": version,
                "base": _wiki_base(fields),
                "max_stars": _number(fields.get("starForceEnhancements")),
            })
        # A version whose stats match an earlier one (Demon Slayer's Force Shield differs only in HP)
        # would offer two identical choices; keep the first.
        kept = {}
        for v in variants:
            kept.setdefault(v["version"], []).append((v["stage"], v["base"], v["max_stars"]))
        unique = []
        for version, rows in kept.items():
            if rows not in [kept[u] for u in unique]:
                unique.append(version)
        variants = [v for v in variants if v["version"] in unique]
        versions = sorted(unique)
        labels = entry.get("versions", {})
        for v in variants:
            v["label"] = f"Stage {v['stage']}" + (
                f" · {labels.get(str(v['version']), 'Version ' + str(v['version']))}" if len(versions) > 1 else ""
            )
        default = max(variants, key=lambda v: (v["stage"], -v["version"]))
        job = entry["job"]
        record = {
            "id": entry.get("id", api_id if job == "common" else f"{job}:{api_id}"),
            "source_id": api_id if api else None,
            "name": entry["page"].split("#")[0],
            "aliases": [n for n in dict.fromkeys([*(([api["name"]]) if api else []), *entry.get("aliases", [])])
                        if n != entry["page"].split("#")[0]],
            "slot": "secondary",
            "level": 200,
            "set": None,
            "job": job,
            "classes": sorted(entry["classes"]),
            "base": default["base"],
            "flame": False,
            "potential": True,
            "starforce": True,
            "flame_advantaged": None,
            "max_stars": default["max_stars"],
            "variants": variants,
            "wiki": snapshot["wiki"][entry["page"]]["url"],
        }
        if entry.get("weapon_like"):
            record["weapon_like"] = True
        if entry.get("addons"):
            record["addons"] = entry["addons"]
        if api:
            # Stage 3 on the wiki should match the API. Report, never silently pick one.
            api_base = _api_base(api.get("stats") or {})
            stage3 = next((v["base"] for v in variants if v["stage"] == 3 and v["version"] == 1), None)
            if stage3 is not None and {k: stage3.get(k, 0) for k in STAT_KEYS} != {
                k: api_base.get(k, 0) for k in STAT_KEYS
            }:
                print(f"  wiki/API differ for {entry['page']}: wiki {stage3} API {api_base}", file=sys.stderr)
        records.append(record)
    return records


def build(snapshot=None, overlay=None):
    snapshot = snapshot or load_snapshot()
    overlay = overlay or json.loads(OVERLAY.read_text(encoding="utf-8"))
    layout = json.loads((ROOT / "src/flaming_data/equipment_layout.json").read_text(encoding="utf-8"))
    names, flames = gms_names(), flameable()
    by_id = collect(snapshot)
    records = []
    for api_id, by_job in sorted(by_id.items()):
        merged = _merge_copies(api_id, by_job)
        for job, item in sorted(merged.items()):
            if _included(api_id, item, overlay):
                records.append(_record(api_id, job, item, overlay, names, flames, layout))
    records.extend(astra_records(snapshot, overlay, by_id))
    for manual in overlay["manual"]:
        records.append(copy.deepcopy(manual))
    records.sort(key=lambda r: (r["slot"], r["level"] or 0, r["name"], r["id"]))
    sources = sorted(
        [{"url": s["url"], "sha256": s["sha256"]} for s in snapshot["api"].values()]
        + [{"url": s["url"], "sha256": s["sha256"]} for s in snapshot["wiki"].values()],
        key=lambda s: s["url"],
    )
    return {
        "version": 1,
        "generated_by": "tools/build_swap_items.py",
        "fetched": snapshot["fetched"],
        "sources": sources,
        "items": records,
    }


def render(data):
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="refresh the snapshot from the network first")
    args = parser.parse_args()
    overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
    if args.fetch:
        fetch(overlay)
    data = build(overlay=overlay)
    sys.path.insert(0, str(ROOT / "src"))
    from itemswap.catalog import validate

    validate(data)
    OUTPUT.write_text(render(data), encoding="utf-8")
    print(f"Wrote {len(data['items'])} items to {OUTPUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
