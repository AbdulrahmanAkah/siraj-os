from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EP = REPO / "projects/episode-002-adam-temptation-fall-repentance"

STORY = EP / "preproduction/EP002_SURGICAL_REPAIR_STORYBOARD_V2_3.json"
DOSSIERS = EP / "preproduction/EP002_CHARACTER_EVIDENCE_DOSSIERS_V2_3.json"
SOURCE = EP / "orchestration/ep002-source-binding-v2-3.json"
CERT = EP / "orchestration/ep002-surgical-visual-repair-preproduction-v2-3.json"
TEMPORAL = EP / "orchestration/ep002-legacy-female-temporal-audit-v2-3.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_v23_generation_remains_blocked():
    s = load(STORY)
    assert s["STORYBOARD_STATUS"] == "AWAITING_HUMAN_APPROVAL"
    assert s["APPROVED_STORYBOARD_SHA256"] is None
    assert s["VISUAL_GENERATION_ALLOWED"] is False
    assert s["NETWORK_CALLS"] == 0
    assert s["PROVIDER_CALLS"] == 0
    assert s["PAID_CALLS"] == 0

def test_v23_surgical_cost_plan():
    s = load(STORY)
    assert len(s["MICRO_SHOTS"]) == 111
    assert s["EDITORIAL_NEW_MICRO_SHOT_COUNT"] == 29
    assert s["REUSED_LEGACY_MICRO_SHOT_COUNT_RETAINED"] == 82
    assert s["PROVIDER_GENERATION_UNIT_COUNT"] == 23
    assert s["PLANNED_PROVIDER_REQUEST_SECONDS"] == 176
    assert s["UNSUPPORTED_PROVIDER_DURATIONS"] == []

def test_every_generation_unit_fits_provider_source():
    s = load(STORY)
    shots = {x["MICRO_SHOT_ID"]: x for x in s["MICRO_SHOTS"]}
    for unit in s["PROVIDER_GENERATION_UNITS"]:
        assert unit["PROVIDER_REQUEST_DURATION_SECONDS"] in {4, 6, 8}
        assert unit["SOURCE_RANGE_CAPACITY_PASS"] is True
        for sid in unit["EDITORIAL_MEMBER_SHOT_IDS"]:
            assert shots[sid]["PROVIDER_SOURCE_OUT"] <= unit["PROVIDER_REQUEST_DURATION_SECONDS"] + 1e-9

def test_provider_prompt_has_one_canonical_field_and_no_execution_state():
    s = load(STORY)
    forbidden = (
        "AWAITING_HUMAN_APPROVAL",
        "VISUAL_GENERATION_ALLOWED",
        "APPROVED_STORYBOARD_SHA256",
        "PAID_CALLS",
        "NETWORK_CALLS",
        "PROVIDER_CALLS",
        "AUTHORIZATION",
    )
    for shot in s["MICRO_SHOTS"]:
        if shot["SOURCE"] != "NEW_GENERATION_REQUIRED":
            continue
        assert "COMPILED_PROVIDER_PROMPT" not in shot
        assert shot["CANONICAL_PROVIDER_PROMPT_FIELD"] == "VISUAL_PROVIDER_PROMPT"
        text = json.dumps(shot["VISUAL_PROVIDER_PROMPT"], ensure_ascii=False)
        assert not any(term.lower() in text.lower() for term in forbidden)

def test_shared_source_math_is_real():
    s = load(STORY)
    shots = {x["MICRO_SHOT_ID"]: x for x in s["MICRO_SHOTS"]}

    assert shots["EP002-V2-NEW-003"]["GENERATION_UNIT_ID"] == shots["EP002-V2-NEW-004"]["GENERATION_UNIT_ID"]
    assert shots["EP002-V2-NEW-003"]["PROVIDER_SOURCE_IN"] == 0.0
    assert shots["EP002-V2-NEW-003"]["PROVIDER_SOURCE_OUT"] == 4.0
    assert shots["EP002-V2-NEW-004"]["PROVIDER_SOURCE_IN"] == 4.0
    assert shots["EP002-V2-NEW-004"]["PROVIDER_SOURCE_OUT"] == 8.0

    assert shots["EP002-V2-NEW-005"]["GENERATION_UNIT_ID"] == shots["EP002-V2-NEW-006"]["GENERATION_UNIT_ID"]
    assert shots["EP002-V2-NEW-006"]["PROVIDER_SOURCE_OUT"] <= 8.0

    assert shots["EP002-V2-NEW-015"]["GENERATION_UNIT_ID"] == shots["EP002-V2-NEW-016"]["GENERATION_UNIT_ID"]
    assert shots["EP002-V2-NEW-017"]["GENERATION_UNIT_ID"] != shots["EP002-V2-NEW-015"]["GENERATION_UNIT_ID"]

def test_timeline_is_contiguous_and_frame_quantized():
    s = load(STORY)
    shots = s["MICRO_SHOTS"]
    fps = s["PRODUCTION_FPS"]
    assert shots[0]["TIMELINE_IN"] == 0.0
    assert abs(shots[-1]["TIMELINE_OUT"] - 623.5111041666667) < 1e-9
    for left, right in zip(shots, shots[1:]):
        assert abs(left["TIMELINE_OUT"] - right["TIMELINE_IN"]) < 1e-9
    for shot in shots[:-1]:
        assert abs(shot["TIMELINE_IN"] * fps - round(shot["TIMELINE_IN"] * fps)) < 1e-6
        assert abs(shot["TIMELINE_OUT"] * fps - round(shot["TIMELINE_OUT"] * fps)) < 1e-6

def test_controlled_reuse_is_transparent_and_bounded():
    s = load(STORY)
    assert s["MAX_EXACT_SOURCE_RANGE_USE_COUNT"] <= 2
    assert s["CONSECUTIVE_IDENTICAL_REUSE_COUNT"] == 0
    assert s["MAJOR_EVENT_DEPENDENCE_ON_CONTROLLED_DUPLICATE_SUPPORT"] == 0
    assert s["CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT"] > 0
    assert s["UNJUSTIFIED_EXACT_RANGE_REUSE"] == 0

def test_eating_no_fruit_through_fabric():
    s = load(STORY)
    shots = {x["MICRO_SHOT_ID"]: x for x in s["MICRO_SHOTS"]}
    for sid in ("EP002-V2-NEW-001", "EP002-V2-NEW-007"):
        prompt = shots[sid]["VIDEO_PROMPT"].lower()
        assert "occlusion" in prompt
        assert "fabric penetration" in prompt

def test_shared_supplication():
    s = load(STORY)
    shots = {x["MICRO_SHOT_ID"]: x for x in s["MICRO_SHOTS"]}
    prompt = shots["EP002-V2-NEW-010"]["VIDEO_PROMPT"].lower()
    assert "both figures" in prompt
    assert "hands remain fully hidden" in prompt

def test_earth_shots_begin_on_earth():
    s = load(STORY)
    shots = {x["MICRO_SHOT_ID"]: x for x in s["MICRO_SHOTS"]}
    for sid in ("EP002-V2-NEW-013", "EP002-V2-NEW-014"):
        assert "first frame is already on earth" in shots[sid]["VIDEO_PROMPT"].lower()

def test_musa_authentic_hair_variant_not_collapsed():
    d = load(DOSSIERS)
    musa = next(x for x in d["CHARACTERS"] if x["CHARACTER_ID"] == "MUSA")
    variants = musa["PHYSICAL_APPEARANCE_CONTRACT"]["AUTHENTIC_VARIANT_ATTRIBUTES"]["hair_texture"]
    assert any("straight" in x for x in variants)
    assert any("curly" in x for x in variants)
    assert musa["VISUAL_BIBLE"]["HAIR_RENDER_POLICY"] == "LOW_DETAIL_DO_NOT_CANONICALIZE_VARIANT"

def test_descent_is_tier5_non_authoritative():
    s = load(SOURCE)
    assert s["SEPARATE_STAGING_SOURCE_TIER"] == "TIER_5_PERMISSIBLE_ISRAILIYYAT"
    assert s["EXACT_GEOGRAPHY_ASSERTED"] is False
    lower = next(x for x in s["SOURCE_RECORDS"] if x["SOURCE_TIER"] == "TIER_5_PERMISSIBLE_ISRAILIYYAT")
    assert lower["ASSERTION_MODE"] == "PERMISSIBLE_VISUAL_STAGING_ONLY"
    assert lower["EXACT_LOCATIONS_RENDERABLE"] is False
    assert lower["HUMAN_REVIEW_REQUIRED"] is True

def test_temporal_female_certification_is_fail_closed_pending_human():
    a = load(TEMPORAL)
    s = load(STORY)
    assert a["STATUS"] == "AWAITING_HUMAN_ALL_FRAME_REVIEW"
    assert a["ALL_DECODED_VIDEO_FRAMES_CONTACT_SHEETED"] is True
    assert a["PRODUCTION_REUSE_CERTIFIED"] is False
    assert s["TEMPORAL_FEMALE_AUDIT_STATUS"] == "AWAITING_HUMAN_ALL_FRAME_CONTACT_SHEET_REVIEW"
    assert s["VISUAL_GENERATION_ALLOWED"] is False

def test_certification_does_not_fake_final_pass():
    c = load(CERT)
    assert c["STATUS"] == "PASS_AUTOMATED_V2_3_GATES_PENDING_HUMAN_TEMPORAL_AUDIT"
    assert c["VISUAL_GENERATION_ALLOWED"] is False
    assert c["TEMPORAL_FEMALE_HUMAN_REVIEW_STATUS"] == "PENDING"
    assert c["ACTUAL_RENDER_MUTE_COMPREHENSION"] == "NOT_RUN"
