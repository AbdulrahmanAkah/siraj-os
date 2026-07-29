"""Bind the explicit human approval of Adam storyboard master v2.1."""
from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Mapping

SCHEMA_APPROVAL = "siraj-final-storyboard-master-human-approval-v2.1"
SCHEMA_RECEIPT = "siraj-final-storyboard-master-approval-receipt-v2.1"
SCHEMA_BINDING = "siraj-final-storyboard-master-approval-binding-v2.1"
SCHEMA_VISUAL_GATE = "siraj-non-paid-visual-development-gate-v1"

TIMEZONE = "Asia/Baghdad"
APPROVAL_DATE_BAGHDAD = "2026-07-29"
VERSION = "2.1"
LIVE_EXECUTION = "BLOCKED"
PAID_EXECUTION = "BLOCKED"
RUNWARE_EXECUTION = "BLOCKED"

SCRIPT_ID = "adam_prestige_cinematic_script_v2_1_ff540783ec519581"
SCRIPT_FINGERPRINT = (
    "ff540783ec519581bd902caf81145c3f77819a7351f2bd5d07e9f84705a4fb27"
)
STORYBOARD_ID = "adam_detailed_cinematic_storyboard_v2_1_867b88ade164ebe4"
STORYBOARD_FINGERPRINT = (
    "867b88ade164ebe444aeaaeeb9f60accef122f59cf8b45b020223f3ca8788bf8"
)
DIRECTORIAL_AUDIT_ID = (
    "adam_storyboard_master_directorial_audit_v2_1_8e592ccb2937446c"
)
APPROVAL_REQUEST_ID = (
    "adam_final_storyboard_master_approval_request_v2_1_81ce8c14dfa69ebf"
)
TRACE_ID = "adam_script_storyboard_trace_v2_1_a77f4d5de33416a7"

EXACT_APPROVAL_PHRASE = (
    "أعتمد بشريًا النسخة الإخراجية النهائية للنص السينمائي والستوريبورد "
    "الرئيسي لحلقة آدم بإصدار 2.1 وفق بصمتيهما المحددتين، وأجيز الانتقال "
    "إلى الهوية البصرية الرئيسية والأنيماتيك غير المدفوع دون السماح بأي "
    "تشغيل مدفوع أو مباشر"
)
EXACT_APPROVAL_PHRASE_SHA256 = (
    "ff7f1def070b6d68f3562b3f65d925d51eb40bdfa8f04c211f1ab412087608e2"
)

NEXT_STAGE = (
    "MASTER_VISUAL_BIBLE_COLOR_SCRIPT_AND_NON_PAID_ANIMATIC_DEVELOPMENT"
)
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


class ApprovalBindingError(ValueError):
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
        raise ApprovalBindingError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ApprovalBindingError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def count_unresolved_directorial_decisions(
    audit: Mapping[str, object],
) -> int:
    """Derive unresolved decisions from the persisted audit schema."""
    required_exact = {
        "status": "PASS_FINAL_STORYBOARD_MASTER_CANDIDATE",
        "director_cut_version": VERSION,
        "shot_count": 70,
        "sequence_count": 14,
        "duration_seconds": 1320,
        "dramatic_beat_coverage": 70,
        "visual_subtext_coverage": 70,
        "camera_psychology_coverage": 70,
        "sound_perspective_coverage": 70,
        "acceptance_criteria_coverage": 70,
        "rejection_trigger_coverage": 70,
        "unique_dramatic_beats": 70,
        "generic_placeholder_shots": 0,
        "exact_covenant_verse_present": True,
        "malformed_covenant_text_present": False,
        "descendants_emergence_assertive": True,
        "chronology_qualification_only": True,
        "research_meta_language_removed": True,
        "v2_predecessor_preserved": True,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
    }
    return sum(
        audit.get(key) != expected
        for key, expected in required_exact.items()
    )


def validate_inputs(
    *,
    script: Mapping[str, object],
    storyboard: Mapping[str, object],
    trace: Mapping[str, object],
    approval_request: Mapping[str, object],
    audit: Mapping[str, object],
    episode_definition: Mapping[str, object],
) -> None:
    if script.get("script_id") != SCRIPT_ID:
        raise ApprovalBindingError("Unexpected final script id.")
    if script.get("script_fingerprint") != SCRIPT_FINGERPRINT:
        raise ApprovalBindingError("Unexpected final script fingerprint.")
    if str(script.get("director_cut_version")) != VERSION:
        raise ApprovalBindingError("Final script must be v2.1.")
    if script.get("sequence_count") != 14:
        raise ApprovalBindingError("Final script must retain fourteen sequences.")

    if storyboard.get("storyboard_id") != STORYBOARD_ID:
        raise ApprovalBindingError("Unexpected final storyboard id.")
    if storyboard.get("storyboard_fingerprint") != STORYBOARD_FINGERPRINT:
        raise ApprovalBindingError("Unexpected final storyboard fingerprint.")
    if str(storyboard.get("director_cut_version")) != VERSION:
        raise ApprovalBindingError("Final storyboard must be v2.1.")
    if storyboard.get("shot_count") != 70:
        raise ApprovalBindingError("Final storyboard must retain seventy shots.")

    if trace.get("trace_id") != TRACE_ID:
        raise ApprovalBindingError("Unexpected final trace id.")
    if trace.get("event_count") != 37:
        raise ApprovalBindingError("Final trace must retain 37 events.")
    if trace.get("evidence_item_count") != 57:
        raise ApprovalBindingError("Final trace must retain 57 evidence items.")

    if audit.get("audit_id") != DIRECTORIAL_AUDIT_ID:
        raise ApprovalBindingError("Unexpected directorial audit id.")
    if audit.get("status") != "PASS_FINAL_STORYBOARD_MASTER_CANDIDATE":
        raise ApprovalBindingError("Directorial audit candidate did not pass.")
    if audit.get("shot_count") != 70:
        raise ApprovalBindingError("Directorial audit shot count changed.")
    if count_unresolved_directorial_decisions(audit) != 0:
        raise ApprovalBindingError(
            "Persisted directorial audit contains unresolved or "
            "incomplete decisions."
        )

    if approval_request.get("request_id") != APPROVAL_REQUEST_ID:
        raise ApprovalBindingError("Unexpected approval request id.")
    if approval_request.get("exact_approval_phrase") != EXACT_APPROVAL_PHRASE:
        raise ApprovalBindingError("Approval phrase differs from the request.")
    if (
        approval_request.get("exact_approval_phrase_sha256")
        != EXACT_APPROVAL_PHRASE_SHA256
    ):
        raise ApprovalBindingError("Approval phrase fingerprint changed.")
    if approval_request.get("human_approval") is not False:
        raise ApprovalBindingError("Approval request was already mutated.")
    if hashlib.sha256(EXACT_APPROVAL_PHRASE.encode("utf-8")).hexdigest() != (
        EXACT_APPROVAL_PHRASE_SHA256
    ):
        raise ApprovalBindingError("Embedded approval phrase hash mismatch.")

    script_definition = episode_definition.get("cinematic_script")
    storyboard_definition = episode_definition.get("detailed_storyboard")
    revision = episode_definition.get("director_cut_revision")
    if not (
        isinstance(script_definition, Mapping)
        and script_definition.get("input_fingerprint") == SCRIPT_FINGERPRINT
    ):
        raise ApprovalBindingError("Episode script does not bind v2.1.")
    if not (
        isinstance(storyboard_definition, Mapping)
        and storyboard_definition.get("input_fingerprint")
        == STORYBOARD_FINGERPRINT
    ):
        raise ApprovalBindingError("Episode storyboard does not bind v2.1.")
    if not (
        isinstance(revision, Mapping)
        and str(revision.get("version")) == VERSION
        and revision.get("script_fingerprint") == SCRIPT_FINGERPRINT
        and revision.get("storyboard_fingerprint") == STORYBOARD_FINGERPRINT
    ):
        raise ApprovalBindingError("Episode revision does not bind v2.1.")

    pending_state = (
        script_definition.get("human_approval") is False
        and storyboard_definition.get("human_approval") is False
        and episode_definition.get("next_stage")
        == "HUMAN_REVIEW_OF_FINAL_STORYBOARD_MASTER_V2_1"
    )
    approval_state = episode_definition.get(
        "script_storyboard_human_approval"
    )
    approved_state = (
        script_definition.get("human_approval") is True
        and storyboard_definition.get("human_approval") is True
        and episode_definition.get("next_stage") == NEXT_STAGE
        and isinstance(approval_state, Mapping)
        and approval_state.get("script_fingerprint")
        == SCRIPT_FINGERPRINT
        and approval_state.get("storyboard_fingerprint")
        == STORYBOARD_FINGERPRINT
    )
    if not (pending_state or approved_state):
        raise ApprovalBindingError(
            "Episode is neither at the exact pending gate nor at the "
            "matching bound-approval state."
        )
    if episode_definition.get("live_execution_status") != LIVE_EXECUTION:
        raise ApprovalBindingError("Live execution must remain blocked.")
    if episode_definition.get("paid_execution") != PAID_EXECUTION:
        raise ApprovalBindingError("Paid execution must remain blocked.")


def build_approval_record() -> dict:
    approval = {
        "schema_version": SCHEMA_APPROVAL,
        "status": "HUMAN_APPROVED_FINAL_STORYBOARD_MASTER_V2_1",
        "episode_id": "episode-001-adam",
        "director_cut_version": VERSION,
        "canonical_timezone": TIMEZONE,
        "approval_date_baghdad": APPROVAL_DATE_BAGHDAD,
        "human_approval": True,
        "approval_phrase": EXACT_APPROVAL_PHRASE,
        "approval_phrase_sha256": EXACT_APPROVAL_PHRASE_SHA256,
        "approval_request_id": APPROVAL_REQUEST_ID,
        "script_id": SCRIPT_ID,
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_id": STORYBOARD_ID,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "trace_id": TRACE_ID,
        "directorial_audit_id": DIRECTORIAL_AUDIT_ID,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": "BLOCKED",
        "runware_execution": RUNWARE_EXECUTION,
        "approval_scope": {
            "final_cinematic_script_v2_1": "APPROVED",
            "religious_safety_of_final_script_v2_1": "APPROVED",
            "final_storyboard_master_v2_1": "APPROVED",
            "master_visual_bible_development": "ALLOWED_NON_PAID_ONLY",
            "color_script_development": "ALLOWED_NON_PAID_ONLY",
            "animatic_development": "ALLOWED_NON_PAID_ONLY",
            "paid_execution": PAID_EXECUTION,
            "direct_execution": "BLOCKED",
            "live_provider_execution": LIVE_EXECUTION,
            "runware_execution": RUNWARE_EXECUTION,
        },
    }
    approval["approval_id"] = (
        "adam_final_storyboard_master_human_approval_v2_1_"
        + canonical_sha256(approval)[:16]
    )
    return approval


def build_binding_receipt(approval: Mapping[str, object]) -> dict:
    receipt = {
        "schema_version": SCHEMA_RECEIPT,
        "status": "PASS_HUMAN_APPROVAL_BOUND_TO_EXACT_FINGERPRINTS",
        "episode_id": "episode-001-adam",
        "canonical_timezone": TIMEZONE,
        "approval_id": approval["approval_id"],
        "approval_phrase_sha256": EXACT_APPROVAL_PHRASE_SHA256,
        "approval_request_id": APPROVAL_REQUEST_ID,
        "script_id": SCRIPT_ID,
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_id": STORYBOARD_ID,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "trace_id": TRACE_ID,
        "directorial_audit_id": DIRECTORIAL_AUDIT_ID,
        "binding_scope": "SCRIPT_RELIGIOUS_SAFETY_AND_STORYBOARD_MASTER_V2_1",
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": "BLOCKED",
        "runware_execution": RUNWARE_EXECUTION,
    }
    receipt["receipt_id"] = (
        "adam_final_storyboard_master_approval_receipt_v2_1_"
        + canonical_sha256(receipt)[:16]
    )
    return receipt


def build_approval_binding(
    approval: Mapping[str, object],
    receipt: Mapping[str, object],
) -> dict:
    binding = {
        "schema_version": SCHEMA_BINDING,
        "status": "BOUND_HUMAN_APPROVED_FINAL_STORYBOARD_MASTER_V2_1",
        "episode_id": "episode-001-adam",
        "director_cut_version": VERSION,
        "approval_id": approval["approval_id"],
        "approval_receipt_id": receipt["receipt_id"],
        "approval_request_id": APPROVAL_REQUEST_ID,
        "script_id": SCRIPT_ID,
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_id": STORYBOARD_ID,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "directorial_audit_id": DIRECTORIAL_AUDIT_ID,
        "next_stage": NEXT_STAGE,
        "master_visual_approval": False,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": "BLOCKED",
        "runware_execution": RUNWARE_EXECUTION,
    }
    binding["binding_id"] = (
        "adam_final_storyboard_master_approval_binding_v2_1_"
        + canonical_sha256(binding)[:16]
    )
    return binding


def build_visual_development_gate(
    binding: Mapping[str, object],
) -> dict:
    gate = {
        "schema_version": SCHEMA_VISUAL_GATE,
        "status": "OPEN_NON_PAID_VISUAL_DEVELOPMENT_ONLY",
        "episode_id": "episode-001-adam",
        "source_binding_id": binding["binding_id"],
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "allowed_non_paid_stages": list(ALLOWED_NON_PAID_STAGES),
        "forbidden_execution_modes": list(FORBIDDEN_EXECUTION_MODES),
        "master_visual_approval": False,
        "generated_video_planned_seconds": 0,
        "provider_selection": "DEFERRED",
        "budget_allocation": "DEFERRED",
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": "BLOCKED",
        "runware_execution": RUNWARE_EXECUTION,
    }
    gate["gate_id"] = (
        "adam_non_paid_visual_development_gate_"
        + canonical_sha256(gate)[:16]
    )
    return gate


def update_episode_definition(
    *,
    episode_definition: Mapping[str, object],
    approval: Mapping[str, object],
    receipt: Mapping[str, object],
    binding: Mapping[str, object],
    visual_gate: Mapping[str, object],
) -> dict:
    definition = copy.deepcopy(dict(episode_definition))
    existing = definition.get("script_storyboard_human_approval")
    if isinstance(existing, Mapping):
        if (
            existing.get("approval_id") != approval["approval_id"]
            or existing.get("script_fingerprint") != SCRIPT_FINGERPRINT
            or existing.get("storyboard_fingerprint")
            != STORYBOARD_FINGERPRINT
        ):
            raise ApprovalBindingError(
                "Existing storyboard approval binds different fingerprints."
            )

    script = copy.deepcopy(dict(definition["cinematic_script"]))
    script.update(
        {
            "status": "HUMAN_APPROVED_FINAL_MASTER_V2_1",
            "human_approval": True,
            "approval_id": approval["approval_id"],
            "approval_receipt_id": receipt["receipt_id"],
        }
    )
    definition["cinematic_script"] = script

    storyboard = copy.deepcopy(dict(definition["detailed_storyboard"]))
    storyboard.update(
        {
            "status": "HUMAN_APPROVED_FINAL_MASTER_V2_1",
            "human_approval": True,
            "approval_id": approval["approval_id"],
            "approval_receipt_id": receipt["receipt_id"],
        }
    )
    definition["detailed_storyboard"] = storyboard

    revision = copy.deepcopy(dict(definition["director_cut_revision"]))
    revision.update(
        {
            "status": "HUMAN_APPROVED_FINAL_MASTER_V2_1",
            "human_approval": True,
            "approval_id": approval["approval_id"],
            "approval_receipt_id": receipt["receipt_id"],
            "approval_binding_id": binding["binding_id"],
        }
    )
    definition["director_cut_revision"] = revision

    definition["script_storyboard_approval_request"] = {
        "status": "HUMAN_APPROVED_AND_BOUND",
        "path": "evidence/script-storyboard-human-approval-request-v2-1.json",
        "request_id": APPROVAL_REQUEST_ID,
        "approval_path":
            "evidence/final-storyboard-master-human-approval-v2-1.json",
        "approval_id": approval["approval_id"],
        "receipt_path":
            "evidence/final-storyboard-master-approval-receipt-v2-1.json",
        "receipt_id": receipt["receipt_id"],
        "binding_path":
            "contracts/final-storyboard-master-approval-binding-v2-1.json",
        "binding_id": binding["binding_id"],
    }
    definition["script_storyboard_human_approval"] = {
        "status": "APPROVED_EXACT_FINGERPRINT_BINDING",
        "approval_id": approval["approval_id"],
        "approval_receipt_id": receipt["receipt_id"],
        "approval_binding_id": binding["binding_id"],
        "script_fingerprint": SCRIPT_FINGERPRINT,
        "storyboard_fingerprint": STORYBOARD_FINGERPRINT,
        "religious_safety_approval": "APPROVED_FOR_FINAL_SCRIPT_V2_1",
        "approval_date_baghdad": APPROVAL_DATE_BAGHDAD,
    }
    definition["visual_development_gate"] = {
        "status": visual_gate["status"],
        "path": "cinematic/non-paid-visual-development-gate-v1.json",
        "gate_id": visual_gate["gate_id"],
        "master_visual_approval": False,
    }
    definition["storyboard_completion_status"] = "COMPLETE_HUMAN_APPROVED"
    definition["religious_sensitivity"] = (
        "FINAL_SCRIPT_V2_1_HUMAN_APPROVED; "
        "MASTER_VISUAL_REMAINS_HUMAN_REVIEW_REQUIRED"
    )
    definition["master_visual_status"] = (
        "NOT_STARTED_HUMAN_APPROVAL_REQUIRED"
    )
    definition["next_stage"] = NEXT_STAGE
    definition["live_execution_status"] = LIVE_EXECUTION
    definition["paid_execution"] = PAID_EXECUTION
    return definition


def validate_outputs(
    *,
    approval: Mapping[str, object],
    receipt: Mapping[str, object],
    binding: Mapping[str, object],
    visual_gate: Mapping[str, object],
    episode_definition: Mapping[str, object],
) -> None:
    if approval.get("human_approval") is not True:
        raise ApprovalBindingError("Human approval was not recorded.")
    if approval.get("approval_phrase") != EXACT_APPROVAL_PHRASE:
        raise ApprovalBindingError("Recorded approval phrase differs.")
    if receipt.get("approval_id") != approval.get("approval_id"):
        raise ApprovalBindingError("Receipt does not bind the approval.")
    if binding.get("approval_receipt_id") != receipt.get("receipt_id"):
        raise ApprovalBindingError("Binding does not bind the receipt.")
    if visual_gate.get("source_binding_id") != binding.get("binding_id"):
        raise ApprovalBindingError("Visual-development gate is unbound.")
    if visual_gate.get("allowed_non_paid_stages") != list(
        ALLOWED_NON_PAID_STAGES
    ):
        raise ApprovalBindingError("Unexpected non-paid stage permissions.")
    if visual_gate.get("forbidden_execution_modes") != list(
        FORBIDDEN_EXECUTION_MODES
    ):
        raise ApprovalBindingError("Execution prohibition changed.")
    if episode_definition.get("storyboard_completion_status") != (
        "COMPLETE_HUMAN_APPROVED"
    ):
        raise ApprovalBindingError("Episode storyboard approval is not active.")
    if episode_definition.get("next_stage") != NEXT_STAGE:
        raise ApprovalBindingError("Episode next stage did not advance.")
    if episode_definition.get("master_visual_status") != (
        "NOT_STARTED_HUMAN_APPROVAL_REQUIRED"
    ):
        raise ApprovalBindingError("Master visual approval was opened incorrectly.")
    for artifact in (approval, receipt, binding, visual_gate):
        if artifact.get("live_provider_execution") != LIVE_EXECUTION:
            raise ApprovalBindingError("Live execution must remain blocked.")
        if artifact.get("paid_execution") != PAID_EXECUTION:
            raise ApprovalBindingError("Paid execution must remain blocked.")
        if artifact.get("direct_execution") != "BLOCKED":
            raise ApprovalBindingError("Direct execution must remain blocked.")
        if artifact.get("runware_execution") != RUNWARE_EXECUTION:
            raise ApprovalBindingError("Runware execution must remain blocked.")


def build_all(
    *,
    script: Mapping[str, object],
    storyboard: Mapping[str, object],
    trace: Mapping[str, object],
    approval_request: Mapping[str, object],
    audit: Mapping[str, object],
    episode_definition: Mapping[str, object],
) -> tuple[dict, dict, dict, dict, dict]:
    validate_inputs(
        script=script,
        storyboard=storyboard,
        trace=trace,
        approval_request=approval_request,
        audit=audit,
        episode_definition=episode_definition,
    )
    approval = build_approval_record()
    receipt = build_binding_receipt(approval)
    binding = build_approval_binding(approval, receipt)
    visual_gate = build_visual_development_gate(binding)
    updated_definition = update_episode_definition(
        episode_definition=episode_definition,
        approval=approval,
        receipt=receipt,
        binding=binding,
        visual_gate=visual_gate,
    )
    validate_outputs(
        approval=approval,
        receipt=receipt,
        binding=binding,
        visual_gate=visual_gate,
        episode_definition=updated_definition,
    )
    return approval, receipt, binding, visual_gate, updated_definition


def write_outputs(
    *,
    output_root: Path,
    approval: Mapping[str, object],
    receipt: Mapping[str, object],
    binding: Mapping[str, object],
    visual_gate: Mapping[str, object],
    episode_definition: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "approval":
            output_root / "final-storyboard-master-human-approval-v2-1.json",
        "receipt":
            output_root / "final-storyboard-master-approval-receipt-v2-1.json",
        "binding":
            output_root / "final-storyboard-master-approval-binding-v2-1.json",
        "visual_gate":
            output_root / "non-paid-visual-development-gate-v1.json",
        "episode_definition": output_root / "episode-definition-v1.json",
        "readme": output_root / "README.md",
    }
    write_json(outputs["approval"], approval)
    write_json(outputs["receipt"], receipt)
    write_json(outputs["binding"], binding)
    write_json(outputs["visual_gate"], visual_gate)
    write_json(outputs["episode_definition"], episode_definition)
    outputs["readme"].write_text(
        "# Adam Final Storyboard Master Approval Binding v2.1\n\n"
        "The user's exact human-approval phrase is bound to the final script "
        "and storyboard fingerprints. Script, religious-safety, and storyboard "
        "gates are approved. Only non-paid visual-bible, colour-script, "
        "animatic, shot-planning, and audio-previs work is opened. Master "
        "visual approval remains pending. Paid, direct, live-provider, and "
        "Runware execution remain blocked.\n",
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
