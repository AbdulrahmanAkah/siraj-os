"""Prepare Adam's master-visual human-review and decision package.

This stage critically reviews the deterministic Visual Bible, Color Script, and
text/geometric animatic development package. It prepares a readable dossier, a
critical review, a non-paid style-frame prototype plan, and an immutable human
approval request. It does not grant human approval, does not approve the final
master visual identity, and performs no image, audio, video, paid, direct,
live-provider, or Runware execution.
"""
from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Mapping, Sequence

TIMEZONE = "Asia/Baghdad"
EPISODE_ID = "episode-001-adam"
SCRIPT_ID = "adam_prestige_cinematic_script_v2_1_ff540783ec519581"
SCRIPT_FINGERPRINT = (
    "ff540783ec519581bd902caf81145c3f77819a7351f2bd5d07e9f84705a4fb27"
)
STORYBOARD_ID = "adam_detailed_cinematic_storyboard_v2_1_867b88ade164ebe4"
STORYBOARD_FINGERPRINT = (
    "867b88ade164ebe444aeaaeeb9f60accef122f59cf8b45b020223f3ca8788bf8"
)
VISUAL_BIBLE_ID = "adam_master_visual_bible_v1_0790d2e2e5fed178"
COLOR_SCRIPT_ID = "adam_color_script_v1_fe7ad6202e323835"
ANIMATIC_DEVELOPMENT_ID = (
    "adam_non_paid_animatic_development_v1_df9bfe3614040947"
)
DEVELOPMENT_AUDIT_ID = (
    "adam_master_visual_development_audit_v1_7fefb6449a10cbe9"
)
DEVELOPMENT_BINDING_ID = (
    "adam_master_visual_development_binding_v1_aadea96d4b8935c5"
)
SOURCE_STAGE = (
    "HUMAN_REVIEW_OF_MASTER_VISUAL_BIBLE_COLOR_SCRIPT_AND_NON_PAID_ANIMATIC_V1"
)
NEXT_STAGE = "HUMAN_DECISION_ON_MASTER_VISUAL_DEVELOPMENT_REVIEW_V1"
APPROVED_NEXT_STAGE = "NON_PAID_MASTER_STYLE_FRAMES_AND_KEYFRAME_PROTOTYPING_V1"
LIVE_EXECUTION = "BLOCKED"
PAID_EXECUTION = "BLOCKED"
DIRECT_EXECUTION = "BLOCKED"
RUNWARE_EXECUTION = "BLOCKED"
MASTER_VISUAL_APPROVAL = False
GENERATED_VIDEO_PLANNED_SECONDS = 0
MEDIA_ASSETS_CREATED = 0

SCHEMA_DOSSIER = "siraj-master-visual-human-review-dossier-v1"
SCHEMA_CRITICAL_REVIEW = "siraj-master-visual-critical-review-v1"
SCHEMA_PROTOTYPE_PLAN = "siraj-master-style-frame-prototype-plan-v1"
SCHEMA_APPROVAL_REQUEST = "siraj-master-visual-human-approval-request-v1"
SCHEMA_REVIEW_BINDING = "siraj-master-visual-human-review-binding-v1"

EXACT_APPROVAL_PHRASE = (
    "أعتمد بشريًا حزمة مراجعة التطوير البصري غير المدفوع لحلقة آدم بإصدار 1 "
    "والمربوطة ببصمات النص والستوريبورد ومعرفات الحزمة المحددة، وأجيز "
    "الانتقال إلى بناء نماذج الإطارات البصرية الرئيسية والـKeyframes غير "
    "المدفوعة فقط، دون اعتماد الهوية البصرية الرئيسية النهائية ودون السماح "
    "بأي تشغيل مدفوع أو مباشر أو توليد فيديو"
)
EXACT_APPROVAL_PHRASE_SHA256 = hashlib.sha256(
    EXACT_APPROVAL_PHRASE.encode("utf-8")
).hexdigest()

ANCHOR_SHOT_IDS = (
    "ADAM-DC2-S01-SH01",
    "ADAM-DC2-S02-SH03",
    "ADAM-DC2-S05-SH03",
    "ADAM-DC2-S07-SH03",
    "ADAM-DC2-S09-SH03",
    "ADAM-DC2-S11-SH04",
    "ADAM-DC2-S13-SH03",
    "ADAM-DC2-S14-SH05",
)

DECISION_OPTIONS = (
    "APPROVE_DEVELOPMENT_BASELINE_FOR_NON_PAID_STYLE_FRAMES",
    "APPROVE_WITH_CORRECTIONS",
    "REJECT_AND_REVISE",
)


class MasterVisualHumanReviewError(ValueError):
    """Raised when review sources or derived outputs are inconsistent."""


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
        raise MasterVisualHumanReviewError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise MasterVisualHumanReviewError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise MasterVisualHumanReviewError(f"Expected mapping for {label}.")
    return value


def _require_list(value: object, label: str, expected: int) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or len(value) != expected:
        raise MasterVisualHumanReviewError(
            f"{label} must contain exactly {expected} entries."
        )
    if not all(isinstance(item, Mapping) for item in value):
        raise MasterVisualHumanReviewError(f"Every {label} entry must be an object.")
    return list(value)  # type: ignore[arg-type]


def _validate_execution_blocks(artifact: Mapping[str, object], label: str) -> None:
    for key, expected in (
        ("live_provider_execution", LIVE_EXECUTION),
        ("paid_execution", PAID_EXECUTION),
        ("direct_execution", DIRECT_EXECUTION),
        ("runware_execution", RUNWARE_EXECUTION),
    ):
        if artifact.get(key) != expected:
            raise MasterVisualHumanReviewError(
                f"{label}: {key} must remain BLOCKED."
            )


def validate_inputs(
    *,
    storyboard: Mapping[str, object],
    visual_bible: Mapping[str, object],
    color_script: Mapping[str, object],
    animatic: Mapping[str, object],
    development_audit: Mapping[str, object],
    development_binding: Mapping[str, object],
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
) -> None:
    if storyboard.get("storyboard_id") != STORYBOARD_ID:
        raise MasterVisualHumanReviewError("Unexpected storyboard id.")
    if storyboard.get("script_id") != SCRIPT_ID:
        raise MasterVisualHumanReviewError("Unexpected storyboard script id.")
    if storyboard.get("script_fingerprint") != SCRIPT_FINGERPRINT:
        raise MasterVisualHumanReviewError("Storyboard script fingerprint changed.")
    if storyboard.get("storyboard_fingerprint") != STORYBOARD_FINGERPRINT:
        raise MasterVisualHumanReviewError("Storyboard fingerprint changed.")
    shots = _require_list(storyboard.get("shots"), "storyboard shots", 70)
    if sum(int(item.get("duration_seconds", 0)) for item in shots) != 1320:
        raise MasterVisualHumanReviewError("Storyboard duration must remain 1320 seconds.")

    if visual_bible.get("visual_bible_id") != VISUAL_BIBLE_ID:
        raise MasterVisualHumanReviewError("Unexpected Visual Bible id.")
    if visual_bible.get("schema_version") != "siraj-master-visual-bible-v1":
        raise MasterVisualHumanReviewError("Unexpected Visual Bible schema.")
    if visual_bible.get("sequence_coverage") != "14/14":
        raise MasterVisualHumanReviewError("Visual Bible sequence coverage changed.")
    if visual_bible.get("shot_coverage") != "70/70":
        raise MasterVisualHumanReviewError("Visual Bible shot coverage changed.")
    _require_list(visual_bible.get("sequence_profiles"), "sequence profiles", 14)

    if color_script.get("color_script_id") != COLOR_SCRIPT_ID:
        raise MasterVisualHumanReviewError("Unexpected Color Script id.")
    if color_script.get("source_visual_bible_id") != VISUAL_BIBLE_ID:
        raise MasterVisualHumanReviewError("Color Script does not bind Visual Bible.")
    if color_script.get("duration_seconds") != 1320:
        raise MasterVisualHumanReviewError("Color Script duration changed.")
    _require_list(color_script.get("sequence_cards"), "color cards", 14)

    if animatic.get("animatic_development_id") != ANIMATIC_DEVELOPMENT_ID:
        raise MasterVisualHumanReviewError("Unexpected animatic-development id.")
    if animatic.get("source_visual_bible_id") != VISUAL_BIBLE_ID:
        raise MasterVisualHumanReviewError("Animatic does not bind Visual Bible.")
    if animatic.get("source_color_script_id") != COLOR_SCRIPT_ID:
        raise MasterVisualHumanReviewError("Animatic does not bind Color Script.")
    if animatic.get("duration_seconds") != 1320:
        raise MasterVisualHumanReviewError("Animatic duration changed.")
    if animatic.get("media_assets_created") != 0:
        raise MasterVisualHumanReviewError("Animatic unexpectedly contains media assets.")
    plans = _require_list(animatic.get("shot_plans"), "animatic shot plans", 70)
    if any(item.get("image_generation") != "NOT_PERFORMED" for item in plans):
        raise MasterVisualHumanReviewError("Image generation occurred before review.")
    if any(item.get("video_generation") != "NOT_PERFORMED" for item in plans):
        raise MasterVisualHumanReviewError("Video generation occurred before review.")

    if development_audit.get("audit_id") != DEVELOPMENT_AUDIT_ID:
        raise MasterVisualHumanReviewError("Unexpected development-audit id.")
    if development_audit.get("status") != "PASS_NON_PAID_VISUAL_DEVELOPMENT_PACKAGE":
        raise MasterVisualHumanReviewError("Development audit is not passing.")

    if development_binding.get("binding_id") != DEVELOPMENT_BINDING_ID:
        raise MasterVisualHumanReviewError("Unexpected development-binding id.")
    if development_binding.get("visual_bible_id") != VISUAL_BIBLE_ID:
        raise MasterVisualHumanReviewError("Binding Visual Bible id changed.")
    if development_binding.get("color_script_id") != COLOR_SCRIPT_ID:
        raise MasterVisualHumanReviewError("Binding Color Script id changed.")
    if development_binding.get("animatic_development_id") != ANIMATIC_DEVELOPMENT_ID:
        raise MasterVisualHumanReviewError("Binding animatic id changed.")
    if development_binding.get("audit_id") != DEVELOPMENT_AUDIT_ID:
        raise MasterVisualHumanReviewError("Binding audit id changed.")

    for label, artifact in (
        ("visual bible", visual_bible),
        ("color script", color_script),
        ("animatic", animatic),
        ("development audit", development_audit),
        ("development binding", development_binding),
    ):
        if artifact.get("master_visual_approval") is not False:
            raise MasterVisualHumanReviewError(
                f"{label}: final master visual approval must remain false."
            )
        if artifact.get("generated_video_planned_seconds") != 0:
            raise MasterVisualHumanReviewError(
                f"{label}: generated-video allocation must remain zero."
            )
        _validate_execution_blocks(artifact, label)

    development = _require_mapping(
        episode_definition.get("master_visual_development"),
        "master_visual_development",
    )
    if development.get("binding_id") != DEVELOPMENT_BINDING_ID:
        raise MasterVisualHumanReviewError("Episode does not bind the development package.")
    if episode_definition.get("next_stage") not in (SOURCE_STAGE, NEXT_STAGE):
        raise MasterVisualHumanReviewError("Episode is not in the human-review state.")
    if episode_definition.get("storyboard_completion_status") != "COMPLETE_HUMAN_APPROVED":
        raise MasterVisualHumanReviewError("Storyboard approval is no longer active.")
    if episode_definition.get("live_execution_status") != LIVE_EXECUTION:
        raise MasterVisualHumanReviewError("Episode live execution changed.")
    if episode_definition.get("paid_execution") != PAID_EXECUTION:
        raise MasterVisualHumanReviewError("Episode paid execution changed.")

    if production_brief.get("brief_id") != (
        "adam_prestige_production_brief_v2_1_c8e7e9b9ccd7cadd"
    ):
        raise MasterVisualHumanReviewError("Unexpected production brief.")
    if production_brief.get("visual_development_binding_id") != DEVELOPMENT_BINDING_ID:
        raise MasterVisualHumanReviewError("Production brief does not bind development.")
    if production_brief.get("generated_video_planned_seconds") != 0:
        raise MasterVisualHumanReviewError("Production brief allocated generated video.")
    _validate_execution_blocks(production_brief, "production brief")


def build_review_dossier(
    *,
    visual_bible: Mapping[str, object],
    color_script: Mapping[str, object],
    animatic: Mapping[str, object],
) -> dict:
    profiles = _require_list(
        visual_bible.get("sequence_profiles"), "sequence profiles", 14
    )
    cards = _require_list(color_script.get("sequence_cards"), "color cards", 14)
    plans = _require_list(animatic.get("shot_plans"), "animatic shot plans", 70)
    sequence_cards: list[dict] = []
    for profile, card in zip(profiles, cards, strict=True):
        if profile.get("sequence_id") != card.get("sequence_id"):
            raise MasterVisualHumanReviewError("Visual and colour sequence order differs.")
        sequence_cards.append(
            {
                "sequence_id": profile["sequence_id"],
                "duration_seconds": card["duration_seconds"],
                "shot_count": card["shot_count"],
                "palette_progression": copy.deepcopy(profile["palette_progression"]),
                "entry_palette": card["entry_palette"],
                "midpoint_palette": card["midpoint_palette"],
                "exit_palette": card["exit_palette"],
                "light_behaviour": profile["light_behaviour"],
                "treatments": copy.deepcopy(profile["treatments"]),
                "continuity_anchors": copy.deepcopy(profile["continuity_anchors"]),
                "dramatic_beats": copy.deepcopy(profile["dramatic_beats"]),
                "religious_visual_safety": copy.deepcopy(
                    profile["religious_visual_safety"]
                ),
                "review_status": "PASS_AS_TEXTUAL_DEVELOPMENT_BASELINE",
                "mandatory_visual_validation": [
                    "STYLE_FRAME_LIGHT_AND_MATERIAL_PROOF",
                    "PALETTE_CALIBRATION_PROOF",
                    "RELIGIOUS_SAFETY_RENDER_PROOF",
                ],
            }
        )

    shot_index = [
        {
            "shot_id": plan["shot_id"],
            "sequence_id": plan["sequence_id"],
            "duration_seconds": plan["duration_seconds"],
            "previs_mode": plan["previs_mode"],
            "religious_visual_safety": plan["religious_visual_safety"],
            "review_status": "COVERED_TEXT_ONLY_VISUAL_PROOF_PENDING",
        }
        for plan in plans
    ]

    dossier = {
        "schema_version": SCHEMA_DOSSIER,
        "status": "READY_FOR_HUMAN_DECISION_ON_DEVELOPMENT_BASELINE",
        "episode_id": EPISODE_ID,
        "canonical_timezone": TIMEZONE,
        "source_development_binding_id": DEVELOPMENT_BINDING_ID,
        "visual_bible_id": VISUAL_BIBLE_ID,
        "color_script_id": COLOR_SCRIPT_ID,
        "animatic_development_id": ANIMATIC_DEVELOPMENT_ID,
        "development_audit_id": DEVELOPMENT_AUDIT_ID,
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "executive_verdict": {
            "development_baseline_approval_eligible": True,
            "non_paid_style_frame_prototyping_recommended": True,
            "final_master_visual_approval_eligible": False,
            "reason": (
                "The visual grammar is coherent and fully mapped, but no rendered "
                "style frames, calibrated visual swatches, or timed media animatic "
                "exist yet."
            ),
        },
        "review_dimensions": [
            {
                "dimension": "AUTHORSHIP_AND_VISUAL_GRAMMAR",
                "status": "PASS_DEVELOPMENT_BASELINE",
            },
            {
                "dimension": "RELIGIOUS_VISUAL_SAFETY",
                "status": "PASS_RULESET_VISUAL_OUTPUT_VALIDATION_REQUIRED",
            },
            {
                "dimension": "COLOR_AND_LIGHT_ARC",
                "status": "PASS_TEXTUAL_SCRIPT_CALIBRATED_SWATCHES_PENDING",
            },
            {
                "dimension": "CAMERA_LENS_AND_CONTINUITY",
                "status": "PASS_DEVELOPMENT_BASELINE",
            },
            {
                "dimension": "ANIMATIC_TIMING_AND_MOTION",
                "status": "PASS_TEXT_PLAN_TIMED_MEDIA_PENDING",
            },
            {
                "dimension": "FINAL_MASTER_VISUAL_IDENTITY",
                "status": "BLOCKED_UNTIL_STYLE_FRAME_PROOF",
            },
        ],
        "sequence_review_cards": sequence_cards,
        "sequence_coverage": "14/14",
        "shot_review_index": shot_index,
        "shot_coverage": "70/70",
        "duration_seconds": 1320,
        "decision_options": list(DECISION_OPTIONS),
        "master_visual_approval": False,
        "media_assets_created": 0,
        "generated_video_planned_seconds": 0,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    dossier["review_dossier_id"] = (
        "adam_master_visual_human_review_dossier_v1_"
        + canonical_sha256(dossier)[:16]
    )
    return dossier


def build_critical_review(dossier: Mapping[str, object]) -> dict:
    findings = [
        {
            "finding_id": "MVHR-001",
            "area": "STYLE_FRAME_PROOF",
            "severity": "BLOCKING_FINAL_MASTER_VISUAL_APPROVAL",
            "status": "OPEN_BY_DESIGN",
            "finding": "No rendered master style frames exist.",
            "required_action": "Produce the approved non-paid anchor style frames.",
        },
        {
            "finding_id": "MVHR-002",
            "area": "COLOR_CALIBRATION",
            "severity": "BLOCKING_FINAL_MASTER_VISUAL_APPROVAL",
            "status": "OPEN_BY_DESIGN",
            "finding": "The Color Script is descriptive text rather than calibrated swatches.",
            "required_action": "Lock swatches, value hierarchy, contrast, and colour continuity in style-frame proofs.",
        },
        {
            "finding_id": "MVHR-003",
            "area": "ANIMATIC_MEDIA_TIMING",
            "severity": "BLOCKING_FINAL_MASTER_VISUAL_APPROVAL",
            "status": "OPEN_BY_DESIGN",
            "finding": "The animatic is a 70-shot text/geometric plan, not timed media.",
            "required_action": "Build a non-paid visual timing prototype only after human approval.",
        },
        {
            "finding_id": "MVHR-004",
            "area": "ASSET_IDENTITY_REGISTRY",
            "severity": "MANDATORY_STYLE_FRAME_STAGE_ACTION",
            "status": "OPEN_BY_DESIGN",
            "finding": "Environment, material, title, and recurring motif identities are not yet locked through visual specimens.",
            "required_action": "Create a cross-shot identity registry from the selected anchor frames.",
        },
        {
            "finding_id": "MVHR-005",
            "area": "TYPOGRAPHY_AND_TITLE_SYSTEM",
            "severity": "MANDATORY_STYLE_FRAME_STAGE_ACTION",
            "status": "OPEN_BY_DESIGN",
            "finding": "Title typography and evidence-plate behaviour are described but not visually proven.",
            "required_action": "Prototype the Siraj and episode-title treatments without expository plate aesthetics.",
        },
        {
            "finding_id": "MVHR-006",
            "area": "RELIGIOUS_VISUAL_SAFETY",
            "severity": "VALIDATION_REQUIRED_NOT_A_RULESET_FAILURE",
            "status": "PASS_RULESET",
            "finding": "The written safety rules are strong; generated or illustrated outputs must still be inspected frame by frame.",
            "required_action": "Apply human religious-safety review to every prototype image before reuse.",
        },
    ]
    critical = {
        "schema_version": SCHEMA_CRITICAL_REVIEW,
        "status": "PASS_REVIEW_READY_WITH_FINAL_APPROVAL_BLOCKERS",
        "episode_id": EPISODE_ID,
        "review_dossier_id": dossier["review_dossier_id"],
        "source_development_binding_id": DEVELOPMENT_BINDING_ID,
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "findings": findings,
        "finding_count": len(findings),
        "development_baseline_blocker_count": 0,
        "final_master_visual_approval_blocker_count": 3,
        "mandatory_style_frame_action_count": 2,
        "religious_rule_failure_count": 0,
        "unresolved_technical_package_decisions": 0,
        "unresolved_human_decisions": 1,
        "recommendation": (
            "APPROVE_DEVELOPMENT_BASELINE_FOR_NON_PAID_STYLE_FRAME_PROTOTYPING"
        ),
        "final_master_visual_approval_eligible": False,
        "master_visual_approval": False,
        "media_assets_created": 0,
        "generated_video_planned_seconds": 0,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    critical["critical_review_id"] = (
        "adam_master_visual_critical_review_v1_"
        + canonical_sha256(critical)[:16]
    )
    return critical


def build_style_frame_prototype_plan(
    *,
    storyboard: Mapping[str, object],
    dossier: Mapping[str, object],
    critical_review: Mapping[str, object],
) -> dict:
    shots = _require_list(storyboard.get("shots"), "storyboard shots", 70)
    by_id = {str(shot.get("shot_id")): shot for shot in shots}
    missing = [shot_id for shot_id in ANCHOR_SHOT_IDS if shot_id not in by_id]
    if missing:
        raise MasterVisualHumanReviewError(f"Missing anchor shots: {missing}")
    prototypes: list[dict] = []
    for index, shot_id in enumerate(ANCHOR_SHOT_IDS, start=1):
        shot = by_id[shot_id]
        prototypes.append(
            {
                "prototype_number": index,
                "shot_id": shot_id,
                "sequence_id": shot.get("sequence_id"),
                "duration_reference_seconds": shot.get("duration_seconds"),
                "dramatic_beat": shot.get("dramatic_beat"),
                "composition": shot.get("composition"),
                "camera": shot.get("camera"),
                "lighting_and_colour": shot.get("lighting_and_colour"),
                "treatment": shot.get("treatment"),
                "screen_action": shot.get("screen_action"),
                "religious_visual_safety": shot.get("religious_visual_safety"),
                "prototype_purpose": (
                    "Prove composition, material language, light behaviour, colour "
                    "hierarchy, continuity, and religious-safety interpretation."
                ),
                "required_human_checks": [
                    "AUTHORSHIP_NOT_GENERIC_AI_FANTASY",
                    "MATERIAL_AND_LIGHT_COHERENCE",
                    "PALETTE_AND_VALUE_HIERARCHY",
                    "RELIGIOUS_VISUAL_SAFETY",
                    "CROSS_SHOT_IDENTITY_CONTINUITY",
                ],
                "image_generation_authorisation": "PENDING_HUMAN_APPROVAL",
                "video_generation": "BLOCKED",
                "provider_execution": "BLOCKED",
            }
        )
    plan = {
        "schema_version": SCHEMA_PROTOTYPE_PLAN,
        "status": "PLANNED_AWAITING_HUMAN_DEVELOPMENT_BASELINE_APPROVAL",
        "episode_id": EPISODE_ID,
        "review_dossier_id": dossier["review_dossier_id"],
        "critical_review_id": critical_review["critical_review_id"],
        "source_development_binding_id": DEVELOPMENT_BINDING_ID,
        "prototype_scope": "EIGHT_NON_PAID_MASTER_STYLE_FRAMES_AND_KEYFRAMES",
        "prototype_count": len(prototypes),
        "anchor_shot_ids": list(ANCHOR_SHOT_IDS),
        "prototypes": prototypes,
        "image_generation_authorisation": "PENDING_HUMAN_APPROVAL",
        "audio_generation": "BLOCKED",
        "video_generation": "BLOCKED",
        "final_master_visual_approval": False,
        "master_visual_approval": False,
        "media_assets_created": 0,
        "generated_video_planned_seconds": 0,
        "provider_selection": "DEFERRED",
        "budget_allocation": "DEFERRED",
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    plan["prototype_plan_id"] = (
        "adam_master_style_frame_prototype_plan_v1_"
        + canonical_sha256(plan)[:16]
    )
    return plan


def build_human_approval_request(
    *,
    dossier: Mapping[str, object],
    critical_review: Mapping[str, object],
    prototype_plan: Mapping[str, object],
) -> dict:
    request = {
        "schema_version": SCHEMA_APPROVAL_REQUEST,
        "status": "HUMAN_DECISION_REQUIRED",
        "episode_id": EPISODE_ID,
        "source_development_binding_id": DEVELOPMENT_BINDING_ID,
        "review_dossier_id": dossier["review_dossier_id"],
        "critical_review_id": critical_review["critical_review_id"],
        "prototype_plan_id": prototype_plan["prototype_plan_id"],
        "visual_bible_id": VISUAL_BIBLE_ID,
        "color_script_id": COLOR_SCRIPT_ID,
        "animatic_development_id": ANIMATIC_DEVELOPMENT_ID,
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "decision_options": list(DECISION_OPTIONS),
        "recommended_decision": (
            "APPROVE_DEVELOPMENT_BASELINE_FOR_NON_PAID_STYLE_FRAMES"
        ),
        "exact_approval_phrase": EXACT_APPROVAL_PHRASE,
        "exact_approval_phrase_sha256": EXACT_APPROVAL_PHRASE_SHA256,
        "approval_scope": {
            "development_baseline": "APPROVE_IF_HUMAN_ACCEPTS",
            "non_paid_style_frame_prototyping": "ALLOW_AFTER_EXACT_HUMAN_APPROVAL",
            "final_master_visual_identity": "NOT_APPROVED",
            "timed_video_animatic": "NOT_APPROVED",
            "paid_execution": "BLOCKED",
            "direct_execution": "BLOCKED",
            "live_provider_execution": "BLOCKED",
            "runware_execution": "BLOCKED",
        },
        "approval_effect_next_stage": APPROVED_NEXT_STAGE,
        "human_approval": False,
        "human_decision": "PENDING",
        "master_visual_approval": False,
        "media_assets_created": 0,
        "generated_video_planned_seconds": 0,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    request["request_id"] = (
        "adam_master_visual_human_approval_request_v1_"
        + canonical_sha256(request)[:16]
    )
    return request


def build_review_binding(
    *,
    dossier: Mapping[str, object],
    critical_review: Mapping[str, object],
    prototype_plan: Mapping[str, object],
    approval_request: Mapping[str, object],
) -> dict:
    binding = {
        "schema_version": SCHEMA_REVIEW_BINDING,
        "status": "BOUND_HUMAN_REVIEW_PACKAGE_AWAITING_HUMAN_DECISION",
        "episode_id": EPISODE_ID,
        "source_development_binding_id": DEVELOPMENT_BINDING_ID,
        "review_dossier_id": dossier["review_dossier_id"],
        "critical_review_id": critical_review["critical_review_id"],
        "prototype_plan_id": prototype_plan["prototype_plan_id"],
        "approval_request_id": approval_request["request_id"],
        "approval_phrase_sha256": EXACT_APPROVAL_PHRASE_SHA256,
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "next_stage": NEXT_STAGE,
        "approved_next_stage": APPROVED_NEXT_STAGE,
        "human_approval": False,
        "master_visual_approval": False,
        "media_assets_created": 0,
        "generated_video_planned_seconds": 0,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    binding["review_binding_id"] = (
        "adam_master_visual_human_review_binding_v1_"
        + canonical_sha256(binding)[:16]
    )
    return binding


def update_episode_definition(
    *,
    episode_definition: Mapping[str, object],
    dossier: Mapping[str, object],
    critical_review: Mapping[str, object],
    prototype_plan: Mapping[str, object],
    approval_request: Mapping[str, object],
    review_binding: Mapping[str, object],
) -> dict:
    definition = copy.deepcopy(dict(episode_definition))
    existing = definition.get("master_visual_human_review")
    if isinstance(existing, Mapping):
        existing_binding = existing.get("review_binding_id")
        if existing_binding not in (None, review_binding["review_binding_id"]):
            raise MasterVisualHumanReviewError(
                "Existing human-review package binds different content."
            )
    definition["master_visual_human_review"] = {
        "status": "READY_FOR_HUMAN_DECISION",
        "review_dossier_path": "cinematic/master-visual-human-review-dossier-v1.json",
        "review_dossier_id": dossier["review_dossier_id"],
        "critical_review_path": "cinematic/master-visual-critical-review-v1.json",
        "critical_review_id": critical_review["critical_review_id"],
        "readable_review_path": "cinematic/master-visual-human-review-v1.md",
        "prototype_plan_path": "cinematic/master-style-frame-prototype-plan-v1.json",
        "prototype_plan_id": prototype_plan["prototype_plan_id"],
        "approval_request_path": "evidence/master-visual-human-approval-request-v1.json",
        "approval_request_id": approval_request["request_id"],
        "review_binding_path": "contracts/master-visual-human-review-binding-v1.json",
        "review_binding_id": review_binding["review_binding_id"],
        "recommended_decision": approval_request["recommended_decision"],
        "human_approval": False,
        "human_decision": "PENDING",
        "final_master_visual_approval_eligible": False,
        "master_visual_approval": False,
    }
    definition["master_style_frame_prototype_plan"] = {
        "status": "PLANNED_AWAITING_HUMAN_DEVELOPMENT_BASELINE_APPROVAL",
        "path": "cinematic/master-style-frame-prototype-plan-v1.json",
        "prototype_plan_id": prototype_plan["prototype_plan_id"],
        "prototype_count": prototype_plan["prototype_count"],
        "image_generation_authorisation": "PENDING_HUMAN_APPROVAL",
    }
    definition["master_visual_status"] = (
        "HUMAN_REVIEW_PACKAGE_READY_FINAL_APPROVAL_STILL_BLOCKED"
    )
    definition["master_visual_approval"] = False
    definition["next_stage"] = NEXT_STAGE
    definition["religious_sensitivity"] = (
        "FINAL_SCRIPT_V2_1_HUMAN_APPROVED; VISUAL_DEVELOPMENT_REVIEW_READY; "
        "FINAL_MASTER_VISUAL_REMAINS_HUMAN_REVIEW_REQUIRED"
    )
    definition["live_execution_status"] = LIVE_EXECUTION
    definition["paid_execution"] = PAID_EXECUTION
    return definition


def update_production_brief(
    *,
    production_brief: Mapping[str, object],
    dossier: Mapping[str, object],
    critical_review: Mapping[str, object],
    prototype_plan: Mapping[str, object],
    approval_request: Mapping[str, object],
    review_binding: Mapping[str, object],
) -> dict:
    brief = copy.deepcopy(dict(production_brief))
    brief.update(
        {
            "status": "MASTER_VISUAL_HUMAN_REVIEW_READY_PROVIDER_EXECUTION_BLOCKED",
            "master_visual_review_status": "READY_FOR_HUMAN_DECISION",
            "master_visual_status": (
                "HUMAN_REVIEW_PACKAGE_READY_FINAL_APPROVAL_STILL_BLOCKED"
            ),
            "master_visual_approval": False,
            "master_visual_review_dossier_id": dossier["review_dossier_id"],
            "master_visual_critical_review_id": critical_review["critical_review_id"],
            "master_style_frame_prototype_plan_id": prototype_plan["prototype_plan_id"],
            "master_visual_human_approval_request_id": approval_request["request_id"],
            "master_visual_human_review_binding_id": review_binding["review_binding_id"],
            "style_frame_prototyping_status": "PENDING_HUMAN_BASELINE_APPROVAL",
            "next_non_paid_stage": NEXT_STAGE,
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


def render_review_markdown(
    *,
    dossier: Mapping[str, object],
    critical_review: Mapping[str, object],
    prototype_plan: Mapping[str, object],
    approval_request: Mapping[str, object],
) -> str:
    verdict = _require_mapping(dossier.get("executive_verdict"), "executive verdict")
    lines = [
        "# مراجعة الهوية البصرية — حلقة آدم — الإصدار 1",
        "",
        "## الحكم التنفيذي",
        "",
        "الحزمة الحالية متماسكة بوصفها خط أساس للتطوير البصري، ويمكن عرضها "
        "للقرار البشري بشأن الانتقال إلى نماذج Style Frames وKeyframes غير "
        "مدفوعة.",
        "",
        "لا يجوز اعتبارها اعتمادًا نهائيًا للهوية البصرية؛ لا توجد حتى الآن "
        "إطارات بصرية منفذة، ولا Color Swatches معايرة، ولا Animatic مرئي موقّت.",
        "",
        f"- أهلية اعتماد خط الأساس: {verdict['development_baseline_approval_eligible']}",
        f"- أهلية الاعتماد البصري النهائي: {verdict['final_master_visual_approval_eligible']}",
        f"- عدد التسلسلات: {dossier['sequence_coverage']}",
        f"- عدد اللقطات: {dossier['shot_coverage']}",
        f"- المدة: {dossier['duration_seconds']} ثانية",
        "",
        "## النتائج النقدية",
        "",
    ]
    for finding in critical_review["findings"]:
        lines.extend(
            [
                f"### {finding['finding_id']} — {finding['area']}",
                "",
                f"- الشدة: {finding['severity']}",
                f"- النتيجة: {finding['finding']}",
                f"- الإجراء: {finding['required_action']}",
                "",
            ]
        )
    lines.extend(
        [
            "## خطة النماذج المرجعية",
            "",
            f"سيُبنى بعد الاعتماد البشري {prototype_plan['prototype_count']} نماذج غير مدفوعة فقط:",
            "",
        ]
    )
    for item in prototype_plan["prototypes"]:
        lines.append(
            f"- {item['prototype_number']:02d}. {item['shot_id']} — "
            f"{item['sequence_id']} — {item['treatment']}"
        )
    lines.extend(
        [
            "",
            "## القرار المطلوب",
            "",
            "القرار الموصى به:",
            "",
            f"`{approval_request['recommended_decision']}`",
            "",
            "عبارة الاعتماد الدقيقة:",
            "",
            f"> {approval_request['exact_approval_phrase']}",
            "",
            f"SHA-256: `{approval_request['exact_approval_phrase_sha256']}`",
            "",
            "هذا الاعتماد — عند صدوره — يسمح فقط بالنماذج البصرية غير المدفوعة. "
            "ولا يعتمد الهوية البصرية النهائية، ولا يسمح بفيديو أو تشغيل مدفوع أو مباشر.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def validate_outputs(
    *,
    dossier: Mapping[str, object],
    critical_review: Mapping[str, object],
    prototype_plan: Mapping[str, object],
    approval_request: Mapping[str, object],
    review_binding: Mapping[str, object],
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
    markdown: str,
) -> None:
    if dossier.get("sequence_coverage") != "14/14":
        raise MasterVisualHumanReviewError("Review dossier sequence coverage failed.")
    if dossier.get("shot_coverage") != "70/70":
        raise MasterVisualHumanReviewError("Review dossier shot coverage failed.")
    if len(dossier.get("sequence_review_cards", [])) != 14:
        raise MasterVisualHumanReviewError("Review dossier requires 14 sequence cards.")
    if len(dossier.get("shot_review_index", [])) != 70:
        raise MasterVisualHumanReviewError("Review dossier requires 70 shot entries.")
    if critical_review.get("development_baseline_blocker_count") != 0:
        raise MasterVisualHumanReviewError("Development baseline has unexpected blockers.")
    if critical_review.get("final_master_visual_approval_eligible") is not False:
        raise MasterVisualHumanReviewError("Final visual approval was opened prematurely.")
    if prototype_plan.get("prototype_count") != 8:
        raise MasterVisualHumanReviewError("Exactly eight anchor prototypes are required.")
    if prototype_plan.get("anchor_shot_ids") != list(ANCHOR_SHOT_IDS):
        raise MasterVisualHumanReviewError("Anchor-shot selection changed.")
    if approval_request.get("human_approval") is not False:
        raise MasterVisualHumanReviewError("Human approval cannot be automatic.")
    if approval_request.get("exact_approval_phrase") != EXACT_APPROVAL_PHRASE:
        raise MasterVisualHumanReviewError("Exact approval phrase changed.")
    if approval_request.get("exact_approval_phrase_sha256") != EXACT_APPROVAL_PHRASE_SHA256:
        raise MasterVisualHumanReviewError("Approval phrase hash changed.")
    if review_binding.get("approval_request_id") != approval_request.get("request_id"):
        raise MasterVisualHumanReviewError("Review binding does not bind request.")
    if review_binding.get("next_stage") != NEXT_STAGE:
        raise MasterVisualHumanReviewError("Review binding next stage changed.")
    review = _require_mapping(
        episode_definition.get("master_visual_human_review"),
        "master_visual_human_review",
    )
    if review.get("review_binding_id") != review_binding.get("review_binding_id"):
        raise MasterVisualHumanReviewError("Episode does not bind review package.")
    if episode_definition.get("next_stage") != NEXT_STAGE:
        raise MasterVisualHumanReviewError("Episode did not advance to human decision.")
    if episode_definition.get("master_visual_approval") is not False:
        raise MasterVisualHumanReviewError("Episode visual approval opened prematurely.")
    if production_brief.get("master_visual_human_review_binding_id") != review_binding.get(
        "review_binding_id"
    ):
        raise MasterVisualHumanReviewError("Production brief does not bind review.")
    if EXACT_APPROVAL_PHRASE not in markdown:
        raise MasterVisualHumanReviewError("Readable review omits approval phrase.")

    for label, artifact in (
        ("dossier", dossier),
        ("critical review", critical_review),
        ("prototype plan", prototype_plan),
        ("approval request", approval_request),
        ("review binding", review_binding),
        ("production brief", production_brief),
    ):
        if artifact.get("master_visual_approval") is not False:
            raise MasterVisualHumanReviewError(
                f"{label}: final master visual approval must remain false."
            )
        if artifact.get("generated_video_planned_seconds") != 0:
            raise MasterVisualHumanReviewError(
                f"{label}: generated-video allocation must remain zero."
            )
        _validate_execution_blocks(artifact, label)


def build_all(
    *,
    storyboard: Mapping[str, object],
    visual_bible: Mapping[str, object],
    color_script: Mapping[str, object],
    animatic: Mapping[str, object],
    development_audit: Mapping[str, object],
    development_binding: Mapping[str, object],
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
) -> tuple[dict, dict, dict, dict, dict, dict, dict, str]:
    validate_inputs(
        storyboard=storyboard,
        visual_bible=visual_bible,
        color_script=color_script,
        animatic=animatic,
        development_audit=development_audit,
        development_binding=development_binding,
        episode_definition=episode_definition,
        production_brief=production_brief,
    )
    dossier = build_review_dossier(
        visual_bible=visual_bible,
        color_script=color_script,
        animatic=animatic,
    )
    critical_review = build_critical_review(dossier)
    prototype_plan = build_style_frame_prototype_plan(
        storyboard=storyboard,
        dossier=dossier,
        critical_review=critical_review,
    )
    approval_request = build_human_approval_request(
        dossier=dossier,
        critical_review=critical_review,
        prototype_plan=prototype_plan,
    )
    review_binding = build_review_binding(
        dossier=dossier,
        critical_review=critical_review,
        prototype_plan=prototype_plan,
        approval_request=approval_request,
    )
    updated_definition = update_episode_definition(
        episode_definition=episode_definition,
        dossier=dossier,
        critical_review=critical_review,
        prototype_plan=prototype_plan,
        approval_request=approval_request,
        review_binding=review_binding,
    )
    updated_brief = update_production_brief(
        production_brief=production_brief,
        dossier=dossier,
        critical_review=critical_review,
        prototype_plan=prototype_plan,
        approval_request=approval_request,
        review_binding=review_binding,
    )
    markdown = render_review_markdown(
        dossier=dossier,
        critical_review=critical_review,
        prototype_plan=prototype_plan,
        approval_request=approval_request,
    )
    validate_outputs(
        dossier=dossier,
        critical_review=critical_review,
        prototype_plan=prototype_plan,
        approval_request=approval_request,
        review_binding=review_binding,
        episode_definition=updated_definition,
        production_brief=updated_brief,
        markdown=markdown,
    )
    return (
        dossier,
        critical_review,
        prototype_plan,
        approval_request,
        review_binding,
        updated_definition,
        updated_brief,
        markdown,
    )


def write_outputs(
    *,
    output_root: Path,
    dossier: Mapping[str, object],
    critical_review: Mapping[str, object],
    prototype_plan: Mapping[str, object],
    approval_request: Mapping[str, object],
    review_binding: Mapping[str, object],
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
    markdown: str,
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "dossier": output_root / "master-visual-human-review-dossier-v1.json",
        "critical_review": output_root / "master-visual-critical-review-v1.json",
        "prototype_plan": output_root / "master-style-frame-prototype-plan-v1.json",
        "approval_request": output_root / "master-visual-human-approval-request-v1.json",
        "review_binding": output_root / "master-visual-human-review-binding-v1.json",
        "episode_definition": output_root / "episode-definition-v1.json",
        "production_brief": output_root / "prestige-production-brief-v2-1.json",
        "readable_review": output_root / "master-visual-human-review-v1.md",
        "readme": output_root / "README.md",
    }
    for key, payload in (
        ("dossier", dossier),
        ("critical_review", critical_review),
        ("prototype_plan", prototype_plan),
        ("approval_request", approval_request),
        ("review_binding", review_binding),
        ("episode_definition", episode_definition),
        ("production_brief", production_brief),
    ):
        write_json(outputs[key], payload)
    outputs["readable_review"].write_text(
        markdown,
        encoding="utf-8",
        newline="\n",
    )
    outputs["readme"].write_text(
        "# Adam Master Visual Human Review v1\n\n"
        "This package critically reviews the non-paid visual-development baseline, "
        "prepares eight style-frame prototypes, and requests an explicit human "
        "decision. It grants no approval and creates no media. Final master visual, "
        "video, paid, direct, live-provider, and Runware execution remain blocked.\n",
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
