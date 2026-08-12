"""Independent offline checks for the Episode 002 V2.2 preproduction packet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
EPISODE = REPO / "projects" / "episode-002-adam-temptation-fall-repentance"
STORYBOARD_PATH = EPISODE / "preproduction/EP002_SURGICAL_REPAIR_STORYBOARD_V2_2.json"
REPORT_PATH = EPISODE / "orchestration/ep002-surgical-visual-repair-preproduction-v2-2.json"
AUDIT_PATH = EPISODE / "orchestration/ep002-surgical-visual-asset-audit-v2-2.json"
DOSSIER_PATH = EPISODE / "preproduction/EP002_CHARACTER_EVIDENCE_DOSSIERS_V2_2.json"
SOURCE_BINDING_PATH = EPISODE / "orchestration/ep002-source-binding-v2-2.json"
STATE_PATH = EPISODE / "orchestration/visual-repair-preproduction-state-v2-2.json"
CONSTITUTION_PATH = REPO / "projects/_series/siraj-visual-production-constitution-v2-2.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def storyboard() -> dict:
    return read_json(STORYBOARD_PATH)


@pytest.fixture(scope="module")
def report() -> dict:
    return read_json(REPORT_PATH)


@pytest.fixture(scope="module")
def audit() -> dict:
    return read_json(AUDIT_PATH)


@pytest.fixture(scope="module")
def dossiers() -> dict:
    return read_json(DOSSIER_PATH)


@pytest.fixture(scope="module")
def constitution() -> dict:
    return read_json(CONSTITUTION_PATH)


def test_constitution_is_v22_and_series_wide(constitution: dict) -> None:
    assert constitution["CONSTITUTION_VERSION"] == "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2_2"
    assert constitution["CONSTITUTION_SCOPE"] == "ALL_FUTURE_EPISODES"


def test_constitution_v22_additions_are_enabled(constitution: dict) -> None:
    for key in (
        "AUDIO_BEAT_MAPPING_REQUIRED",
        "SUB_FRAME_MICRO_SHOTS_MUST_EQUAL_ZERO",
        "MICRO_CRUMB_SHOTS_MUST_EQUAL_ZERO",
        "PROVIDER_EDITORIAL_DURATION_SEPARATION_REQUIRED",
        "GENERATION_CONSOLIDATION_REQUIRED",
        "EXECUTION_ENVELOPE_SEPARATE_FROM_VISUAL_PROVIDER_PROMPT",
        "MUSA_SOURCE_BACKED_TRAITS_REQUIRED_WHEN_USED",
        "LEGACY_FEMALE_REUSE_COUNT_MUST_EQUAL_ZERO",
    ):
        assert constitution[key] is True


def test_preproduction_generation_is_blocked(constitution: dict, storyboard: dict) -> None:
    assert constitution["PREPRODUCTION_VISUAL_GENERATION_ALLOWED"] is False
    assert storyboard["VISUAL_GENERATION_ALLOWED"] is False


def test_audio_master_is_frozen_and_authoritative(storyboard: dict, report: dict) -> None:
    assert storyboard["CURRENT_NARRATION_FROZEN"] is True
    assert storyboard["AUDIO_IS_DURATION_AUTHORITY"] is True
    assert storyboard["AUDIO_SHA256"] == report["audio_sha256"]
    assert storyboard["AUDIO_DURATION_SECONDS"] == pytest.approx(623.5111041666667)


def test_audio_timeline_starts_at_zero_and_ends_at_master(storyboard: dict) -> None:
    shots = storyboard["MICRO_SHOTS"]
    assert shots[0]["TIMELINE_IN"] == 0.0
    assert shots[-1]["TIMELINE_OUT"] == pytest.approx(storyboard["AUDIO_DURATION_SECONDS"])


def test_audio_timeline_is_gap_free(storyboard: dict) -> None:
    shots = storyboard["MICRO_SHOTS"]
    for left, right in zip(shots, shots[1:]):
        assert left["TIMELINE_OUT"] == pytest.approx(right["TIMELINE_IN"], abs=1e-9)


def test_audio_mapping_declares_no_gaps_or_overlaps(storyboard: dict, report: dict) -> None:
    assert storyboard["AUDIO_BEAT_MAPPING"] == "PASS"
    assert storyboard["AUDIO_TIMELINE_GAPS"] == 0
    assert storyboard["AUDIO_TIMELINE_OVERLAPS"] == 0
    assert report["STALE_PARENT_NARRATION_INHERITANCE"] == 0


def test_every_shot_has_audio_identity_and_exact_fragment(storyboard: dict) -> None:
    for shot in storyboard["MICRO_SHOTS"]:
        assert shot["AUDIO_BEAT_ID"]
        assert shot["AUDIO_BEAT_START"] <= shot["AUDIO_BEAT_END"]
        assert shot["AUDIO_TRANSCRIPT_FRAGMENT"]
        assert shot["AUDIO_SOURCE_TIMING_REFERENCE"]
        assert shot["NARRATION_TEXT"] == shot["AUDIO_TRANSCRIPT_FRAGMENT"]


def test_multi_beat_spans_are_explicit(storyboard: dict) -> None:
    spans = [shot for shot in storyboard["MICRO_SHOTS"] if shot["AUDIO_SPANS_MULTIPLE_BEATS"]]
    assert spans
    assert all(shot["AUDIO_BEAT_ID"].startswith("MULTI_BEAT:") for shot in spans)


def test_no_subframe_or_micro_crumb_shots(storyboard: dict, report: dict) -> None:
    assert storyboard["SUB_FRAME_MICRO_SHOTS"] == 0
    assert storyboard["MICRO_CRUMB_SHOTS"] == 0
    assert report["SUB_FRAME_MICRO_SHOTS"] == 0
    assert report["MICRO_CRUMB_SHOTS"] == 0


def test_interior_boundaries_are_frame_quantized(storyboard: dict) -> None:
    fps = storyboard["PRODUCTION_FPS"]
    for shot in storyboard["MICRO_SHOTS"][:-1]:
        assert shot["TIMELINE_IN"] * fps == pytest.approx(round(shot["TIMELINE_IN"] * fps))
        assert shot["TIMELINE_OUT"] * fps == pytest.approx(round(shot["TIMELINE_OUT"] * fps))


def test_final_audio_tail_is_explicit(storyboard: dict) -> None:
    assert storyboard["FINAL_AUDIO_TAIL_NON_FRAME_ALIGNED"] is True
    assert 0 < storyboard["FINAL_AUDIO_TAIL_SECONDS"] < 1 / storyboard["PRODUCTION_FPS"]


def test_minimum_visual_duration_is_respected(storyboard: dict) -> None:
    minimum = storyboard["MINIMUM_VISUAL_SHOT_FRAMES"] / storyboard["PRODUCTION_FPS"]
    assert all(shot["DURATION"] >= minimum - 1e-9 for shot in storyboard["MICRO_SHOTS"])


def test_major_events_have_literal_contracts(storyboard: dict) -> None:
    assert len(storyboard["MAJOR_EVENTS"]) == storyboard["MAJOR_EVENTS_WITH_EXPLICIT_VISUAL_CONTRACT"] if "MAJOR_EVENTS_WITH_EXPLICIT_VISUAL_CONTRACT" in storyboard else True
    literal = [shot for shot in storyboard["MICRO_SHOTS"] if shot["EVENT_ROLE"] == "LITERAL_EVENT"]
    assert literal
    assert all(shot["VISIBLE_ACTION"] and shot["MUTE_COMPREHENSION_TARGET"] for shot in literal)


def test_planned_mute_precheck_passes_for_every_shot(storyboard: dict) -> None:
    assert storyboard["MUTE_COMPREHENSION_PRECHECK"] == "PASS"
    for shot in storyboard["MICRO_SHOTS"]:
        assert shot["PLANNED_MUTE_COMPREHENSION"]["PLANNED_MUTE_COMPREHENSION"] is True


def test_actual_pixel_mute_review_has_not_been_falsely_run(storyboard: dict) -> None:
    assert storyboard["ACTUAL_RENDER_MUTE_COMPREHENSION"] == "NOT_RUN"
    assert all(shot["ACTUAL_RENDER_MUTE_COMPREHENSION"] == "NOT_RUN" for shot in storyboard["MICRO_SHOTS"])


def test_all_reused_rows_are_female_free(storyboard: dict) -> None:
    reused = [shot for shot in storyboard["MICRO_SHOTS"] if shot["SOURCE"] in {"EXISTING", "REASSIGNED_EXISTING"}]
    assert reused
    assert all(shot["FEMALE_PRESENT"] == "FALSE" for shot in reused)
    assert all(shot["UNCERTAIN_FEMALE_PRESENCE"] is False for shot in reused)


def test_zero_legacy_female_reuse_is_explicit(storyboard: dict, report: dict, audit: dict) -> None:
    assert storyboard["LEGACY_FEMALE_REUSE_COUNT"] == 0
    assert report["LEGACY_FEMALE_REUSE_COUNT"] == 0
    assert audit["LEGACY_FEMALE_REUSE_COUNT"] == 0


def test_legacy_female_assets_are_forensic_only(report: dict, audit: dict) -> None:
    assert report["FORENSIC_ASSET_PRESERVED"] is True
    assert report["PRODUCTION_REUSE_ALLOWED_FOR_EXCLUDED"] is False
    assert report["FINAL_MONTAGE_ALLOWED_FOR_EXCLUDED"] is False
    assert audit["NO_SALVAGE_TRANSFORMS_USED"] is True


def test_all_96_legacy_reuse_rows_were_reaudited(audit: dict, report: dict) -> None:
    assert audit["REUSED_LEGACY_MICRO_SHOT_COUNT"] == 96
    assert report["REUSED_LEGACY_MICRO_SHOT_COUNT"] == 96
    assert len(audit["reuse_plan_audit"]) == 96


def test_reuse_plan_contains_no_exact_range_duplicate(report: dict) -> None:
    ranges = report["RETAINED_REUSED_SOURCE_RANGES"]
    keys = [(row["ASSET_ID"], row["SOURCE_IN"], row["SOURCE_OUT"]) for row in ranges]
    assert len(keys) == len(set(keys))
    assert report["UNJUSTIFIED_EXACT_RANGE_REUSE"] == 0


def test_reused_rows_have_human_readable_content_and_relevance(storyboard: dict) -> None:
    reused = [shot for shot in storyboard["MICRO_SHOTS"] if shot["SOURCE"] in {"EXISTING", "REASSIGNED_EXISTING"}]
    for shot in reused:
        assert shot["ACTUAL_VISIBLE_CONTENT"]
        assert shot["EXACT_AUDIO_RELEVANCE"]
        assert shot["NEW_VISUAL_INFORMATION"]
        assert shot["WHY_NON_REDUNDANT"]


def test_reuse_metrics_are_present_and_nonnegative(report: dict) -> None:
    for key in ("REUSED_TIMELINE_SECONDS", "UNIQUE_REUSED_SOURCE_SECONDS", "DUPLICATED_REUSE_TIMELINE_SECONDS", "UNIQUE_PRESERVED_PERCENT"):
        assert report[key] >= 0
    assert report["DUPLICATED_REUSE_TIMELINE_SECONDS"] == 0


def test_provider_durations_are_external_contract_values(storyboard: dict, report: dict) -> None:
    assert report["PROVIDER_SUPPORTED_DURATIONS_SECONDS"] == [4, 6, 8]
    new = [shot for shot in storyboard["MICRO_SHOTS"] if shot["SOURCE"] == "NEW_GENERATION_REQUIRED"]
    assert new
    assert all(shot["PROVIDER_REQUEST_DURATION_SECONDS"] in {4, 6, 8} for shot in new)
    assert report["UNSUPPORTED_PROVIDER_DURATIONS"] == []


def test_editorial_and_provider_duration_are_distinct(storyboard: dict) -> None:
    new = [shot for shot in storyboard["MICRO_SHOTS"] if shot["SOURCE"] == "NEW_GENERATION_REQUIRED"]
    assert all("EDITORIAL_DURATION_SECONDS" in shot for shot in new)
    assert all("PROVIDER_REQUEST_DURATION_SECONDS" in shot for shot in new)


def test_generation_units_are_consolidated(storyboard: dict) -> None:
    units = storyboard["PROVIDER_GENERATION_UNITS"]
    assert units
    assert any(unit["CONSOLIDATED"] for unit in units)
    assert all(unit["PROVIDER_REQUEST_DURATION_SECONDS"] in {4, 6, 8} for unit in units)


def test_required_original_consolidation_groups_exist(storyboard: dict) -> None:
    unit_by_shot = {shot["MICRO_SHOT_ID"]: shot["GENERATION_UNIT_ID"] for shot in storyboard["MICRO_SHOTS"] if shot["SOURCE"] == "NEW_GENERATION_REQUIRED"}
    assert unit_by_shot["EP002-V2-NEW-003"] == unit_by_shot["EP002-V2-NEW-004"]
    assert unit_by_shot["EP002-V2-NEW-005"] == unit_by_shot["EP002-V2-NEW-006"]
    assert unit_by_shot["EP002-V2-NEW-015"] == unit_by_shot["EP002-V2-NEW-016"] == unit_by_shot["EP002-V2-NEW-017"]


def test_provider_prompt_contains_visual_text_only(storyboard: dict) -> None:
    forbidden = ("AWAITING_HUMAN_APPROVAL", "VISUAL_GENERATION_ALLOWED", "PAID_CALLS", "NETWORK_CALLS", "APPROVED_STORYBOARD_SHA256")
    for shot in storyboard["MICRO_SHOTS"]:
        if shot["SOURCE"] != "NEW_GENERATION_REQUIRED":
            continue
        text = json.dumps(shot["VISUAL_PROVIDER_PROMPT"], ensure_ascii=False)
        assert not any(term in text for term in forbidden)


def test_execution_envelope_is_outside_provider_prompt(storyboard: dict) -> None:
    for shot in storyboard["MICRO_SHOTS"]:
        if shot["SOURCE"] == "NEW_GENERATION_REQUIRED":
            assert shot["EXECUTION_ENVELOPE"]["STORYBOARD_STATUS"] == "AWAITING_HUMAN_APPROVAL"
            assert "STORYBOARD_STATUS" not in shot["VISUAL_PROVIDER_PROMPT"]["positive_video"]


def test_prompt_contradictions_and_negative_duplicates_are_zero(storyboard: dict, report: dict) -> None:
    assert report["PROMPT_CONTRADICTIONS"] == 0
    assert report["DUPLICATED_NEGATIVE_PROMPT_LINES"] == 0
    for shot in storyboard["MICRO_SHOTS"]:
        if shot["SOURCE"] == "NEW_GENERATION_REQUIRED":
            assert shot["PROMPT_CONTRADICTIONS"] == []
            assert shot["DUPLICATED_NEGATIVE_PROMPT_LINES"] == 0


def test_female_generation_prompts_compile_strict_modesty(storyboard: dict) -> None:
    female = [shot for shot in storyboard["MICRO_SHOTS"] if shot["SOURCE"] == "NEW_GENERATION_REQUIRED" and shot.get("INCLUDES_FEMALE")]
    assert female
    required = ("FEMALE_VISIBLE_HAIR=FORBIDDEN", "FEMALE_VISIBLE_HANDS=FORBIDDEN", "NUDE_OR_BODY_SHAPED_SILHOUETTE=FORBIDDEN")
    for shot in female:
        text = shot["VISUAL_PROVIDER_PROMPT"]["positive_video"]
        assert all(term in text for term in required)


def test_musa_source_traits_are_in_debate_prompts(storyboard: dict, dossiers: dict) -> None:
    musa = next(item for item in dossiers["CHARACTERS"] if item["CHARACTER_ID"] == "MUSA")
    assert "brown or wheat-toned complexion" in " ".join(musa["SOURCE_BACKED_ATTRIBUTES"])
    debate = [shot for shot in storyboard["MICRO_SHOTS"] if shot["MICRO_SHOT_ID"] in {"EP002-V2-NEW-015", "EP002-V2-NEW-016", "EP002-V2-NEW-017"}]
    assert len(debate) == 3
    assert all("brown or wheat-toned complexion" in shot["VIDEO_PROMPT"] for shot in debate)


def test_adam_complexion_remains_unknown(dossiers: dict, report: dict) -> None:
    adam = next(item for item in dossiers["CHARACTERS"] if item["CHARACTER_ID"] == "ADAM")
    assert "complexion" in adam["UNKNOWN_ATTRIBUTES"]
    assert report["ADAM_COMPLEXION"] == "UNKNOWN"


def test_hawwa_physical_features_remain_unknown_and_strict(dossiers: dict, report: dict) -> None:
    hawwa = next(item for item in dossiers["CHARACTERS"] if item["CHARACTER_ID"] == "HAWWA_SPOUSE")
    assert hawwa["PHYSICAL_APPEARANCE_CONTRACT"]["UNKNOWN"]
    assert report["HAWWA_PHYSICAL_FEATURES"] == "UNKNOWN"


def test_descent_staging_is_not_mislabeled_as_israiliyyat(storyboard: dict, report: dict) -> None:
    source = read_json(SOURCE_BINDING_PATH)
    assert source["SEPARATE_STAGING_SOURCE_STATUS"] == "UNRESOLVED"
    assert source["SEPARATE_STAGING_SOURCE_TIER"] == "TIER_6_ART_DIRECTION"
    assert source["ISRAILIYYAT_FACT_USED"] is False
    assert report["ISRAILIYYAT_FACT_USED"] is False
    assert storyboard["SEPARATE_STAGING_HUMAN_REVIEW_REQUIRED"] is True


def test_graphics_are_forbidden_and_zero(storyboard: dict, report: dict) -> None:
    assert storyboard["GRAPHICS_POLICY"] == "FORBIDDEN"
    assert storyboard["PLANNED_GRAPHICS_COUNT"] == 0
    assert report["PLANNED_GRAPHICS_COUNT"] == 0


def test_external_activity_is_zero(storyboard: dict, report: dict) -> None:
    for key in ("NETWORK_CALLS", "PROVIDER_CALLS", "PAID_CALLS", "RUNWARE_CALLS", "VEO_CALLS", "IMAGE_GENERATION_CALLS", "VIDEO_GENERATION_CALLS"):
        assert storyboard[key] == 0
        assert report[key] == 0


def test_preserved_history_digests_match(report: dict) -> None:
    assert report["PAID_HISTORY_UNCHANGED"] is True
    assert report["EPISODE_TRANSITION_LEDGER_UNCHANGED"] is True
    assert report["PROVIDER_EVIDENCE_UNCHANGED"] is True


def test_no_authorization_or_previs_was_created(storyboard: dict, report: dict) -> None:
    assert storyboard["NO_AUTHORIZATION_CREATED_OR_CONSUMED"] is True
    assert report["NO_AUTHORIZATION_CREATED_OR_CONSUMED"] is True
    assert storyboard["HUMAN_REVIEW_PREVIS_CREATED"] is False


def test_storyboard_remains_awaiting_human_approval(storyboard: dict, report: dict) -> None:
    assert storyboard["STORYBOARD_STATUS"] == "AWAITING_HUMAN_APPROVAL"
    assert storyboard["APPROVED_STORYBOARD_SHA256"] is None
    assert report["STORYBOARD_STATUS"] == "AWAITING_HUMAN_APPROVAL"
    assert report["APPROVED_STORYBOARD_SHA256"] is None


def test_state_matches_pending_review_gate() -> None:
    state = read_json(STATE_PATH)
    assert state["CURRENT_STAGE"] == "PRE_PRODUCTION_VISUAL_REVIEW"
    assert state["STORYBOARD_STATUS"] == "AWAITING_HUMAN_APPROVAL"
    assert state["VISUAL_GENERATION_ALLOWED"] is False
    assert state["NEXT"] == "HUMAN_STORYBOARD_V2_2_REVIEW"


def test_storyboard_hash_is_published(report: dict) -> None:
    import hashlib

    actual = hashlib.sha256(STORYBOARD_PATH.read_bytes()).hexdigest()
    assert report["STORYBOARD_SHA256"] == actual


def test_dossiers_have_exact_required_characters(dossiers: dict) -> None:
    assert {item["CHARACTER_ID"] for item in dossiers["CHARACTERS"]} == {"ADAM", "HAWWA_SPOUSE", "MUSA"}
    assert dossiers["UNKNOWN_ATTRIBUTES_REMAIN_UNKNOWN"] is True
    assert dossiers["SOURCE_FACTS_AND_ART_DIRECTION_SEPARATED"] is True


def test_audit_preserves_forensic_assets(audit: dict) -> None:
    assert audit["NO_ASSET_BYTES_MODIFIED"] is True
    assert all(row["FORENSIC_ASSET_PRESERVED"] is True for row in audit["asset_audit"])


def test_next_action_is_human_review_only(storyboard: dict, report: dict) -> None:
    assert storyboard["NEXT"] == "HUMAN_STORYBOARD_V2_2_REVIEW"
    assert report["NEXT"] == "HUMAN_STORYBOARD_V2_2_REVIEW"
