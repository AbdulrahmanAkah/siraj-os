"""Bind Adam's exact human approval of the visual-development baseline.

The approval authorises only eight non-paid still-image style-frame/keyframe
prototypes. It does not approve the final master visual identity and does not
authorise audio, video, paid, direct, live-provider, or Runware execution.
"""
from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Mapping, Sequence

TIMEZONE = "Asia/Baghdad"
APPROVAL_DATE_BAGHDAD = "2026-07-29"
APPROVAL_TIMESTAMP_BAGHDAD = "2026-07-29T15:53:00+03:00"
EPISODE_ID = "episode-001-adam"
SCRIPT_FINGERPRINT = "ff540783ec519581bd902caf81145c3f77819a7351f2bd5d07e9f84705a4fb27"
STORYBOARD_FINGERPRINT = "867b88ade164ebe444aeaaeeb9f60accef122f59cf8b45b020223f3ca8788bf8"
VISUAL_BIBLE_ID = "adam_master_visual_bible_v1_0790d2e2e5fed178"
COLOR_SCRIPT_ID = "adam_color_script_v1_fe7ad6202e323835"
ANIMATIC_DEVELOPMENT_ID = "adam_non_paid_animatic_development_v1_df9bfe3614040947"
REVIEW_DOSSIER_ID = "adam_master_visual_human_review_dossier_v1_5dd9d62e194cd5b4"
CRITICAL_REVIEW_ID = "adam_master_visual_critical_review_v1_02e5776297bed398"
PROTOTYPE_PLAN_ID = "adam_master_style_frame_prototype_plan_v1_1c4d8ae331ea3dd6"
APPROVAL_REQUEST_ID = "adam_master_visual_human_approval_request_v1_a53844369a6cb0fc"
REVIEW_BINDING_ID = "adam_master_visual_human_review_binding_v1_4527afce21be895f"
SOURCE_STAGE = "HUMAN_DECISION_ON_MASTER_VISUAL_DEVELOPMENT_REVIEW_V1"
NEXT_STAGE = "NON_PAID_MASTER_STYLE_FRAMES_AND_KEYFRAME_PROTOTYPING_V1"
DECISION = "APPROVE_DEVELOPMENT_BASELINE_FOR_NON_PAID_STYLE_FRAMES"
STYLE_FRAME_AUTHORISATION = "AUTHORIZED_NON_PAID_EIGHT_ANCHOR_PROTOTYPES_ONLY"
LIVE_EXECUTION = "BLOCKED"
PAID_EXECUTION = "BLOCKED"
DIRECT_EXECUTION = "BLOCKED"
RUNWARE_EXECUTION = "BLOCKED"

SCHEMA_APPROVAL = "siraj-master-visual-human-approval-v1"
SCHEMA_RECEIPT = "siraj-master-visual-human-approval-receipt-v1"
SCHEMA_BINDING = "siraj-master-visual-human-approval-binding-v1"
SCHEMA_GATE = "siraj-non-paid-master-style-frame-prototyping-gate-v1"

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


class MasterVisualHumanApprovalError(ValueError):
    pass


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
        raise MasterVisualHumanApprovalError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise MasterVisualHumanApprovalError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise MasterVisualHumanApprovalError(f"Expected mapping for {label}.")
    return value


def _validate_blocks(artifact: Mapping[str, object], label: str) -> None:
    for key, expected in (
        ("live_provider_execution", LIVE_EXECUTION),
        ("paid_execution", PAID_EXECUTION),
        ("direct_execution", DIRECT_EXECUTION),
        ("runware_execution", RUNWARE_EXECUTION),
    ):
        if artifact.get(key) != expected:
            raise MasterVisualHumanApprovalError(f"{label}: {key} must remain BLOCKED.")
    if artifact.get("generated_video_planned_seconds") != 0:
        raise MasterVisualHumanApprovalError(f"{label}: video allocation must remain zero.")
    if artifact.get("master_visual_approval") is not False:
        raise MasterVisualHumanApprovalError(f"{label}: final visual approval must remain false.")


def validate_inputs(
    *,
    dossier: Mapping[str, object],
    critical_review: Mapping[str, object],
    prototype_plan: Mapping[str, object],
    approval_request: Mapping[str, object],
    review_binding: Mapping[str, object],
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
) -> None:
    if dossier.get("review_dossier_id") != REVIEW_DOSSIER_ID:
        raise MasterVisualHumanApprovalError("Unexpected review dossier id.")
    if dossier.get("status") != "READY_FOR_HUMAN_DECISION_ON_DEVELOPMENT_BASELINE":
        raise MasterVisualHumanApprovalError("Review dossier is not decision-ready.")
    if critical_review.get("critical_review_id") != CRITICAL_REVIEW_ID:
        raise MasterVisualHumanApprovalError("Unexpected critical review id.")
    if critical_review.get("development_baseline_blocker_count") != 0:
        raise MasterVisualHumanApprovalError("Development baseline has blockers.")
    if critical_review.get("final_master_visual_approval_blocker_count") != 3:
        raise MasterVisualHumanApprovalError("Final-approval blocker set changed.")
    if prototype_plan.get("prototype_plan_id") != PROTOTYPE_PLAN_ID:
        raise MasterVisualHumanApprovalError("Unexpected prototype plan id.")
    if prototype_plan.get("prototype_count") != 8:
        raise MasterVisualHumanApprovalError("Exactly eight prototypes are required.")
    if prototype_plan.get("anchor_shot_ids") != list(ANCHOR_SHOT_IDS):
        raise MasterVisualHumanApprovalError("Anchor-shot selection changed.")
    if approval_request.get("request_id") != APPROVAL_REQUEST_ID:
        raise MasterVisualHumanApprovalError("Unexpected approval request id.")
    if approval_request.get("exact_approval_phrase") != EXACT_APPROVAL_PHRASE:
        raise MasterVisualHumanApprovalError("Exact approval phrase differs.")
    if approval_request.get("exact_approval_phrase_sha256") != EXACT_APPROVAL_PHRASE_SHA256:
        raise MasterVisualHumanApprovalError("Approval phrase hash differs.")
    if approval_request.get("human_approval") is not False:
        raise MasterVisualHumanApprovalError(
            "Approval request must remain immutable and pending."
        )
    if review_binding.get("review_binding_id") != REVIEW_BINDING_ID:
        raise MasterVisualHumanApprovalError("Unexpected review binding id.")
    if review_binding.get("approval_request_id") != APPROVAL_REQUEST_ID:
        raise MasterVisualHumanApprovalError("Review binding does not bind request.")
    if review_binding.get("approval_phrase_sha256") != EXACT_APPROVAL_PHRASE_SHA256:
        raise MasterVisualHumanApprovalError("Review binding phrase hash differs.")
    if review_binding.get("next_stage") != SOURCE_STAGE:
        raise MasterVisualHumanApprovalError("Review binding source stage differs.")

    review = _mapping(episode_definition.get("master_visual_human_review"), "review")
    if review.get("review_binding_id") != REVIEW_BINDING_ID:
        raise MasterVisualHumanApprovalError("Episode does not bind review package.")
    if episode_definition.get("master_visual_approval") is not False:
        raise MasterVisualHumanApprovalError("Episode final visual approval changed.")
    if production_brief.get("master_visual_human_review_binding_id") != REVIEW_BINDING_ID:
        raise MasterVisualHumanApprovalError(
            "Production brief does not bind review package."
        )

    plan_authorisation = prototype_plan.get("image_generation_authorisation")
    pending_state = plan_authorisation == "PENDING_HUMAN_APPROVAL"
    authorised_state = plan_authorisation == STYLE_FRAME_AUTHORISATION
    if not (pending_state or authorised_state):
        raise MasterVisualHumanApprovalError(
            "Prototype-plan image authorisation has an unexpected value."
        )

    if pending_state:
        if prototype_plan.get("status") != (
            "PLANNED_AWAITING_HUMAN_DEVELOPMENT_BASELINE_APPROVAL"
        ):
            raise MasterVisualHumanApprovalError(
                "Pending prototype-plan status changed."
            )
        if prototype_plan.get("human_approval") not in (None, False):
            raise MasterVisualHumanApprovalError(
                "Pending prototype plan contains an approval."
            )
        if review.get("human_approval") is not False:
            raise MasterVisualHumanApprovalError("Episode human approval is not pending.")
        if review.get("human_decision") != "PENDING":
            raise MasterVisualHumanApprovalError("Episode human decision is not pending.")
        if episode_definition.get("next_stage") != SOURCE_STAGE:
            raise MasterVisualHumanApprovalError(
                "Episode is not at the human decision gate."
            )
        if production_brief.get("style_frame_prototyping_status") != (
            "PENDING_HUMAN_BASELINE_APPROVAL"
        ):
            raise MasterVisualHumanApprovalError(
                "Pending production-brief prototype status changed."
            )
    else:
        approval = build_approval_record()
        receipt = build_receipt(approval)
        binding = build_binding(approval, receipt)
        gate = build_prototyping_gate(binding)

        if prototype_plan.get("status") != (
            "HUMAN_APPROVED_READY_FOR_NON_PAID_PROTOTYPE_EXECUTION"
        ):
            raise MasterVisualHumanApprovalError(
                "Authorised prototype-plan status changed."
            )
        if prototype_plan.get("human_approval") is not True:
            raise MasterVisualHumanApprovalError(
                "Authorised prototype plan lost human approval."
            )
        if prototype_plan.get("human_decision") != DECISION:
            raise MasterVisualHumanApprovalError(
                "Authorised prototype-plan decision differs."
            )
        if prototype_plan.get("human_approval_id") != approval["approval_id"]:
            raise MasterVisualHumanApprovalError(
                "Authorised prototype plan binds another approval."
            )
        if prototype_plan.get("human_approval_binding_id") != binding["binding_id"]:
            raise MasterVisualHumanApprovalError(
                "Authorised prototype plan binds another approval binding."
            )
        if prototype_plan.get("prototyping_gate_id") != gate["gate_id"]:
            raise MasterVisualHumanApprovalError(
                "Authorised prototype plan binds another gate."
            )
        prototypes = prototype_plan.get("prototypes")
        if not isinstance(prototypes, list) or len(prototypes) != 8:
            raise MasterVisualHumanApprovalError(
                "Authorised prototype plan must retain eight prototype entries."
            )
        for prototype in prototypes:
            item = _mapping(prototype, "authorised prototype")
            if item.get("image_generation_authorisation") != STYLE_FRAME_AUTHORISATION:
                raise MasterVisualHumanApprovalError(
                    "A prototype is outside the authorised image scope."
                )
            if item.get("provider_execution") != "NON_PAID_PROTOTYPE_TOOLING_ONLY":
                raise MasterVisualHumanApprovalError(
                    "A prototype has an unexpected provider-execution scope."
                )
            if item.get("video_generation") != "BLOCKED":
                raise MasterVisualHumanApprovalError(
                    "Prototype video generation must remain blocked."
                )

        if review.get("status") != "HUMAN_APPROVED_DEVELOPMENT_BASELINE_ONLY":
            raise MasterVisualHumanApprovalError(
                "Approved episode-review status changed."
            )
        if review.get("human_approval") is not True:
            raise MasterVisualHumanApprovalError(
                "Approved episode review lost human approval."
            )
        if review.get("human_decision") != DECISION:
            raise MasterVisualHumanApprovalError(
                "Approved episode-review decision differs."
            )
        if review.get("human_approval_id") != approval["approval_id"]:
            raise MasterVisualHumanApprovalError(
                "Approved episode review binds another approval."
            )
        if review.get("human_approval_receipt_id") != receipt["receipt_id"]:
            raise MasterVisualHumanApprovalError(
                "Approved episode review binds another receipt."
            )
        if review.get("human_approval_binding_id") != binding["binding_id"]:
            raise MasterVisualHumanApprovalError(
                "Approved episode review binds another binding."
            )
        if review.get("style_frame_image_authorisation") != STYLE_FRAME_AUTHORISATION:
            raise MasterVisualHumanApprovalError(
                "Episode review has an unexpected style-frame scope."
            )
        if review.get("master_visual_approval") is not False:
            raise MasterVisualHumanApprovalError(
                "Final visual approval opened in the review record."
            )

        recorded = _mapping(
            episode_definition.get("master_visual_human_approval"),
            "master visual human approval",
        )
        expected_record = {
            "approval_id": approval["approval_id"],
            "receipt_id": receipt["receipt_id"],
            "binding_id": binding["binding_id"],
            "approval_request_id": APPROVAL_REQUEST_ID,
            "review_binding_id": REVIEW_BINDING_ID,
            "human_decision": DECISION,
            "development_baseline_approval": True,
            "style_frame_image_authorisation": STYLE_FRAME_AUTHORISATION,
            "final_master_visual_approval": False,
            "master_visual_approval": False,
        }
        for key, expected in expected_record.items():
            if recorded.get(key) != expected:
                raise MasterVisualHumanApprovalError(
                    f"Recorded human approval differs at {key}."
                )

        plan_ref = _mapping(
            episode_definition.get("master_style_frame_prototype_plan"),
            "episode prototype plan",
        )
        if (
            plan_ref.get("prototype_plan_id") != PROTOTYPE_PLAN_ID
            or plan_ref.get("prototype_count") != 8
            or plan_ref.get("image_generation_authorisation")
            != STYLE_FRAME_AUTHORISATION
            or plan_ref.get("human_approval_id") != approval["approval_id"]
            or plan_ref.get("prototyping_gate_id") != gate["gate_id"]
        ):
            raise MasterVisualHumanApprovalError(
                "Episode prototype-plan reference is incompatible."
            )

        gate_ref = _mapping(
            episode_definition.get("style_frame_prototyping_gate"),
            "episode style-frame gate",
        )
        if (
            gate_ref.get("gate_id") != gate["gate_id"]
            or gate_ref.get("approved_prototype_count") != 8
            or gate_ref.get("image_generation_authorisation")
            != STYLE_FRAME_AUTHORISATION
            or gate_ref.get("video_generation") != "BLOCKED"
            or gate_ref.get("master_visual_approval") is not False
        ):
            raise MasterVisualHumanApprovalError(
                "Episode style-frame gate is incompatible."
            )
        if episode_definition.get("next_stage") != NEXT_STAGE:
            raise MasterVisualHumanApprovalError(
                "Approved episode did not remain at the prototype stage."
            )
        if episode_definition.get("master_visual_status") != (
            "DEVELOPMENT_BASELINE_HUMAN_APPROVED_STYLE_FRAME_PROTOTYPING_"
            "AUTHORISED_FINAL_APPROVAL_BLOCKED"
        ):
            raise MasterVisualHumanApprovalError(
                "Approved episode master-visual status changed."
            )

        expected_brief = {
            "status": (
                "NON_PAID_STYLE_FRAME_PROTOTYPING_AUTHORISED_"
                "PROVIDER_EXECUTION_BLOCKED"
            ),
            "master_visual_review_status": (
                "HUMAN_APPROVED_DEVELOPMENT_BASELINE_ONLY"
            ),
            "master_visual_status": (
                "DEVELOPMENT_BASELINE_HUMAN_APPROVED_STYLE_FRAME_PROTOTYPING_"
                "AUTHORISED_FINAL_APPROVAL_BLOCKED"
            ),
            "master_visual_human_approval_id": approval["approval_id"],
            "master_visual_human_approval_receipt_id": receipt["receipt_id"],
            "master_visual_human_approval_binding_id": binding["binding_id"],
            "style_frame_prototyping_gate_id": gate["gate_id"],
            "style_frame_prototyping_status": (
                "AUTHORISED_EIGHT_NON_PAID_ANCHOR_PROTOTYPES_ONLY"
            ),
            "style_frame_image_authorisation": STYLE_FRAME_AUTHORISATION,
            "next_non_paid_stage": NEXT_STAGE,
            "provider_selection": "DEFERRED_NON_PAID_PROTOTYPE_TOOLING",
            "budget_allocation": "ZERO_PAID_BUDGET",
        }
        for key, expected in expected_brief.items():
            if production_brief.get(key) != expected:
                raise MasterVisualHumanApprovalError(
                    f"Authorised production brief differs at {key}."
                )

    for label, artifact in (
        ("dossier", dossier),
        ("critical review", critical_review),
        ("prototype plan", prototype_plan),
        ("approval request", approval_request),
        ("review binding", review_binding),
        ("production brief", production_brief),
    ):
        _validate_blocks(artifact, label)


def build_approval_record() -> dict:
    approval = {
        "schema_version": SCHEMA_APPROVAL,
        "status": "APPROVED_DEVELOPMENT_BASELINE_FOR_NON_PAID_STYLE_FRAME_PROTOTYPING",
        "episode_id": EPISODE_ID,
        "human_approval": True,
        "human_decision": DECISION,
        "approval_date_baghdad": APPROVAL_DATE_BAGHDAD,
        "approval_timestamp_baghdad": APPROVAL_TIMESTAMP_BAGHDAD,
        "canonical_timezone": TIMEZONE,
        "approval_phrase": EXACT_APPROVAL_PHRASE,
        "approval_phrase_sha256": EXACT_APPROVAL_PHRASE_SHA256,
        "approval_request_id": APPROVAL_REQUEST_ID,
        "review_binding_id": REVIEW_BINDING_ID,
        "review_dossier_id": REVIEW_DOSSIER_ID,
        "critical_review_id": CRITICAL_REVIEW_ID,
        "prototype_plan_id": PROTOTYPE_PLAN_ID,
        "visual_bible_id": VISUAL_BIBLE_ID,
        "color_script_id": COLOR_SCRIPT_ID,
        "animatic_development_id": ANIMATIC_DEVELOPMENT_ID,
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "approval_scope": {
            "development_baseline": "APPROVED",
            "non_paid_style_frame_prototyping": "APPROVED_EIGHT_ANCHOR_STILLS_ONLY",
            "final_master_visual_identity": "NOT_APPROVED",
            "timed_video_animatic": "NOT_APPROVED",
            "audio_generation": "BLOCKED",
            "video_generation": "BLOCKED",
            "paid_execution": "BLOCKED",
            "direct_execution": "BLOCKED",
            "live_provider_execution": "BLOCKED",
            "runware_execution": "BLOCKED",
        },
        "style_frame_image_authorisation": STYLE_FRAME_AUTHORISATION,
        "approved_anchor_shot_ids": list(ANCHOR_SHOT_IDS),
        "approved_prototype_count": 8,
        "next_stage": NEXT_STAGE,
        "master_visual_approval": False,
        "final_master_visual_approval": False,
        "media_assets_created": 0,
        "generated_video_planned_seconds": 0,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    approval["approval_id"] = (
        "adam_master_visual_human_approval_v1_" + canonical_sha256(approval)[:16]
    )
    return approval


def build_receipt(approval: Mapping[str, object]) -> dict:
    receipt = {
        "schema_version": SCHEMA_RECEIPT,
        "status": "RECORDED_EXACT_HUMAN_APPROVAL",
        "episode_id": EPISODE_ID,
        "approval_id": approval["approval_id"],
        "approval_request_id": APPROVAL_REQUEST_ID,
        "review_binding_id": REVIEW_BINDING_ID,
        "approval_phrase_sha256": EXACT_APPROVAL_PHRASE_SHA256,
        "human_decision": DECISION,
        "approval_timestamp_baghdad": APPROVAL_TIMESTAMP_BAGHDAD,
        "style_frame_image_authorisation": STYLE_FRAME_AUTHORISATION,
        "next_stage": NEXT_STAGE,
        "master_visual_approval": False,
        "media_assets_created": 0,
        "generated_video_planned_seconds": 0,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    receipt["receipt_id"] = (
        "adam_master_visual_human_approval_receipt_v1_"
        + canonical_sha256(receipt)[:16]
    )
    return receipt


def build_binding(approval: Mapping[str, object], receipt: Mapping[str, object]) -> dict:
    binding = {
        "schema_version": SCHEMA_BINDING,
        "status": "BOUND_APPROVED_DEVELOPMENT_BASELINE_NON_PAID_STYLE_FRAME_GATE",
        "episode_id": EPISODE_ID,
        "approval_id": approval["approval_id"],
        "approval_receipt_id": receipt["receipt_id"],
        "approval_request_id": APPROVAL_REQUEST_ID,
        "review_binding_id": REVIEW_BINDING_ID,
        "prototype_plan_id": PROTOTYPE_PLAN_ID,
        "approval_phrase_sha256": EXACT_APPROVAL_PHRASE_SHA256,
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "style_frame_image_authorisation": STYLE_FRAME_AUTHORISATION,
        "approved_anchor_shot_ids": list(ANCHOR_SHOT_IDS),
        "approved_prototype_count": 8,
        "next_stage": NEXT_STAGE,
        "master_visual_approval": False,
        "media_assets_created": 0,
        "generated_video_planned_seconds": 0,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    binding["binding_id"] = (
        "adam_master_visual_human_approval_binding_v1_"
        + canonical_sha256(binding)[:16]
    )
    return binding


def build_prototyping_gate(binding: Mapping[str, object]) -> dict:
    gate = {
        "schema_version": SCHEMA_GATE,
        "status": "OPEN_EIGHT_NON_PAID_STYLE_FRAME_PROTOTYPES_ONLY",
        "episode_id": EPISODE_ID,
        "source_approval_binding_id": binding["binding_id"],
        "source_review_binding_id": REVIEW_BINDING_ID,
        "prototype_plan_id": PROTOTYPE_PLAN_ID,
        "image_generation_authorisation": STYLE_FRAME_AUTHORISATION,
        "image_generation_scope": "EIGHT_MASTER_STYLE_FRAME_STILL_IMAGES_ONLY",
        "approved_anchor_shot_ids": list(ANCHOR_SHOT_IDS),
        "approved_prototype_count": 8,
        "audio_generation": "BLOCKED",
        "video_generation": "BLOCKED",
        "timed_animatic_generation": "BLOCKED",
        "provider_selection": "DEFERRED_NON_PAID_PROTOTYPE_TOOLING",
        "budget_allocation": "ZERO_PAID_BUDGET",
        "next_stage": NEXT_STAGE,
        "master_visual_approval": False,
        "final_master_visual_approval": False,
        "media_assets_created": 0,
        "generated_video_planned_seconds": 0,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "runware_execution": RUNWARE_EXECUTION,
    }
    gate["gate_id"] = (
        "adam_non_paid_master_style_frame_prototyping_gate_v1_"
        + canonical_sha256(gate)[:16]
    )
    return gate


def update_prototype_plan(
    prototype_plan: Mapping[str, object],
    approval: Mapping[str, object],
    binding: Mapping[str, object],
    gate: Mapping[str, object],
) -> dict:
    plan = copy.deepcopy(dict(prototype_plan))
    if plan.get("prototype_plan_id") != PROTOTYPE_PLAN_ID:
        raise MasterVisualHumanApprovalError("Prototype plan id changed.")
    plan.update(
        {
            "status": "HUMAN_APPROVED_READY_FOR_NON_PAID_PROTOTYPE_EXECUTION",
            "human_approval": True,
            "human_decision": DECISION,
            "human_approval_id": approval["approval_id"],
            "human_approval_binding_id": binding["binding_id"],
            "prototyping_gate_id": gate["gate_id"],
            "image_generation_authorisation": STYLE_FRAME_AUTHORISATION,
            "provider_selection": "DEFERRED_NON_PAID_PROTOTYPE_TOOLING",
            "budget_allocation": "ZERO_PAID_BUDGET",
            "master_visual_approval": False,
            "final_master_visual_approval": False,
            "media_assets_created": 0,
            "generated_video_planned_seconds": 0,
            "live_provider_execution": LIVE_EXECUTION,
            "paid_execution": PAID_EXECUTION,
            "direct_execution": DIRECT_EXECUTION,
            "runware_execution": RUNWARE_EXECUTION,
        }
    )
    for prototype in plan.get("prototypes", []):
        if isinstance(prototype, dict):
            prototype["image_generation_authorisation"] = STYLE_FRAME_AUTHORISATION
            prototype["provider_execution"] = "NON_PAID_PROTOTYPE_TOOLING_ONLY"
            prototype["video_generation"] = "BLOCKED"
    return plan


def update_episode_definition(
    episode_definition: Mapping[str, object],
    approval: Mapping[str, object],
    receipt: Mapping[str, object],
    binding: Mapping[str, object],
    gate: Mapping[str, object],
    prototype_plan: Mapping[str, object],
) -> dict:
    definition = copy.deepcopy(dict(episode_definition))
    review = copy.deepcopy(dict(_mapping(definition.get("master_visual_human_review"), "review")))
    review.update(
        {
            "status": "HUMAN_APPROVED_DEVELOPMENT_BASELINE_ONLY",
            "human_approval": True,
            "human_decision": DECISION,
            "human_approval_id": approval["approval_id"],
            "human_approval_receipt_id": receipt["receipt_id"],
            "human_approval_binding_id": binding["binding_id"],
            "approval_date_baghdad": APPROVAL_DATE_BAGHDAD,
            "style_frame_image_authorisation": STYLE_FRAME_AUTHORISATION,
            "final_master_visual_approval_eligible": False,
            "master_visual_approval": False,
        }
    )
    definition["master_visual_human_review"] = review
    definition["master_visual_human_approval"] = {
        "status": approval["status"],
        "path": "evidence/master-visual-human-approval-v1.json",
        "approval_id": approval["approval_id"],
        "receipt_path": "evidence/master-visual-human-approval-receipt-v1.json",
        "receipt_id": receipt["receipt_id"],
        "binding_path": "contracts/master-visual-human-approval-binding-v1.json",
        "binding_id": binding["binding_id"],
        "approval_request_id": APPROVAL_REQUEST_ID,
        "review_binding_id": REVIEW_BINDING_ID,
        "human_decision": DECISION,
        "development_baseline_approval": True,
        "style_frame_image_authorisation": STYLE_FRAME_AUTHORISATION,
        "final_master_visual_approval": False,
        "master_visual_approval": False,
        "approval_date_baghdad": APPROVAL_DATE_BAGHDAD,
    }
    definition["master_style_frame_prototype_plan"] = {
        "status": prototype_plan["status"],
        "path": "cinematic/master-style-frame-prototype-plan-v1.json",
        "prototype_plan_id": PROTOTYPE_PLAN_ID,
        "prototype_count": 8,
        "image_generation_authorisation": STYLE_FRAME_AUTHORISATION,
        "human_approval_id": approval["approval_id"],
        "prototyping_gate_id": gate["gate_id"],
    }
    definition["style_frame_prototyping_gate"] = {
        "status": gate["status"],
        "path": "cinematic/non-paid-master-style-frame-prototyping-gate-v1.json",
        "gate_id": gate["gate_id"],
        "approved_prototype_count": 8,
        "image_generation_authorisation": STYLE_FRAME_AUTHORISATION,
        "video_generation": "BLOCKED",
        "master_visual_approval": False,
    }
    definition["master_visual_status"] = (
        "DEVELOPMENT_BASELINE_HUMAN_APPROVED_STYLE_FRAME_PROTOTYPING_AUTHORISED_FINAL_APPROVAL_BLOCKED"
    )
    definition["master_visual_approval"] = False
    definition["next_stage"] = NEXT_STAGE
    definition["religious_sensitivity"] = (
        "FINAL_SCRIPT_V2_1_HUMAN_APPROVED; VISUAL_DEVELOPMENT_BASELINE_HUMAN_APPROVED; "
        "EIGHT_NON_PAID_STYLE_FRAME_PROTOTYPES_AUTHORISED; FINAL_MASTER_VISUAL_REMAINS_UNAPPROVED"
    )
    definition["live_execution_status"] = LIVE_EXECUTION
    definition["paid_execution"] = PAID_EXECUTION
    return definition


def update_production_brief(
    production_brief: Mapping[str, object],
    approval: Mapping[str, object],
    receipt: Mapping[str, object],
    binding: Mapping[str, object],
    gate: Mapping[str, object],
) -> dict:
    brief = copy.deepcopy(dict(production_brief))
    brief.update(
        {
            "status": "NON_PAID_STYLE_FRAME_PROTOTYPING_AUTHORISED_PROVIDER_EXECUTION_BLOCKED",
            "master_visual_review_status": "HUMAN_APPROVED_DEVELOPMENT_BASELINE_ONLY",
            "master_visual_status": (
                "DEVELOPMENT_BASELINE_HUMAN_APPROVED_STYLE_FRAME_PROTOTYPING_AUTHORISED_FINAL_APPROVAL_BLOCKED"
            ),
            "master_visual_approval": False,
            "master_visual_human_approval_id": approval["approval_id"],
            "master_visual_human_approval_receipt_id": receipt["receipt_id"],
            "master_visual_human_approval_binding_id": binding["binding_id"],
            "style_frame_prototyping_gate_id": gate["gate_id"],
            "style_frame_prototyping_status": "AUTHORISED_EIGHT_NON_PAID_ANCHOR_PROTOTYPES_ONLY",
            "style_frame_image_authorisation": STYLE_FRAME_AUTHORISATION,
            "next_non_paid_stage": NEXT_STAGE,
            "generated_video_planned_seconds": 0,
            "provider_selection": "DEFERRED_NON_PAID_PROTOTYPE_TOOLING",
            "budget_allocation": "ZERO_PAID_BUDGET",
            "live_provider_execution": LIVE_EXECUTION,
            "paid_execution": PAID_EXECUTION,
            "direct_execution": DIRECT_EXECUTION,
            "runware_execution": RUNWARE_EXECUTION,
        }
    )
    return brief


def render_approval_markdown(
    approval: Mapping[str, object],
    receipt: Mapping[str, object],
    binding: Mapping[str, object],
    gate: Mapping[str, object],
) -> str:
    lines = [
        "# اعتماد خط أساس التطوير البصري — حلقة آدم — الإصدار 1",
        "",
        "## القرار البشري المسجل",
        "",
        f"> {EXACT_APPROVAL_PHRASE}",
        "",
        f"- SHA-256: `{EXACT_APPROVAL_PHRASE_SHA256}`",
        f"- تاريخ القرار في بغداد: `{APPROVAL_DATE_BAGHDAD}`",
        f"- وقت التسجيل: `{APPROVAL_TIMESTAMP_BAGHDAD}`",
        f"- القرار: `{DECISION}`",
        "",
        "## أثر القرار",
        "",
        "- اعتماد خط أساس التطوير البصري فقط.",
        "- السماح بثمانية Style Frames/Keyframes ثابتة غير مدفوعة ومحددة مسبقًا.",
        "- عدم اعتماد الهوية البصرية الرئيسية النهائية.",
        "- منع الصوت والفيديو والـAnimatic الموقّت والتشغيل المدفوع أو المباشر.",
        "",
        f"- Approval ID: `{approval['approval_id']}`",
        f"- Receipt ID: `{receipt['receipt_id']}`",
        f"- Binding ID: `{binding['binding_id']}`",
        f"- Gate ID: `{gate['gate_id']}`",
        "",
        f"المرحلة التالية: `{NEXT_STAGE}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def validate_outputs(
    approval: Mapping[str, object],
    receipt: Mapping[str, object],
    binding: Mapping[str, object],
    gate: Mapping[str, object],
    prototype_plan: Mapping[str, object],
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
    markdown: str,
) -> None:
    if approval.get("human_approval") is not True or approval.get("human_decision") != DECISION:
        raise MasterVisualHumanApprovalError("Human approval was not recorded exactly.")
    if approval.get("approval_phrase") != EXACT_APPROVAL_PHRASE:
        raise MasterVisualHumanApprovalError("Recorded approval phrase differs.")
    if receipt.get("approval_id") != approval.get("approval_id"):
        raise MasterVisualHumanApprovalError("Receipt does not bind approval.")
    if binding.get("approval_receipt_id") != receipt.get("receipt_id"):
        raise MasterVisualHumanApprovalError("Binding does not bind receipt.")
    if gate.get("source_approval_binding_id") != binding.get("binding_id"):
        raise MasterVisualHumanApprovalError("Prototype gate is unbound.")
    if gate.get("approved_anchor_shot_ids") != list(ANCHOR_SHOT_IDS):
        raise MasterVisualHumanApprovalError("Gate anchor shots changed.")
    if prototype_plan.get("image_generation_authorisation") != STYLE_FRAME_AUTHORISATION:
        raise MasterVisualHumanApprovalError("Prototype plan was not authorised.")
    if episode_definition.get("next_stage") != NEXT_STAGE:
        raise MasterVisualHumanApprovalError("Episode did not advance to prototype stage.")
    if episode_definition.get("master_visual_approval") is not False:
        raise MasterVisualHumanApprovalError("Final master visual approval opened incorrectly.")
    if production_brief.get("style_frame_prototyping_gate_id") != gate.get("gate_id"):
        raise MasterVisualHumanApprovalError("Production brief does not bind gate.")
    if EXACT_APPROVAL_PHRASE not in markdown:
        raise MasterVisualHumanApprovalError("Approval markdown omits exact phrase.")
    for label, artifact in (
        ("approval", approval),
        ("receipt", receipt),
        ("binding", binding),
        ("gate", gate),
        ("prototype plan", prototype_plan),
        ("production brief", production_brief),
    ):
        _validate_blocks(artifact, label)


def build_all(
    *,
    dossier: Mapping[str, object],
    critical_review: Mapping[str, object],
    prototype_plan: Mapping[str, object],
    approval_request: Mapping[str, object],
    review_binding: Mapping[str, object],
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
) -> tuple[dict, dict, dict, dict, dict, dict, dict, str]:
    validate_inputs(
        dossier=dossier,
        critical_review=critical_review,
        prototype_plan=prototype_plan,
        approval_request=approval_request,
        review_binding=review_binding,
        episode_definition=episode_definition,
        production_brief=production_brief,
    )
    approval = build_approval_record()
    receipt = build_receipt(approval)
    binding = build_binding(approval, receipt)
    gate = build_prototyping_gate(binding)
    updated_plan = update_prototype_plan(prototype_plan, approval, binding, gate)
    updated_definition = update_episode_definition(
        episode_definition, approval, receipt, binding, gate, updated_plan
    )
    updated_brief = update_production_brief(
        production_brief, approval, receipt, binding, gate
    )
    markdown = render_approval_markdown(approval, receipt, binding, gate)
    validate_outputs(
        approval,
        receipt,
        binding,
        gate,
        updated_plan,
        updated_definition,
        updated_brief,
        markdown,
    )
    return (
        approval,
        receipt,
        binding,
        gate,
        updated_plan,
        updated_definition,
        updated_brief,
        markdown,
    )


def write_outputs(
    *,
    output_root: Path,
    approval: Mapping[str, object],
    receipt: Mapping[str, object],
    binding: Mapping[str, object],
    gate: Mapping[str, object],
    prototype_plan: Mapping[str, object],
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
    markdown: str,
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "approval": output_root / "master-visual-human-approval-v1.json",
        "receipt": output_root / "master-visual-human-approval-receipt-v1.json",
        "binding": output_root / "master-visual-human-approval-binding-v1.json",
        "gate": output_root / "non-paid-master-style-frame-prototyping-gate-v1.json",
        "prototype_plan": output_root / "master-style-frame-prototype-plan-v1.json",
        "episode_definition": output_root / "episode-definition-v1.json",
        "production_brief": output_root / "prestige-production-brief-v2-1.json",
        "readable_approval": output_root / "master-visual-human-approval-v1.md",
        "readme": output_root / "README.md",
    }
    for key, payload in (
        ("approval", approval),
        ("receipt", receipt),
        ("binding", binding),
        ("gate", gate),
        ("prototype_plan", prototype_plan),
        ("episode_definition", episode_definition),
        ("production_brief", production_brief),
    ):
        write_json(outputs[key], payload)
    outputs["readable_approval"].write_text(markdown, encoding="utf-8", newline="\n")
    outputs["readme"].write_text(
        "# Adam Master Visual Human Approval Binding v1\n\n"
        "Records the exact human approval of the development baseline and opens only "
        "the eight-still non-paid style-frame prototype gate. Final master visual, "
        "audio, video, paid, direct, live-provider, and Runware execution remain blocked.\n",
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
