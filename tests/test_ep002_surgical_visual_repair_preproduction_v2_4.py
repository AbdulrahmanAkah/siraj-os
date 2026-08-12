from __future__ import annotations
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EP = REPO / 'projects/episode-002-adam-temptation-fall-repentance'
STORY = EP / 'preproduction/EP002_SURGICAL_REPAIR_STORYBOARD_V2_4.json'
CERT = EP / 'orchestration/ep002-surgical-visual-repair-preproduction-v2-4.json'
TEMPORAL = EP / 'orchestration/ep002-legacy-female-temporal-human-review-v2-4.json'

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def test_v24_cost_and_generation_plan():
    s = load(STORY)
    assert s['PROVIDER_GENERATION_UNIT_COUNT'] == 27
    assert s['PLANNED_PROVIDER_REQUEST_SECONDS'] == 208
    assert s['PLANNED_VEO_720P_COST_USD'] == 10.40
    assert s['PLANNED_COST_CAP_USD'] == 12.0
    assert s['PLANNED_COST_WITHIN_CAP'] is True

def test_v24_legacy_reuse_below_half_and_duplicates_reduced():
    s = load(STORY)
    assert s['LEGACY_REUSED_TIMELINE_PERCENT'] < 50.0
    assert s['CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT'] <= 9
    assert s['REUSED_TIMELINE_SECONDS'] < 309.0

def test_v24_no_legacy_generic_tail_after_479_583():
    s = load(STORY)
    for shot in s['MICRO_SHOTS']:
        if shot['TIMELINE_IN'] >= 479.5833333333333 - 1e-9:
            assert shot['SOURCE'] not in {'EXISTING', 'REASSIGNED_EXISTING'}

def test_v24_callbacks_do_not_cost_provider_calls():
    s = load(STORY)
    callbacks = [x for x in s['MICRO_SHOTS'] if x['SOURCE'] == 'CALLBACK_FROM_PLANNED_GENERATION']
    assert len(callbacks) == 19
    assert s['CALLBACK_PROVIDER_CALLS_REQUIRED'] == 0
    assert s['CALLBACK_MAX_USE_COUNT_PER_GENERATION_UNIT'] <= 2
    for shot in callbacks:
        assert shot['PROVIDER_REQUEST_DURATION_SECONDS'] == 0
        assert shot['CALLBACK_MUST_NOT_TRIGGER_PROVIDER_CALL'] is True
        assert abs((shot['CALLBACK_SOURCE_OUT'] - shot['CALLBACK_SOURCE_IN']) - shot['DURATION']) < 1e-6

def test_v24_temporal_female_review_closed_pass():
    a = load(TEMPORAL)
    s = load(STORY)
    assert a['STATUS'] == 'PASS_HUMAN_ALL_FRAME_REVIEW'
    assert a['ASSETS_REVIEWED'] == 40
    assert a['VIDEO_ASSETS_REVIEWED'] == 29
    assert a['STATIC_IMAGES_REVIEWED'] == 11
    assert a['TOTAL_DECODED_VIDEO_FRAMES_REVIEWED'] == 4811
    assert a['CONTACT_SHEETS_REVIEWED'] == 92
    assert a['LEGACY_FEMALE_REUSE_COUNT'] == 0
    assert s['LEGACY_FEMALE_REUSE_COUNT'] == 0

def test_v24_generation_still_blocked():
    s = load(STORY)
    c = load(CERT)
    assert s['STORYBOARD_STATUS'] == 'AWAITING_HUMAN_APPROVAL'
    assert s['APPROVED_STORYBOARD_SHA256'] is None
    assert s['VISUAL_GENERATION_ALLOWED'] is False
    assert s['PAID_GENERATION_AUTHORIZATION_GRANTED'] is False
    assert c['VISUAL_GENERATION_ALLOWED'] is False
    assert c['PAID_CALLS'] == 0

def test_v24_no_word_level_claim():
    s = load(STORY)
    assert s['AUDIO_WORD_LEVEL_ALIGNMENT_STATUS'] == 'UNAVAILABLE_NOT_CLAIMED'
    assert s['AUDIO_ALIGNMENT_PRECISION'] == 'BEAT_LEVEL_PLUS_HUMAN_EVENT_AND_RECAP_ANCHORS'
