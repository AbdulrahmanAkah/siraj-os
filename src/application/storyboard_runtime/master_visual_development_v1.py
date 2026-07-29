"""Build Adam's non-paid master-visual development package.

This stage develops a deterministic Visual Bible, Color Script, and text/shape
animatic plan from the human-approved storyboard master. It does not approve a
master visual identity and it never authorises paid, direct, live-provider, or
Runware execution.
"""
from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

TIMEZONE = "Asia/Baghdad"
VERSION = "1"
EPISODE_ID = "episode-001-adam"
SCRIPT_ID = "adam_prestige_cinematic_script_v2_1_ff540783ec519581"
SCRIPT_FINGERPRINT = (
    "ff540783ec519581bd902caf81145c3f77819a7351f2bd5d07e9f84705a4fb27"
)
STORYBOARD_ID = "adam_detailed_cinematic_storyboard_v2_1_867b88ade164ebe4"
STORYBOARD_FINGERPRINT = (
    "867b88ade164ebe444aeaaeeb9f60accef122f59cf8b45b020223f3ca8788bf8"
)
APPROVAL_ID = (
    "adam_final_storyboard_master_human_approval_v2_1_264f49c20f5c1500"
)
APPROVAL_BINDING_ID = (
    "adam_final_storyboard_master_approval_binding_v2_1_d7e21a0b1d9d0cff"
)
VISUAL_GATE_ID = "adam_non_paid_visual_development_gate_a1431674b6976d87"
SOURCE_STAGE = "MASTER_VISUAL_BIBLE_COLOR_SCRIPT_AND_NON_PAID_ANIMATIC_DEVELOPMENT"
NEXT_STAGE = (
    "HUMAN_REVIEW_OF_MASTER_VISUAL_BIBLE_COLOR_SCRIPT_AND_NON_PAID_ANIMATIC_V1"
)
DOWNSTREAM_REVIEW_DECISION_STAGE = (
    "HUMAN_DECISION_ON_MASTER_VISUAL_DEVELOPMENT_REVIEW_V1"
)
DOWNSTREAM_STYLE_FRAME_PROTOTYPE_STAGE = (
    "NON_PAID_MASTER_STYLE_FRAMES_AND_KEYFRAME_PROTOTYPING_V1"
)
ALLOWED_EPISODE_STAGES = (
    SOURCE_STAGE,
    NEXT_STAGE,
    DOWNSTREAM_REVIEW_DECISION_STAGE,
    DOWNSTREAM_STYLE_FRAME_PROTOTYPE_STAGE,
)
LIVE_EXECUTION = "BLOCKED"
PAID_EXECUTION = "BLOCKED"
DIRECT_EXECUTION = "BLOCKED"
RUNWARE_EXECUTION = "BLOCKED"
MASTER_VISUAL_APPROVAL = False
GENERATED_VIDEO_PLANNED_SECONDS = 0

SCHEMA_VISUAL_BIBLE = "siraj-master-visual-bible-v1"
SCHEMA_COLOR_SCRIPT = "siraj-color-script-v1"
SCHEMA_ANIMATIC = "siraj-non-paid-animatic-development-v1"
SCHEMA_AUDIT = "siraj-master-visual-development-audit-v1"
SCHEMA_BINDING = "siraj-master-visual-development-binding-v1"

ALLOWED_NON_PAID_STAGES = (
    "MASTER_VISUAL_BIBLE",
    "COLOR_SCRIPT",
    "NON_PAID_ANIMATIC",
    "SHOT_PACKAGE_PLANNING",
    "AUDIO_PREVIS",
)
FORBIDDEN_EXECUTION_MODES = (
    "LIVE_PROVIDER_EXECUTION",
    "PAID_EXECUTION",
    "DIRECT_PROVIDER_EXECUTION",
    "RUNWARE_EXECUTION",
)

MATERIAL_LANGUAGE = {
    "primordial_void": ["basalt", "cold silver", "suspended mineral dust"],
    "creation": ["earth", "clay", "rain", "amber moisture", "tactile macro texture"],
    "knowledge": ["disciplined pearl", "ink gold", "ordered shadow"],
    "pride_and_refusal": ["obsidian", "volcanic copper", "compressed darkness"],
    "human_covenant": ["human warmth", "covenantal blue", "restrained gold"],
    "paradise": ["emerald depth", "pearl atmosphere", "warning shadow"],
}

LIGHT_BEHAVIOURS = (
    "REVEAL",
    "BIND",
    "DIVIDE",
    "WITHDRAW",
)


class MasterVisualDevelopmentError(ValueError):
    """Raised when the approved source state or derived package is invalid."""


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MasterVisualDevelopmentError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise MasterVisualDevelopmentError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _unique(values: Iterable[object]) -> list[object]:
    seen: set[str] = set()
    result: list[object] = []
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise MasterVisualDevelopmentError(f"Expected mapping for {label}.")
    return value


def _require_shots(storyboard: Mapping[str, object]) -> list[Mapping[str, object]]:
    shots = storyboard.get("shots")
    if not isinstance(shots, list) or len(shots) != 70:
        raise MasterVisualDevelopmentError("Storyboard must contain exactly 70 shots.")
    if not all(isinstance(shot, Mapping) for shot in shots):
        raise MasterVisualDevelopmentError("Every storyboard shot must be an object.")
    return list(shots)  # type: ignore[arg-type]


def _group_sequences(
    shots: Sequence[Mapping[str, object]],
) -> list[tuple[str, list[Mapping[str, object]]]]:
    grouped: "OrderedDict[str, list[Mapping[str, object]]]" = OrderedDict()
    for shot in shots:
        sequence_id = shot.get("sequence_id")
        if not isinstance(sequence_id, str) or not sequence_id:
            raise MasterVisualDevelopmentError("Every shot needs a sequence_id.")
        grouped.setdefault(sequence_id, []).append(shot)
    if len(grouped) != 14:
        raise MasterVisualDevelopmentError("Storyboard must retain 14 sequences.")
    return list(grouped.items())


def _validate_execution_blocks(artifact: Mapping[str, object], label: str) -> None:
    expected = {
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    for key, value in expected.items():
        if artifact.get(key) != value:
            raise MasterVisualDevelopmentError(f"{label}: {key} must remain BLOCKED.")


def validate_inputs(
    *,
    storyboard: Mapping[str, object],
    approval: Mapping[str, object],
    approval_binding: Mapping[str, object],
    visual_gate: Mapping[str, object],
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
) -> None:
    if storyboard.get("episode_id") != EPISODE_ID:
        raise MasterVisualDevelopmentError("Unexpected episode id in storyboard.")
    if storyboard.get("script_id") != SCRIPT_ID:
        raise MasterVisualDevelopmentError("Unexpected storyboard script id.")
    if storyboard.get("script_fingerprint") != SCRIPT_FINGERPRINT:
        raise MasterVisualDevelopmentError("Unexpected storyboard script fingerprint.")
    if str(storyboard.get("director_cut_version")) != "2.1":
        raise MasterVisualDevelopmentError("Storyboard must be Director's Cut 2.1.")
    if storyboard.get("shot_count") != 70 or storyboard.get("sequence_count") != 14:
        raise MasterVisualDevelopmentError("Storyboard counts changed.")

    shots = _require_shots(storyboard)
    shot_ids = [shot.get("shot_id") for shot in shots]
    if len(set(shot_ids)) != 70 or any(not isinstance(value, str) for value in shot_ids):
        raise MasterVisualDevelopmentError("Storyboard shot ids must be 70 unique strings.")
    if sum(int(shot.get("duration_seconds", 0)) for shot in shots) != 1320:
        raise MasterVisualDevelopmentError("Storyboard duration must remain 1320 seconds.")
    if any(shot.get("provider_execution") != "BLOCKED" for shot in shots):
        raise MasterVisualDevelopmentError("Every storyboard shot must block execution.")
    _group_sequences(shots)

    if approval.get("approval_id") != APPROVAL_ID or approval.get("human_approval") is not True:
        raise MasterVisualDevelopmentError("Final storyboard human approval is not active.")
    if approval.get("script_fingerprint") != SCRIPT_FINGERPRINT:
        raise MasterVisualDevelopmentError("Approval script fingerprint changed.")
    if approval.get("storyboard_fingerprint") != STORYBOARD_FINGERPRINT:
        raise MasterVisualDevelopmentError("Approval storyboard fingerprint changed.")
    _validate_execution_blocks(approval, "approval")

    if approval_binding.get("binding_id") != APPROVAL_BINDING_ID:
        raise MasterVisualDevelopmentError("Unexpected storyboard approval binding.")
    if approval_binding.get("approval_id") != APPROVAL_ID:
        raise MasterVisualDevelopmentError("Approval binding does not bind approval.")
    if approval_binding.get("script_fingerprint") != SCRIPT_FINGERPRINT:
        raise MasterVisualDevelopmentError("Binding script fingerprint changed.")
    if approval_binding.get("storyboard_fingerprint") != STORYBOARD_FINGERPRINT:
        raise MasterVisualDevelopmentError("Binding storyboard fingerprint changed.")
    _validate_execution_blocks(approval_binding, "approval binding")

    if visual_gate.get("gate_id") != VISUAL_GATE_ID:
        raise MasterVisualDevelopmentError("Unexpected visual-development gate.")
    if visual_gate.get("source_binding_id") != APPROVAL_BINDING_ID:
        raise MasterVisualDevelopmentError("Visual gate is not bound to approval.")
    if visual_gate.get("status") != "OPEN_NON_PAID_VISUAL_DEVELOPMENT_ONLY":
        raise MasterVisualDevelopmentError("Non-paid visual-development gate is not open.")
    if visual_gate.get("allowed_non_paid_stages") != list(ALLOWED_NON_PAID_STAGES):
        raise MasterVisualDevelopmentError("Allowed non-paid stages changed.")
    if visual_gate.get("forbidden_execution_modes") != list(FORBIDDEN_EXECUTION_MODES):
        raise MasterVisualDevelopmentError("Forbidden execution modes changed.")
    if visual_gate.get("master_visual_approval") is not False:
        raise MasterVisualDevelopmentError("Master visual approval must remain false.")
    _validate_execution_blocks(visual_gate, "visual gate")

    script_definition = _require_mapping(
        episode_definition.get("cinematic_script"), "episode cinematic_script"
    )
    storyboard_definition = _require_mapping(
        episode_definition.get("detailed_storyboard"), "episode detailed_storyboard"
    )
    if script_definition.get("human_approval") is not True:
        raise MasterVisualDevelopmentError("Episode script approval is not active.")
    if storyboard_definition.get("human_approval") is not True:
        raise MasterVisualDevelopmentError("Episode storyboard approval is not active.")
    if script_definition.get("input_fingerprint") != SCRIPT_FINGERPRINT:
        raise MasterVisualDevelopmentError("Episode script fingerprint changed.")
    if storyboard_definition.get("input_fingerprint") != STORYBOARD_FINGERPRINT:
        raise MasterVisualDevelopmentError("Episode storyboard fingerprint changed.")
    if episode_definition.get("storyboard_completion_status") != "COMPLETE_HUMAN_APPROVED":
        raise MasterVisualDevelopmentError("Storyboard is not human approved.")
    if episode_definition.get("next_stage") not in ALLOWED_EPISODE_STAGES:
        raise MasterVisualDevelopmentError("Episode is not at an allowed visual-development state.")
    if episode_definition.get("live_execution_status") != LIVE_EXECUTION:
        raise MasterVisualDevelopmentError("Episode live execution must remain blocked.")
    if episode_definition.get("paid_execution") != PAID_EXECUTION:
        raise MasterVisualDevelopmentError("Episode paid execution must remain blocked.")

    if production_brief.get("brief_id") != (
        "adam_prestige_production_brief_v2_1_c8e7e9b9ccd7cadd"
    ):
        raise MasterVisualDevelopmentError("Unexpected production brief.")
    if production_brief.get("generated_video_planned_seconds") != 0:
        raise MasterVisualDevelopmentError("Generated-video allocation must remain zero.")
    if production_brief.get("live_provider_execution") != LIVE_EXECUTION:
        raise MasterVisualDevelopmentError("Brief live execution must remain blocked.")
    if production_brief.get("paid_execution") != PAID_EXECUTION:
        raise MasterVisualDevelopmentError("Brief paid execution must remain blocked.")


def build_master_visual_bible(
    storyboard: Mapping[str, object],
) -> dict:
    shots = _require_shots(storyboard)
    sequences = _group_sequences(shots)
    grammar = copy.deepcopy(dict(_require_mapping(
        storyboard.get("master_visual_grammar"), "master_visual_grammar"
    )))
    rules = copy.deepcopy(dict(_require_mapping(
        storyboard.get("master_visual_rules"), "master_visual_rules"
    )))

    sequence_profiles: list[dict] = []
    for sequence_id, sequence_shots in sequences:
        palette = _unique(
            shot.get("lighting_and_colour", "UNSPECIFIED") for shot in sequence_shots
        )
        profile = {
            "sequence_id": sequence_id,
            "shot_count": len(sequence_shots),
            "duration_seconds": sum(
                int(shot.get("duration_seconds", 0)) for shot in sequence_shots
            ),
            "palette_progression": palette,
            "treatments": _unique(
                shot.get("treatment", "UNSPECIFIED") for shot in sequence_shots
            ),
            "continuity_anchors": _unique(
                shot.get("continuity_anchor", "UNSPECIFIED") for shot in sequence_shots
            ),
            "camera_intents": _unique(
                shot.get("camera", "UNSPECIFIED") for shot in sequence_shots
            ),
            "dramatic_beats": [shot.get("dramatic_beat") for shot in sequence_shots],
            "religious_visual_safety": _unique(
                shot.get("religious_visual_safety", "UNSPECIFIED")
                for shot in sequence_shots
            ),
            "light_behaviour": LIGHT_BEHAVIOURS[(len(sequence_profiles)) % 4],
            "approval_status": "DEVELOPED_AWAITING_HUMAN_MASTER_VISUAL_APPROVAL",
        }
        sequence_profiles.append(profile)

    bible = {
        "schema_version": SCHEMA_VISUAL_BIBLE,
        "status": "DEVELOPED_AWAITING_HUMAN_MASTER_VISUAL_APPROVAL",
        "episode_id": EPISODE_ID,
        "canonical_timezone": TIMEZONE,
        "source_approval_id": APPROVAL_ID,
        "source_binding_id": APPROVAL_BINDING_ID,
        "source_visual_gate_id": VISUAL_GATE_ID,
        "script_id": SCRIPT_ID,
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_id": STORYBOARD_ID,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "format_identity": storyboard.get("format_identity"),
        "authorship_contract": grammar,
        "religious_visual_rules": rules,
        "material_language": MATERIAL_LANGUAGE,
        "sequence_profiles": sequence_profiles,
        "sequence_coverage": "14/14",
        "shot_coverage": "70/70",
        "master_visual_approval": MASTER_VISUAL_APPROVAL,
        "generated_video_planned_seconds": GENERATED_VIDEO_PLANNED_SECONDS,
        "provider_selection": "DEFERRED",
        "budget_allocation": "DEFERRED",
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    bible["visual_bible_id"] = (
        "adam_master_visual_bible_v1_" + canonical_sha256(bible)[:16]
    )
    return bible


def build_color_script(
    storyboard: Mapping[str, object],
    visual_bible: Mapping[str, object],
) -> dict:
    shots = _require_shots(storyboard)
    sequences = _group_sequences(shots)
    cards: list[dict] = []
    for index, (sequence_id, sequence_shots) in enumerate(sequences):
        colours = [
            str(shot.get("lighting_and_colour", "UNSPECIFIED"))
            for shot in sequence_shots
        ]
        midpoint = colours[len(colours) // 2]
        cards.append(
            {
                "sequence_id": sequence_id,
                "sequence_number": index + 1,
                "shot_count": len(sequence_shots),
                "duration_seconds": sum(
                    int(shot.get("duration_seconds", 0)) for shot in sequence_shots
                ),
                "entry_palette": colours[0],
                "midpoint_palette": midpoint,
                "exit_palette": colours[-1],
                "light_behaviour": LIGHT_BEHAVIOURS[index % 4],
                "dramatic_progression": [
                    shot.get("dramatic_stage") for shot in sequence_shots
                ],
                "emotional_progression": [
                    shot.get("entry_state") for shot in sequence_shots[:1]
                ]
                + [shot.get("exit_state") for shot in sequence_shots[-1:]],
                "continuity_handoff": sequence_shots[-1].get("transition_role"),
                "approval_status": "DEVELOPED_AWAITING_HUMAN_MASTER_VISUAL_APPROVAL",
            }
        )

    color_script = {
        "schema_version": SCHEMA_COLOR_SCRIPT,
        "status": "COMPLETE_NON_PAID_DEVELOPMENT_AWAITING_HUMAN_APPROVAL",
        "episode_id": EPISODE_ID,
        "source_visual_bible_id": visual_bible["visual_bible_id"],
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "sequence_cards": cards,
        "sequence_coverage": "14/14",
        "duration_seconds": sum(card["duration_seconds"] for card in cards),
        "master_visual_approval": MASTER_VISUAL_APPROVAL,
        "generated_video_planned_seconds": GENERATED_VIDEO_PLANNED_SECONDS,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    color_script["color_script_id"] = (
        "adam_color_script_v1_" + canonical_sha256(color_script)[:16]
    )
    return color_script


def build_non_paid_animatic(
    storyboard: Mapping[str, object],
    visual_bible: Mapping[str, object],
    color_script: Mapping[str, object],
) -> dict:
    shots = _require_shots(storyboard)
    plans: list[dict] = []
    for shot in shots:
        plans.append(
            {
                "shot_id": shot.get("shot_id"),
                "shot_number": shot.get("shot_number"),
                "sequence_id": shot.get("sequence_id"),
                "duration_seconds": shot.get("duration_seconds"),
                "composition": shot.get("composition"),
                "camera": shot.get("camera"),
                "screen_action": shot.get("screen_action"),
                "sound_detail": shot.get("sound_detail"),
                "cut_motivation": shot.get("cut_motivation"),
                "continuity_anchor": shot.get("continuity_anchor"),
                "religious_visual_safety": shot.get("religious_visual_safety"),
                "previs_mode": "TEXT_FRAME_AND_GEOMETRIC_BLOCKING_ONLY",
                "image_generation": "NOT_PERFORMED",
                "video_generation": "NOT_PERFORMED",
                "audio_generation": "NOT_PERFORMED",
                "provider_execution": "BLOCKED",
                "asset_status": "PLANNED_NON_PAID_NO_MEDIA_EXECUTION",
            }
        )

    animatic = {
        "schema_version": SCHEMA_ANIMATIC,
        "status": "PLANNED_NON_PAID_NO_MEDIA_EXECUTION",
        "episode_id": EPISODE_ID,
        "source_visual_bible_id": visual_bible["visual_bible_id"],
        "source_color_script_id": color_script["color_script_id"],
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "shot_plans": plans,
        "shot_coverage": "70/70",
        "sequence_coverage": "14/14",
        "duration_seconds": sum(int(plan["duration_seconds"]) for plan in plans),
        "audio_previs": {
            "status": "TEXTUAL_CUE_MAP_ONLY",
            "cue_coverage": "70/70",
            "generated_audio_seconds": 0,
        },
        "media_assets_created": 0,
        "master_visual_approval": MASTER_VISUAL_APPROVAL,
        "generated_video_planned_seconds": GENERATED_VIDEO_PLANNED_SECONDS,
        "provider_selection": "DEFERRED",
        "budget_allocation": "DEFERRED",
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    animatic["animatic_development_id"] = (
        "adam_non_paid_animatic_development_v1_"
        + canonical_sha256(animatic)[:16]
    )
    return animatic


def build_development_audit(
    *,
    visual_bible: Mapping[str, object],
    color_script: Mapping[str, object],
    animatic: Mapping[str, object],
) -> dict:
    audit = {
        "schema_version": SCHEMA_AUDIT,
        "status": "PASS_NON_PAID_VISUAL_DEVELOPMENT_PACKAGE",
        "episode_id": EPISODE_ID,
        "visual_bible_id": visual_bible["visual_bible_id"],
        "color_script_id": color_script["color_script_id"],
        "animatic_development_id": animatic["animatic_development_id"],
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "visual_bible_sequence_coverage": "14/14",
        "color_script_sequence_coverage": "14/14",
        "animatic_shot_coverage": "70/70",
        "duration_seconds": 1320,
        "media_assets_created": 0,
        "generated_video_planned_seconds": 0,
        "master_visual_approval": False,
        "unresolved_package_construction_decisions": 0,
        "human_master_visual_review_required": True,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    audit["audit_id"] = (
        "adam_master_visual_development_audit_v1_"
        + canonical_sha256(audit)[:16]
    )
    return audit


def build_development_binding(
    *,
    visual_bible: Mapping[str, object],
    color_script: Mapping[str, object],
    animatic: Mapping[str, object],
    audit: Mapping[str, object],
) -> dict:
    binding = {
        "schema_version": SCHEMA_BINDING,
        "status": "BOUND_NON_PAID_VISUAL_DEVELOPMENT_PACKAGE",
        "episode_id": EPISODE_ID,
        "source_storyboard_approval_binding_id": APPROVAL_BINDING_ID,
        "source_visual_gate_id": VISUAL_GATE_ID,
        "visual_bible_id": visual_bible["visual_bible_id"],
        "color_script_id": color_script["color_script_id"],
        "animatic_development_id": animatic["animatic_development_id"],
        "audit_id": audit["audit_id"],
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "next_stage": NEXT_STAGE,
        "master_visual_approval": False,
        "generated_video_planned_seconds": 0,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    binding["binding_id"] = (
        "adam_master_visual_development_binding_v1_"
        + canonical_sha256(binding)[:16]
    )
    return binding


def update_episode_definition(
    *,
    episode_definition: Mapping[str, object],
    visual_bible: Mapping[str, object],
    color_script: Mapping[str, object],
    animatic: Mapping[str, object],
    audit: Mapping[str, object],
    binding: Mapping[str, object],
) -> dict:
    definition = copy.deepcopy(dict(episode_definition))
    existing = definition.get("master_visual_development")
    if isinstance(existing, Mapping):
        existing_binding = existing.get("binding_id")
        if existing_binding not in (None, binding["binding_id"]):
            raise MasterVisualDevelopmentError(
                "Existing visual-development package binds different content."
            )

    definition["master_visual_development"] = {
        "status": "DEVELOPED_AWAITING_HUMAN_MASTER_VISUAL_APPROVAL",
        "visual_bible_path": "cinematic/master-visual-bible-v1.json",
        "visual_bible_id": visual_bible["visual_bible_id"],
        "color_script_path": "cinematic/color-script-v1.json",
        "color_script_id": color_script["color_script_id"],
        "animatic_path": "cinematic/non-paid-animatic-development-v1.json",
        "animatic_development_id": animatic["animatic_development_id"],
        "audit_path": "cinematic/master-visual-development-audit-v1.json",
        "audit_id": audit["audit_id"],
        "binding_path": "contracts/master-visual-development-binding-v1.json",
        "binding_id": binding["binding_id"],
        "master_visual_approval": False,
        "human_review_required": True,
    }
    definition["visual_development_gate_usage"] = {
        "gate_id": VISUAL_GATE_ID,
        "status": "CONSUMED_FOR_NON_PAID_DEVELOPMENT_WITHOUT_EXECUTION",
        "media_assets_created": 0,
        "generated_video_planned_seconds": 0,
    }
    human_review = definition.get("master_visual_human_review")
    human_approval = definition.get("master_visual_human_approval")
    downstream_review_active = (
        isinstance(human_review, Mapping)
        and human_review.get("status") == "READY_FOR_HUMAN_DECISION"
        and human_review.get("human_approval") is False
        and human_review.get("master_visual_approval") is False
        and definition.get("next_stage") == DOWNSTREAM_REVIEW_DECISION_STAGE
        and definition.get("master_visual_status")
        == "HUMAN_REVIEW_PACKAGE_READY_FINAL_APPROVAL_STILL_BLOCKED"
    )
    downstream_prototype_active = (
        isinstance(human_approval, Mapping)
        and human_approval.get("development_baseline_approval") is True
        and human_approval.get("master_visual_approval") is False
        and definition.get("next_stage") == DOWNSTREAM_STYLE_FRAME_PROTOTYPE_STAGE
        and definition.get("master_visual_approval") is False
    )
    if not (downstream_review_active or downstream_prototype_active):
        definition["master_visual_status"] = (
            "DEVELOPED_AWAITING_HUMAN_APPROVAL"
        )
        definition["next_stage"] = NEXT_STAGE
    definition["live_execution_status"] = LIVE_EXECUTION
    definition["paid_execution"] = PAID_EXECUTION
    return definition


def update_production_brief(
    *,
    production_brief: Mapping[str, object],
    visual_bible: Mapping[str, object],
    color_script: Mapping[str, object],
    animatic: Mapping[str, object],
    binding: Mapping[str, object],
) -> dict:
    brief = copy.deepcopy(dict(production_brief))
    downstream_review_active = (
        brief.get("master_visual_review_status") == "READY_FOR_HUMAN_DECISION"
        and brief.get("master_visual_status")
        == "HUMAN_REVIEW_PACKAGE_READY_FINAL_APPROVAL_STILL_BLOCKED"
        and brief.get("master_visual_approval") is False
        and brief.get("next_non_paid_stage") == DOWNSTREAM_REVIEW_DECISION_STAGE
        and brief.get("visual_development_binding_id") == binding["binding_id"]
        and brief.get("generated_video_planned_seconds") == 0
        and brief.get("live_provider_execution") == LIVE_EXECUTION
        and brief.get("paid_execution") == PAID_EXECUTION
        and brief.get("direct_execution") == DIRECT_EXECUTION
        and brief.get("runware_execution") == RUNWARE_EXECUTION
    )
    downstream_prototype_active = (
        brief.get("style_frame_prototyping_status")
        == "AUTHORISED_EIGHT_NON_PAID_ANCHOR_PROTOTYPES_ONLY"
        and brief.get("next_non_paid_stage") == DOWNSTREAM_STYLE_FRAME_PROTOTYPE_STAGE
        and brief.get("master_visual_approval") is False
        and brief.get("generated_video_planned_seconds") == 0
        and brief.get("live_provider_execution") == LIVE_EXECUTION
        and brief.get("paid_execution") == PAID_EXECUTION
        and brief.get("direct_execution") == DIRECT_EXECUTION
        and brief.get("runware_execution") == RUNWARE_EXECUTION
    )
    if downstream_review_active or downstream_prototype_active:
        return brief
    brief.update(
        {
            "status": "NON_PAID_VISUAL_DEVELOPMENT_COMPLETE_PROVIDER_EXECUTION_BLOCKED",
            "storyboard_master_status": "COMPLETE_HUMAN_APPROVED",
            "animatic_status": "NON_PAID_DEVELOPMENT_COMPLETE_AWAITING_HUMAN_MASTER_VISUAL_APPROVAL",
            "master_visual_status": "DEVELOPED_AWAITING_HUMAN_APPROVAL",
            "master_visual_approval": False,
            "next_non_paid_stage": NEXT_STAGE,
            "master_visual_bible_id": visual_bible["visual_bible_id"],
            "color_script_id": color_script["color_script_id"],
            "animatic_development_id": animatic["animatic_development_id"],
            "visual_development_binding_id": binding["binding_id"],
            "generated_video_planned_seconds": 0,
            "provider_selection": "DEFERRED",
            "budget_allocation": "DEFERRED",
            "live_provider_execution": LIVE_EXECUTION,
            "paid_execution": PAID_EXECUTION,
            "direct_execution": DIRECT_EXECUTION,
            "runware_execution": RUNWARE_EXECUTION,
        }
    )
    return brief


def validate_outputs(
    *,
    visual_bible: Mapping[str, object],
    color_script: Mapping[str, object],
    animatic: Mapping[str, object],
    audit: Mapping[str, object],
    binding: Mapping[str, object],
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
) -> None:
    if visual_bible.get("sequence_coverage") != "14/14":
        raise MasterVisualDevelopmentError("Visual Bible sequence coverage failed.")
    if visual_bible.get("shot_coverage") != "70/70":
        raise MasterVisualDevelopmentError("Visual Bible shot coverage failed.")
    if len(visual_bible.get("sequence_profiles", [])) != 14:
        raise MasterVisualDevelopmentError("Visual Bible must have 14 profiles.")
    if len(color_script.get("sequence_cards", [])) != 14:
        raise MasterVisualDevelopmentError("Color Script must have 14 cards.")
    if color_script.get("duration_seconds") != 1320:
        raise MasterVisualDevelopmentError("Color Script duration changed.")
    if len(animatic.get("shot_plans", [])) != 70:
        raise MasterVisualDevelopmentError("Animatic must have 70 shot plans.")
    if animatic.get("duration_seconds") != 1320:
        raise MasterVisualDevelopmentError("Animatic duration changed.")
    if animatic.get("media_assets_created") != 0:
        raise MasterVisualDevelopmentError("Animatic created media unexpectedly.")
    if audit.get("status") != "PASS_NON_PAID_VISUAL_DEVELOPMENT_PACKAGE":
        raise MasterVisualDevelopmentError("Development audit did not pass.")
    if binding.get("audit_id") != audit.get("audit_id"):
        raise MasterVisualDevelopmentError("Development binding does not bind audit.")
    if binding.get("next_stage") != NEXT_STAGE:
        raise MasterVisualDevelopmentError("Development binding next stage changed.")
    development = _require_mapping(
        episode_definition.get("master_visual_development"),
        "master_visual_development",
    )
    if development.get("binding_id") != binding.get("binding_id"):
        raise MasterVisualDevelopmentError("Episode does not bind visual package.")
    if episode_definition.get("next_stage") not in (
        NEXT_STAGE,
        DOWNSTREAM_REVIEW_DECISION_STAGE,
        DOWNSTREAM_STYLE_FRAME_PROTOTYPE_STAGE,
    ):
        raise MasterVisualDevelopmentError("Episode visual-review stage changed.")
    human_review = episode_definition.get("master_visual_human_review")
    downstream_review_active = (
        isinstance(human_review, Mapping)
        and human_review.get("status") == "READY_FOR_HUMAN_DECISION"
        and episode_definition.get("next_stage")
        == DOWNSTREAM_REVIEW_DECISION_STAGE
        and episode_definition.get("master_visual_status")
        == "HUMAN_REVIEW_PACKAGE_READY_FINAL_APPROVAL_STILL_BLOCKED"
    )
    human_approval = episode_definition.get("master_visual_human_approval")
    downstream_prototype_active = (
        isinstance(human_approval, Mapping)
        and human_approval.get("development_baseline_approval") is True
        and episode_definition.get("next_stage")
        == DOWNSTREAM_STYLE_FRAME_PROTOTYPE_STAGE
        and episode_definition.get("master_visual_approval") is False
    )
    if not (downstream_review_active or downstream_prototype_active) and episode_definition.get(
        "master_visual_status"
    ) != "DEVELOPED_AWAITING_HUMAN_APPROVAL":
        raise MasterVisualDevelopmentError("Master visual status changed.")
    if production_brief.get("visual_development_binding_id") != binding.get(
        "binding_id"
    ):
        raise MasterVisualDevelopmentError("Production brief does not bind package.")

    for label, artifact in (
        ("visual bible", visual_bible),
        ("color script", color_script),
        ("animatic", animatic),
        ("audit", audit),
        ("binding", binding),
        ("production brief", production_brief),
    ):
        if artifact.get("master_visual_approval", False) is not False:
            raise MasterVisualDevelopmentError(
                f"{label}: master visual approval must remain false."
            )
        if artifact.get("generated_video_planned_seconds", 0) != 0:
            raise MasterVisualDevelopmentError(
                f"{label}: generated video allocation must remain zero."
            )
        _validate_execution_blocks(artifact, label)

    if episode_definition.get("live_execution_status") != LIVE_EXECUTION:
        raise MasterVisualDevelopmentError("Episode live execution changed.")
    if episode_definition.get("paid_execution") != PAID_EXECUTION:
        raise MasterVisualDevelopmentError("Episode paid execution changed.")


def build_all(
    *,
    storyboard: Mapping[str, object],
    approval: Mapping[str, object],
    approval_binding: Mapping[str, object],
    visual_gate: Mapping[str, object],
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
) -> tuple[dict, dict, dict, dict, dict, dict, dict]:
    validate_inputs(
        storyboard=storyboard,
        approval=approval,
        approval_binding=approval_binding,
        visual_gate=visual_gate,
        episode_definition=episode_definition,
        production_brief=production_brief,
    )
    visual_bible = build_master_visual_bible(storyboard)
    color_script = build_color_script(storyboard, visual_bible)
    animatic = build_non_paid_animatic(storyboard, visual_bible, color_script)
    audit = build_development_audit(
        visual_bible=visual_bible,
        color_script=color_script,
        animatic=animatic,
    )
    binding = build_development_binding(
        visual_bible=visual_bible,
        color_script=color_script,
        animatic=animatic,
        audit=audit,
    )
    updated_definition = update_episode_definition(
        episode_definition=episode_definition,
        visual_bible=visual_bible,
        color_script=color_script,
        animatic=animatic,
        audit=audit,
        binding=binding,
    )
    updated_brief = update_production_brief(
        production_brief=production_brief,
        visual_bible=visual_bible,
        color_script=color_script,
        animatic=animatic,
        binding=binding,
    )
    validate_outputs(
        visual_bible=visual_bible,
        color_script=color_script,
        animatic=animatic,
        audit=audit,
        binding=binding,
        episode_definition=updated_definition,
        production_brief=updated_brief,
    )
    return (
        visual_bible,
        color_script,
        animatic,
        audit,
        binding,
        updated_definition,
        updated_brief,
    )


def write_outputs(
    *,
    output_root: Path,
    visual_bible: Mapping[str, object],
    color_script: Mapping[str, object],
    animatic: Mapping[str, object],
    audit: Mapping[str, object],
    binding: Mapping[str, object],
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "visual_bible": output_root / "master-visual-bible-v1.json",
        "color_script": output_root / "color-script-v1.json",
        "animatic": output_root / "non-paid-animatic-development-v1.json",
        "audit": output_root / "master-visual-development-audit-v1.json",
        "binding": output_root / "master-visual-development-binding-v1.json",
        "episode_definition": output_root / "episode-definition-v1.json",
        "production_brief": output_root / "prestige-production-brief-v2-1.json",
        "readme": output_root / "README.md",
    }
    for key, payload in (
        ("visual_bible", visual_bible),
        ("color_script", color_script),
        ("animatic", animatic),
        ("audit", audit),
        ("binding", binding),
        ("episode_definition", episode_definition),
        ("production_brief", production_brief),
    ):
        write_json(outputs[key], payload)
    outputs["readme"].write_text(
        "# Adam Master Visual Development v1\n\n"
        "This package contains the deterministic non-paid Visual Bible, Color "
        "Script, text/shape animatic plan, audit, and binding. It creates no "
        "media assets and does not approve the master visual identity. Paid, "
        "direct, live-provider, and Runware execution remain blocked.\n",
        encoding="utf-8",
        newline="\n",
    )
    archive = output_root.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(output_root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(output_root).as_posix())
    outputs["archive"] = archive
    return outputs
