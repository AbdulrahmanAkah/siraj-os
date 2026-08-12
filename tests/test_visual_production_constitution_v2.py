from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.application.visual_production_constitution_v2 import (
    ConstitutionValidationError,
    VisualPlanningValidationError,
    assert_visual_generation_gate,
    compile_visual_prompt_v2,
    load_visual_production_constitution_v2,
    source_fact_art_direction_overlap,
    validate_character_dossier,
    validate_character_dossiers,
    validate_constitution_mapping,
    validate_micro_shot_storyboard,
    validate_prompt_contradictions,
    validate_source_hierarchy_records,
    validate_temporal_reuse_audit,
)


REPO = Path(__file__).resolve().parents[1]
STORYBOARD = REPO / "projects/episode-002-adam-temptation-fall-repentance/preproduction/EP002_SURGICAL_REPAIR_STORYBOARD_V2.json"
DOSSIERS = REPO / "projects/episode-002-adam-temptation-fall-repentance/preproduction/EP002_CHARACTER_EVIDENCE_DOSSIERS_V2.json"
AUDIT = REPO / "projects/episode-002-adam-temptation-fall-repentance/orchestration/ep002-surgical-visual-asset-audit-v2.json"


def load_outputs() -> tuple[object, dict, list[dict], dict[str, dict]]:
    constitution = load_visual_production_constitution_v2(REPO)
    storyboard = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    dossier_packet = json.loads(DOSSIERS.read_text(encoding="utf-8"))
    audit_packet = json.loads(AUDIT.read_text(encoding="utf-8"))
    dossiers = dossier_packet["CHARACTERS"]
    audits = {item["ASSET_ID"]: item for item in audit_packet["asset_audit"] if item["REUSE_ELIGIBLE"]}
    return constitution, storyboard, dossiers, audits


def test_series_constitution_v2_is_global_and_fail_closed() -> None:
    constitution = load_visual_production_constitution_v2(REPO)
    assert constitution.version == "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2"
    assert constitution.data["CONSTITUTION_SCOPE"] == "ALL_FUTURE_EPISODES"
    assert constitution.data["FAIL_CLOSED"] is True
    assert constitution.data["GRAPHICS_POLICY"]["GRAPHICS_ALLOWED"] is False
    assert constitution.data["FEMALE_MODESTY_MAXIMUM_STRICT"]["FEMALE_VISIBLE_HANDS"] is False
    assert constitution.data["ISRAILIYYAT_POLICY"]["ISRAILIYYAT_ALLOWED"] is True


def test_constitution_load_fails_closed_when_missing(tmp_path: Path) -> None:
    with pytest.raises(ConstitutionValidationError):
        load_visual_production_constitution_v2(tmp_path)


def test_constitution_required_before_storyboard_and_generation() -> None:
    constitution, storyboard, dossiers, audits = load_outputs()
    candidate = deepcopy(storyboard)
    candidate["VISUAL_CONSTITUTION_LOADED"] = False
    result = validate_micro_shot_storyboard(candidate, constitution, dossiers=dossiers, temporal_audits=audits)
    assert result["status"] == "FAIL"
    assert "VISUAL_CONSTITUTION_LOADED_MUST_BE_TRUE" in result["errors"]
    with pytest.raises(VisualPlanningValidationError):
        assert_visual_generation_gate(
            storyboard_status="AWAITING_HUMAN_APPROVAL",
            approved_storyboard_sha256=None,
            current_storyboard_sha256="current",
        )


def test_audio_is_duration_authority_and_microshots_cover_audio() -> None:
    constitution, storyboard, dossiers, audits = load_outputs()
    result = validate_micro_shot_storyboard(storyboard, constitution, dossiers=dossiers, temporal_audits=audits)
    assert result["status"] == "PASS"
    assert storyboard["AUDIO_IS_DURATION_AUTHORITY"] is True
    assert storyboard["CURRENT_NARRATION_FROZEN"] is True
    assert storyboard["MICRO_SHOTS"][-1]["TIMELINE_OUT"] == pytest.approx(storyboard["AUDIO_DURATION_SECONDS"], abs=0.002)


def test_approval_hash_invalidates_material_change() -> None:
    with pytest.raises(VisualPlanningValidationError):
        assert_visual_generation_gate(
            storyboard_status="APPROVED",
            approved_storyboard_sha256="old",
            current_storyboard_sha256="new",
        )
    assert_visual_generation_gate(
        storyboard_status="APPROVED",
        approved_storyboard_sha256="same",
        current_storyboard_sha256="same",
    ) is None


def test_literal_event_cannot_be_replaced_by_atmosphere() -> None:
    constitution, storyboard, dossiers, audits = load_outputs()
    candidate = deepcopy(storyboard)
    literal = next(item for item in candidate["MICRO_SHOTS"] if item["EVENT_ROLE"] == "LITERAL_EVENT")
    literal["VISIBLE_ACTION"] = ""
    literal["MUTE_COMPREHENSION_TARGET"] = ""
    result = validate_micro_shot_storyboard(candidate, constitution, dossiers=dossiers, temporal_audits=audits)
    assert result["status"] == "FAIL"
    assert any("LITERAL_CONTRACT_INCOMPLETE" in error for error in result["errors"])


def test_unseen_source_event_cannot_invent_visible_entity() -> None:
    constitution, storyboard, dossiers, audits = load_outputs()
    candidate = deepcopy(storyboard)
    unseen = next(item for item in candidate["MICRO_SHOTS"] if item["EVENT_TYPE"] == "SOURCE_CONSTRAINED_UNSEEN_EVENT")
    unseen["UNSEEN_ENTITY_VISIBLE"] = True
    result = validate_micro_shot_storyboard(candidate, constitution, dossiers=dossiers, temporal_audits=audits)
    assert result["status"] == "FAIL"
    assert any("UNSEEN_ENTITY_MUST_NOT_BE_VISIBLE" in error for error in result["errors"])


def test_named_character_requires_dossier_and_unknown_stays_unknown() -> None:
    constitution, storyboard, dossiers, audits = load_outputs()
    result = validate_micro_shot_storyboard(storyboard, constitution, dossiers=[], temporal_audits=audits)
    assert result["status"] == "FAIL"
    assert any("DOSSIER" in error for error in result["errors"])
    assert source_fact_art_direction_overlap(["complexion UNKNOWN"], ["earth-tone garment"]) == set()
    adam = next(item for item in dossiers if item["CHARACTER_ID"] == "ADAM")
    assert "complexion" in adam["UNKNOWN_ATTRIBUTES"]
    assert validate_character_dossier(adam) == []


def test_source_fact_and_art_direction_are_separate() -> None:
    _, _, dossiers, _ = load_outputs()
    assert validate_character_dossiers(dossiers)["status"] == "PASS"
    for dossier in dossiers:
        assert source_fact_art_direction_overlap(
            dossier["SOURCE_BACKED_ATTRIBUTES"], dossier["ART_DIRECTION_DECISIONS"]
        ) == set()


def test_source_hierarchy_and_israiliyyat_certainty_rules() -> None:
    assert validate_source_hierarchy_records(
        [
            {
                "SOURCE_TIER": "TIER_5_PERMISSIBLE_ISRAILIYYAT",
                "ASSERTION_MODE": "ATTRIBUTE_AND_QUALIFY",
                "SOURCE_LABEL": "lower-tier report",
                "CERTAINTY": "NON_AUTHORITATIVE",
                "ISRAILIYYAT_STATUS": "PERMISSIBLE_NON_CONFLICTING",
            }
        ]
    ) == []
    errors = validate_source_hierarchy_records(
        [
            {
                "SOURCE_TIER": "TIER_5_PERMISSIBLE_ISRAILIYYAT",
                "ASSERTION_MODE": "STATE_AS_FACT",
                "SOURCE_LABEL": "missing certainty boundary",
                "CERTAINTY": "HIGH",
                "ISRAILIYYAT_STATUS": "DISPUTED",
            }
        ]
    )
    assert "SOURCE_RECORD_0_LOWER_TIER_PRESENTED_AS_FACT" in errors


def test_strict_female_prompt_contract_is_compiled() -> None:
    constitution = load_visual_production_constitution_v2(REPO)
    compiled = compile_visual_prompt_v2(
        constitution,
        "Two people perform a literal action; the woman is fully covered.",
        "Show the literal action with the covered woman present.",
        "No exposed skin, no graphics.",
        includes_female=True,
        event_type="LITERAL_EVENT",
        source_tier="TIER_1_QURAN",
        source_certainty="HIGH",
        source_facts=["shared action"],
        art_direction=["covered rear framing"],
        dossier_refs=["ADAM", "HAWWA_SPOUSE"],
    )
    positive = compiled["COMPILED_PROVIDER_PROMPT"]["positive_video"]
    assert "FEMALE_MODESTY_MAXIMUM_STRICT=TRUE" in positive
    assert "FEMALE_VISIBLE_HANDS=FORBIDDEN" in positive
    assert "SOURCE_FACTS=shared action" in positive
    assert "ART_DIRECTION=covered rear framing" in positive


def test_prompt_contradictions_are_rejected() -> None:
    assert validate_prompt_contradictions("visible mouth", "all faces forbidden")
    assert validate_prompt_contradictions("literal eating action", "no graphics") == []


def test_graphics_are_forbidden_and_render_qa_is_not_run() -> None:
    constitution, storyboard, dossiers, audits = load_outputs()
    assert validate_constitution_mapping(constitution.data) == []
    assert storyboard["PLANNED_GRAPHICS_COUNT"] == 0
    assert storyboard["ACTUAL_RENDER_GRAPHICS_COUNT"] == 0
    assert storyboard["ACTUAL_RENDER_MUTE_COMPREHENSION"] == "NOT_RUN"
    assert storyboard["VISUAL_GENERATION_ALLOWED"] is False


def test_reuse_is_temporally_audited_not_midpoint_only() -> None:
    constitution, storyboard, dossiers, audits = load_outputs()
    assert all(validate_temporal_reuse_audit(item) == [] for item in audits.values())
    candidate = deepcopy(storyboard)
    reuse = next(item for item in candidate["MICRO_SHOTS"] if item["SOURCE"] != "NEW_GENERATION_REQUIRED")
    bad_audits = deepcopy(audits)
    bad_audits[reuse["ASSET_ID"]]["MIDPOINT_ONLY_ACCEPTANCE"] = True
    result = validate_micro_shot_storyboard(candidate, constitution, dossiers=dossiers, temporal_audits=bad_audits)
    assert result["status"] == "FAIL"
    assert any("MIDPOINT_ONLY_ACCEPTANCE_FORBIDDEN" in error for error in result["errors"])


def test_microshot_duration_is_independent_of_parent_audio_segment() -> None:
    _, storyboard, _, _ = load_outputs()
    new_shot = next(item for item in storyboard["MICRO_SHOTS"] if item["SOURCE"] == "NEW_GENERATION_REQUIRED")
    parent_duration = next(
        item["END_TIME"] - item["START_TIME"]
        for item in json.loads((REPO / "projects/episode-002-adam-temptation-fall-repentance/preproduction/EP002_SURGICAL_REPAIR_STORYBOARD_V1.json").read_text(encoding="utf-8"))["timeline_shots"]
        if item["SHOT_ID"] == new_shot["PARENT_AUDIO_SEGMENT_ID"]
    )
    assert new_shot["DURATION"] < parent_duration


def test_no_loop_stretch_or_excessive_consecutive_asset_reuse() -> None:
    _, storyboard, _, _ = load_outputs()
    reused = [item for item in storyboard["MICRO_SHOTS"] if item["SOURCE"] != "NEW_GENERATION_REQUIRED"]
    counts: dict[str, int] = {}
    previous: str | None = None
    for item in reused:
        assert item["PLAYBACK_RATE"] == 1.0
        assert item["NO_LOOP"] is True
        assert item["NO_STRETCH"] is True
        counts[item["ASSET_ID"]] = counts.get(item["ASSET_ID"], 0) + 1
        assert item["ASSET_ID"] != previous
        previous = item["ASSET_ID"]
    assert max(counts.values()) <= 3


def test_required_female_character_cannot_be_omitted() -> None:
    constitution, storyboard, dossiers, audits = load_outputs()
    candidate = deepcopy(storyboard)
    female_shot = next(item for item in candidate["MICRO_SHOTS"] if item.get("INCLUDES_FEMALE") is True)
    female_shot["CHARACTERS"] = ["ADAM"]
    result = validate_micro_shot_storyboard(candidate, constitution, dossiers=dossiers, temporal_audits=audits)
    assert result["status"] == "FAIL"
    assert any("REQUIRED_FEMALE_CHARACTER_OMITTED" in error for error in result["errors"])


def test_v2_artifact_reports_preproduction_only() -> None:
    report = json.loads(
        (REPO / "projects/episode-002-adam-temptation-fall-repentance/orchestration/ep002-surgical-visual-repair-preproduction-v2.json").read_text(encoding="utf-8")
    )
    assert report["STATUS"] == "PASS_EP002_SURGICAL_VISUAL_REPAIR_PREPRODUCTION_V2"
    assert report["NETWORK_CALLS"] == 0
    assert report["PROVIDER_CALLS"] == 0
    assert report["PAID_CALLS"] == 0
    assert report["NO_AUTHORIZATION_CREATED_OR_CONSUMED"] is True
    assert report["STORYBOARD_STATUS"] == "AWAITING_HUMAN_APPROVAL"
    assert report["APPROVED_STORYBOARD_SHA256"] is None
    assert report["VISUAL_GENERATION_ALLOWED"] is False
