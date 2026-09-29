import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from test_app import ID, client

from equipment_scan import capabilities, grid, hover, hovered_slot, save, tooltip_bounds
from flaming import characters
from flaming.vision import ReadError
from scouter import profiles

FIXTURES = Path(__file__).parent / 'fixtures/equipment_hover'


def frame(slot):
    return cv2.imread(str(FIXTURES/(slot+'.png')))


def replay(crops, **kwargs):
    records=json.loads((FIXTURES/'readings.json').read_text(encoding='utf8'))
    return [records[str(c.shape)+hashlib.sha256(c.tobytes()).hexdigest()] for c in crops]


def test_live_grid_and_wrong_slot():
    image=frame('grid')
    result=grid(image)
    assert len(result['slots']) == 25
    assert hovered_slot(image,(1175,240)) == 'hat'
    assert hovered_slot(image,(998,284)) == 'eye'
    with pytest.raises(ReadError):
        hovered_slot(image,(600,200))
    image[250:450,1000:1270]=0
    with pytest.raises(ReadError):
        grid(image)


def test_filtered_tooltip_footer_requires_continuous_edge_and_corner(monkeypatch):
    import equipment_scan

    x, ay, bottom = 20, 120, 400
    image = np.full((500, 400, 3), 50, dtype=np.uint8)
    image[bottom - 2, x + 20:x + 300] = 64
    image[bottom - 1, x + 20:x + 300] = 20
    image[bottom - 11:bottom, x + 306:x + 323] = equipment_scan.template("tooltip_bottom_right")
    monkeypatch.setattr(equipment_scan, "_find_currently_equipped", lambda *args: (1, x + 155, ay))
    assert tooltip_bounds(image) == (x, ay, bottom)
    # A horizontal line without the tooltip's corner is insufficient.
    image[bottom - 11:bottom, x + 306:x + 323] = 50
    with pytest.raises(ReadError, match="bottom edge"):
        tooltip_bounds(image)


def test_hat_combines_stars_flames_and_potential():
    result=hover(frame('hat'),replay,'hat')
    assert result['required_level']==150
    assert result['starforce']['stars']==22
    assert {s['name']:s['value'] for s in result['stats']} == {'STR':64,'DEX':24,'All Stats':6,'Max MP':2700}
    assert result['potential']['line_tiers']==['Legendary','Unique','Unique']


def test_weapon_does_not_include_soul_or_starforce_in_flames():
    result=hover(frame('weapon'),replay,'weapon')
    assert result['weapon_attack']=={'ATT':778,'MATT':124}
    assert next(s['value'] for s in result['stats'] if s['name']=='Attack Power')==210
    assert result['potential']['lines']==['Boss Damage +35%','Boss Damage +40%','Attack Power +10%']


def test_glove_prime_lines():
    result=hover(frame('gloves'),replay,'gloves')
    assert result['starforce']['stars']==18
    assert result['potential']['line_tiers'].count(result['potential']['rank'])==2
    assert result['potential']['lines'][:2]==['Critical Damage +8%']*2


@pytest.mark.parametrize('slot',['ring_4','badge','medal'])
def test_live_non_enhanceable_items(slot):
    result=hover(frame(slot),replay,slot)
    assert result['flameable'] is False
    assert result['cubeable'] is False
    assert result['starforce']['status']=='not_applicable'
    assert 'stats' not in result
    if slot=='ring_4':
        assert result['ring_level']==4


def test_item_specific_exceptions():
    assert capabilities('medal','Immortal Legacy',None,[],'')['flameable'] is True
    assert capabilities('medal','Maple Campus',None,[],'')['flameable'] is False
    for name in ('Ghost Ship Exorcist','Sengoku Hakase Badge'):
        assert capabilities('badge',name,None,[],'')['cubeable'] is True
    assert capabilities('badge','Crystal Ventus Badge',None,[],'')['cubeable'] is False


def test_clipped_tooltip_rejected():
    image=frame('hat')
    x,y,b=tooltip_bounds(image)
    image[b-10:b+2,x:x+325]=0
    with pytest.raises(ReadError):
        tooltip_bounds(image)


def test_save_equipment_then_hover_and_ring(client):
    profile=characters.load(ID)
    save(profile,grid(frame('grid')),frame('grid'))
    assert len(characters.load(ID)['equipment'])==25
    result=hover(frame('hat'),replay,'hat')
    save(characters.load(ID),result,frame('hat'))
    assert characters.load(ID)['equipment']['hat']['starforce']['stars']==22
    result=hover(frame('ring_4'),replay,'ring_4')
    save(characters.load(ID),result,frame('ring_4'))
    assert profiles.load(ID)['inputs']['special.continuosRing']=='4'


def test_persistent_camera_reused(monkeypatch):
    import capture
    import utils.wgc_camera as wgc
    camera=Mock()
    camera.grab_fresh.return_value=np.zeros((1080,1920,3),np.uint8)
    constructor=Mock(return_value=camera)
    monkeypatch.setattr(wgc,'WgcCamera',constructor)
    monkeypatch.setattr(capture,'windows',lambda:[{'id':1}])
    monkeypatch.setattr(capture,'_camera',None)
    monkeypatch.setattr(capture,'_camera_hwnd',None)
    capture.frame(1)
    capture.frame(1)
    constructor.assert_called_once()
    camera.release.assert_not_called()


def test_stat_source_cell_rejects_previous_tooltip(monkeypatch):
    from scouter import vision
    monkeypatch.setattr(vision,'origin',lambda _: (844,162))
    vision.verify_hover(None,(1060,510),'STR')
    with pytest.raises(ReadError):
        vision.verify_hover(None,(1060,510),'ATT')
    vision.verify_hover(None,(1060,637),'ATT')


@pytest.mark.parametrize("heading,confidence,cleared", [("[Base Value]", .99, True), ("", 0, False), ("Base Value", .5, False)])
def test_absent_attack_row_only_clears_with_visible_next_section(monkeypatch, heading, confidence, cleared):
    from scouter import vision
    monkeypatch.setattr(vision, "anchor", lambda *a, **k: (10, 10))
    reader = Mock(side_effect=[[("Base Value : 3185", .99), ("% Value : 51 %", .99), ("", 0)], [(heading, confidence)]])
    result = vision.tooltip(np.zeros((200, 300, 3), dtype=np.uint8), reader)
    assert (result["values"].get("unaffected", {}).get("value") == "0") is cleared


def test_scouter_critical_rate_error_is_actionable():
    from scouter.client import validate_score
    with pytest.raises(ValueError, match="100% critical rate"):
        validate_score({"boss380_hexaStat": -6})
    validate_score({"boss380_hexaStat": 47411, "specEfficiency": {}, "hexaUsed": [0, 0]})


@pytest.mark.parametrize("stat,y,left,right,wrong", [
    ("STR",346,12,239,"DEX"), ("DEX",346,240,449,"STR"),
    ("INT",368,12,239,"LUK"), ("LUK",368,240,449,"INT"),
    ("HP",324,12,239,"STR"), ("ATT",473,12,239,"MATT"),
    ("MATT",495,12,239,"ATT"),
])
def test_hover_accepts_whole_row_but_rejects_other_stats(monkeypatch,stat,y,left,right,wrong):
    from scouter import vision
    monkeypatch.setattr(vision,"origin",lambda _: (400,100))
    for x in (left,left+20,(left+right)//2,right):
        for dy in (-10,0,11):
            point=(400+x,100+y+dy)
            vision.verify_hover(None,point,stat)
            with pytest.raises(ReadError):
                vision.verify_hover(None,point,wrong)
    for point in ((400+left-1,100+y),(400+right+1,100+y),(400+left,100+y-11),(400+left,100+y+12),None):
        with pytest.raises(ReadError):
            vision.verify_hover(None,point,stat)


def test_low_confidence_name_retries_alone():
    calls=[]
    def reader(crops, **kwargs):
        results=replay(crops)
        calls.append((len(crops), kwargs))
        if len(calls)==1:
            results[0]=[results[0][0], .7]
        return results
    result=hover(frame('hat'), reader, 'hat')
    assert result['item']=='Royal Warrior Helm'
    assert calls[1]==(1, {'use_cache': False})


def test_expanded_bonus_details_recover_cursor_obscured_int():
    records = json.loads((FIXTURES/'dreamy_belt_readings.json').read_text(encoding='utf-8'))
    def reader(crops, **kwargs):
        return [records[str(c.shape)+hashlib.sha256(c.tobytes()).hexdigest()] for c in crops]
    result = hover(frame('dreamy_belt'), reader, 'belt')
    assert {s['name']:s['value'] for s in result['stats']} == {
        'INT':102, 'LUK':36, 'All Stats':6, 'Reduced level requirement':-25}
    assert result['required_level'] == 200
    assert len(result['potential']['lines']) == 3


def test_invalid_bonus_detail_is_not_silently_dropped():
    from equipment_scan import parse_bonus_detail
    with pytest.raises(ReadError):
        parse_bonus_detail('INT LUK +3?')
