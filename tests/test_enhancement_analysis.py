import copy

import pytest
from test_app import ID, client, get
from test_equipment_scan import frame, replay, zero_hover

import zero
from cubing.lines import parse_line
from enhancement_analysis import snapshot
from equipment_scan import hover
from flaming import characters


def profile():
    equipment = {}
    for slot in ('hat', 'gloves', 'weapon', 'ring_4', 'badge', 'medal'):
        reading = hover(frame(slot), replay, slot)
        equipment[slot] = {**reading, 'name': reading['item'], 'hover_scanned': True}
    return {'id': ID, 'name': 'Example', 'class': 'Ren', 'equipment': equipment}


def test_real_scans_have_consistent_upgrade_odds_and_current_costs():
    p = profile()
    original = copy.deepcopy(p)
    data = snapshot(p)
    assert p == original
    assert not data['unpriced']['flame']
    assert not data['unpriced']['cube']
    assert len(data['flame_order']) == 3
    assert len(data['cube_costs']) == 3
    assert [r['probability'] for r in data['flame_order']] == sorted((r['probability'] for r in data['flame_order']), reverse=True)
    assert data['totals']['Black Flame'] == pytest.approx(sum(r['expected_mesos'] for r in data['flame_costs']))
    for cube in ('Bright', 'Glowing'):
        assert data['totals'][cube] == pytest.approx(sum(next(c['expected_mesos'] for c in r['cubes'] if c['cube']==cube) for r in data['cube_costs']))
    for row in data['flame_order']:
        current = data['items'][row['slot']]['flame_current']
        assert current['probability'] >= row['probability']
        assert current['expected_mesos'] <= row['expected_mesos']
    assert data['items']['weapon']['catalog']['level'] == 200


def test_zero_partner_sword_is_priced_with_the_weapon():
    equipment = {}
    for name, slot in (('lazuli', 'weapon'), ('lapis', 'secondary')):
        reading = zero_hover(name, slot)
        equipment[slot] = {**reading, 'name': reading['item'], 'hover_scanned': True}
    data = snapshot({'id': ID, 'name': 'Example', 'class': 'Zero', 'equipment': equipment})
    assert [r['slot'] for r in data['starforce_costs']] == ['weapon']
    assert data['totals']['Star Force'] == data['starforce_costs'][0]['expected_mesos'] > 0
    assert data['items']['secondary'] == {'mirror': zero.MIRROR_NOTE}
    assert all(r['slot'] != 'secondary' for rows in data['unpriced'].values() for r in rows)
    assert data['items']['weapon']['catalog']['level'] == 200

def test_unknown_and_epic_costs_remain_unpriced_not_zero():
    p = profile()
    p['equipment']['hat']['name'] = 'Unknown test equipment'
    p['equipment']['hat']['potential']['rank'] = 'Epic'
    data = snapshot(p)
    assert any(r['slot']=='hat' for r in data['unpriced']['flame'])
    assert any(r['slot']=='hat' and 'Epic cost unavailable' in r['reason'] for r in data['unpriced']['cube'])
    assert all(r['slot']!='hat' for r in data['flame_order'])
    assert all(r['slot']!='hat' for r in data['cube_costs'])


def test_cached_analysis_updates_on_scan_and_returns_independent_data():
    p = profile()
    first = snapshot(p)
    first['totals']['Bright'] = -1
    assert snapshot(p)['totals']['Bright'] > 0
    before = snapshot(p)['items']['hat']['flame_score']
    p['equipment']['hat']['stats'][0]['value'] += 1
    assert snapshot(p)['items']['hat']['flame_score'] != before


def test_actual_decent_skill_brackets_are_utility_only():
    assert parse_line('Enables the \u00abDecent Mystic Door\u00bb skill') == ('Junk', 0)
    with pytest.raises(ValueError):
        parse_line('STR +1O%')


def test_analysis_endpoint_and_old_hover_scan_compatibility(client):
    p = profile()
    characters.write(p)
    loaded = characters.load(ID)
    assert loaded['equipment']['hat']['status'] == 'scanned'
    response = get(client, f'/api/characters/{ID}/enhancement-analysis')
    assert response.status_code == 200
    assert len(response.json['flame_order']) == 3


def test_all_imported_aliases_resolve():
    from cubing.item_database import metadata
    from flaming.item_database import lookup
    from utils.payload_data import read_payload_json
    for item in read_payload_json("src/flaming_data/items.json")["items"]:
        for alias in item.get("aliases", []):
            assert lookup(alias, item["slot"]) is not None, (alias, item["slot"])
    for item in read_payload_json("src/cubing/data/equipment_levels.json")["items"]:
        for alias in item.get("aliases", []):
            assert metadata(alias, item["slot"]) is not None, (alias, item["slot"])


def test_starforce_current_costs_and_zero_star_items():
    p = profile()
    p["equipment"] = {"hat":p["equipment"]["hat"]}
    p["equipment"]["hat"]["starforce"] = {"status":"scanned","stars":0,"max_stars":25}
    zero = snapshot(p)
    assert zero["starforce_costs"][0]["expected_mesos"] == 0
    assert zero["totals"]["Star Force"] == 0
    p["equipment"]["hat"]["starforce"]["stars"] = 22
    result = snapshot(p)
    row = result["starforce_costs"][0]
    assert row["stars"] == 22 and row["expected_mesos"] > 0
    assert result["totals"]["Star Force"] == row["expected_mesos"]
    assert result["items"]["hat"]["starforce_current"] == row
    p["equipment"]["hat"]["starforce"]["stars"] = 31
    invalid = snapshot(p)
    assert not invalid["starforce_costs"]
    assert invalid["unpriced"]["starforce"]


def test_starforce_costs_follow_saved_event_settings(tmp_path,monkeypatch):
    import json

    from scouter import profiles as scouter
    monkeypatch.setattr(scouter,"DIRECTORY",tmp_path)
    p = profile()
    before = snapshot(p)
    (tmp_path / f"{ID}.json").write_text(json.dumps({"starforce_options":{"discount":True}}))
    after = snapshot(p)
    assert after["starforce_options"]["discount"]
    assert after["totals"]["Star Force"] < before["totals"]["Star Force"]
    assert any("Fixed Genesis" in row["reason"] for row in after["unpriced"]["starforce"])


def test_combined_cost_adds_star_force_flames_and_cheaper_cube():
    data = snapshot(profile())
    for slot, item in data['items'].items():
        combined = item.get('combined')
        if not combined:
            continue
        expected = {}
        if 'starforce_current' in item:
            expected['Star Force'] = item['starforce_current']['expected_mesos']
        if 'flame_error' not in item and item.get('flame_current', {}).get('expected_mesos') is not None:
            expected['Flames'] = item['flame_current']['expected_mesos']
        if 'cube_current' in item and 'cube_error' not in item:
            expected['Cubes'] = min(c['expected_mesos'] for c in item['cube_current'])
        assert combined['parts'] == pytest.approx(expected), slot
        assert combined['expected_mesos'] == pytest.approx(sum(expected.values()))
    hat = data['items']['hat']['combined']
    assert set(hat['parts']) == {'Star Force', 'Flames', 'Cubes'} and not hat['missing']
    assert data['totals']['Combined'] == pytest.approx(sum(r['expected_mesos'] for r in data['combined_costs']))


def test_combined_cost_lists_what_could_not_be_priced():
    p = profile()
    p['equipment']['hat']['potential']['rank'] = 'Epic'
    hat = snapshot(p)['items']['hat']['combined']
    assert 'Cubes' not in hat['parts']
    assert any(m.startswith('Potential:') for m in hat['missing'])
