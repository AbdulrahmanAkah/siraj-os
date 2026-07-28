"""Finalize Adam evidence approval and open the offline evidence gate."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Mapping, Sequence

from .evidence_binding import (
    ApprovedEventEvidenceAdjudication,
    ApprovedEvidenceBinder,
    ApprovedEvidencePackage,
    EVIDENCE_GATE_OPEN,
    LIVE_EXECUTION_STATUS,
    canonical_json_sha256,
)
from .full_episode_evidence_candidate import validate_candidates

FINAL_APPROVAL_SCHEMA = "siraj-final-evidence-human-approval-v1"
DIRECTION_SCHEMA = "siraj-prestige-historical-cinematic-direction-v1"
BINDING_RECEIPT_SCHEMA = "siraj-approved-evidence-binding-receipt-v1"

EXPECTED_SOURCE_FINGERPRINT = (
    "4598d943a1d728db305b24816095c8c1168dc16b2c01c324420ddb9bfbc6ef00"
)
EXPECTED_EVIDENCE_FINGERPRINT = (
    "026af41120d56b5269414ca4baff5184286ed5b1b3139f3c87139b4afa1948a7"
)
EXPECTED_ADJUDICATION_FINGERPRINT = (
    "4996e91da4f53727f5ccb98c54c02fe58cd26412b597a4f4bc24aa527f83fc31"
)
EXPECTED_APPROVAL_PHRASE_SHA256 = (
    "b3743a558e894e1faf204751a01e2ea032b62c3bc068296e7af71df926700477"
)

APPROVAL_PHRASE = (
    "أعتمد بشريًا حزمة أدلة حلقة آدم النهائية وتحكيم أحداثها الـ37 "
    "وفق البصمات المحددة فقط، وأجيز فتح بوابة الأدلة دون السماح بأي "
    "تشغيل مدفوع أو مباشر"
)

APPROVED_BY = "Abdulrahman Akah"
APPROVED_AT_BAGHDAD = "2026-07-29T01:24:26+03:00"
APPROVED_AT_UTC = "2026-07-28T22:24:26Z"
TIMEZONE = "Asia/Baghdad"

EXPECTED_EVENT_COUNT = 37
EXPECTED_SOURCE_COUNT = 44
EXPECTED_EVIDENCE_ITEM_COUNT = 57
EXPECTED_INCLUDED_EVENT_COUNT = 36
EXPECTED_QUALIFIED_EVENT_COUNT = 7
EXPECTED_OMITTED_EVENT_COUNT = 0
EXPECTED_EDITORIAL_EVENT_COUNT = 1
EXPECTED_STORYBOARD_FRAME_COUNT = 14

PAID_EXECUTION = "BLOCKED"
DIRECT_EXECUTION = "BLOCKED"
AUTOMATIC_EVIDENCE_APPROVAL = "FORBIDDEN"

FINAL_SOURCE_RELATIVE = "contracts/source-package-v1.json"
FINAL_EVIDENCE_RELATIVE = "evidence/approved-evidence-package-v1.json"
FINAL_ADJUDICATION_RELATIVE = "evidence/event-evidence-adjudication-v1.json"
FINAL_APPROVAL_RELATIVE = "evidence/final-evidence-human-approval-v1.json"
FINAL_BINDING_RELATIVE = "cinematic/evidence-bound-cinematic-blueprint-v1.json"
FINAL_RECEIPT_RELATIVE = "evidence/approved-evidence-binding-receipt-v1.json"
DIRECTION_RELATIVE = "contracts/prestige-historical-cinematic-direction-v1.json"


class FinalEvidenceApprovalError(ValueError):
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


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalEvidenceApprovalError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise FinalEvidenceApprovalError(f"Expected JSON object: {path}")
    return value


def read_json_list(path: Path) -> list[dict]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalEvidenceApprovalError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, list) or not all(
        isinstance(item, dict) for item in value
    ):
        raise FinalEvidenceApprovalError(
            f"Expected JSON object list: {path}"
        )
    return [dict(item) for item in value]


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _validate_source_candidate_fingerprint(
    candidate: Mapping[str, object],
) -> None:
    stored = candidate.get("input_fingerprint")
    if stored != EXPECTED_SOURCE_FINGERPRINT:
        raise FinalEvidenceApprovalError(
            "Source candidate fingerprint differs from the approved value."
        )
    payload = copy.deepcopy(dict(candidate))
    payload.pop("candidate_id", None)
    payload.pop("input_fingerprint", None)
    calculated = canonical_sha256(payload)
    if calculated != stored:
        raise FinalEvidenceApprovalError(
            "Source candidate content does not match its stored fingerprint."
        )


def _validate_candidate_fingerprint(
    candidate: Mapping[str, object],
    *,
    key: str,
    expected: str,
    label: str,
) -> None:
    stored = candidate.get(key)
    if stored != expected:
        raise FinalEvidenceApprovalError(
            f"{label} fingerprint differs from the approved value."
        )
    payload = copy.deepcopy(dict(candidate))
    payload.pop(key, None)
    calculated = canonical_sha256(payload)
    if calculated != stored:
        raise FinalEvidenceApprovalError(
            f"{label} content does not match its stored fingerprint."
        )


def validate_approval_inputs(
    *,
    source_candidate: Mapping[str, object],
    evidence_candidate: Mapping[str, object],
    adjudication_candidate: Mapping[str, object],
    approval_request: Mapping[str, object],
) -> None:
    _validate_source_candidate_fingerprint(source_candidate)
    _validate_candidate_fingerprint(
        evidence_candidate,
        key="candidate_fingerprint",
        expected=EXPECTED_EVIDENCE_FINGERPRINT,
        label="Evidence candidate",
    )
    _validate_candidate_fingerprint(
        adjudication_candidate,
        key="candidate_fingerprint",
        expected=EXPECTED_ADJUDICATION_FINGERPRINT,
        label="Adjudication candidate",
    )

    if approval_request.get("exact_approval_phrase") != APPROVAL_PHRASE:
        raise FinalEvidenceApprovalError(
            "Approval request phrase differs from the user's exact approval."
        )
    if text_sha256(APPROVAL_PHRASE) != EXPECTED_APPROVAL_PHRASE_SHA256:
        raise FinalEvidenceApprovalError(
            "Embedded approval phrase hash is invalid."
        )
    if approval_request.get("exact_approval_phrase_sha256") != (
        EXPECTED_APPROVAL_PHRASE_SHA256
    ):
        raise FinalEvidenceApprovalError(
            "Approval request phrase hash differs."
        )

    expected_fields = {
        "source_package_input_fingerprint":
            EXPECTED_SOURCE_FINGERPRINT,
        "evidence_candidate_fingerprint":
            EXPECTED_EVIDENCE_FINGERPRINT,
        "adjudication_candidate_fingerprint":
            EXPECTED_ADJUDICATION_FINGERPRINT,
    }
    for key, expected in expected_fields.items():
        if approval_request.get(key) != expected:
            raise FinalEvidenceApprovalError(
                f"Approval request mismatch: {key}"
            )

    validate_candidates(
        source_candidate=source_candidate,
        evidence_candidate=evidence_candidate,
        adjudication_candidate=adjudication_candidate,
    )
    if source_candidate.get("source_count") != EXPECTED_SOURCE_COUNT:
        raise FinalEvidenceApprovalError("Expected 44 approved sources.")
    if evidence_candidate.get("evidence_item_count") != (
        EXPECTED_EVIDENCE_ITEM_COUNT
    ):
        raise FinalEvidenceApprovalError("Expected 57 evidence items.")
    if adjudication_candidate.get("decision_count") != EXPECTED_EVENT_COUNT:
        raise FinalEvidenceApprovalError("Expected 37 event decisions.")


def build_human_approval_record() -> dict:
    return {
        "approval_id": (
            "adam_final_evidence_human_approval_"
            + EXPECTED_APPROVAL_PHRASE_SHA256[:16]
        ),
        "approved_by": APPROVED_BY,
        "approved_at": APPROVED_AT_UTC,
        "approved_at_baghdad": APPROVED_AT_BAGHDAD,
        "timezone": TIMEZONE,
        "approval_status": "APPROVED",
        "human_approval": True,
        "notes": (
            "Explicit creator approval captured in Asia/Baghdad. "
            "Authorization is limited to final evidence approval and "
            "offline strict binding. Paid, live, direct, and provider "
            "execution remain blocked."
        ),
    }


def build_final_human_approval() -> dict:
    approval = {
        "schema_version": FINAL_APPROVAL_SCHEMA,
        "status": "APPROVED_OFFLINE_BINDING_AUTHORIZED",
        "episode_id": "episode-001-adam",
        **build_human_approval_record(),
        "approval_phrase": APPROVAL_PHRASE,
        "approval_phrase_sha256": EXPECTED_APPROVAL_PHRASE_SHA256,
        "candidate_fingerprints": {
            "source_package": EXPECTED_SOURCE_FINGERPRINT,
            "evidence_package": EXPECTED_EVIDENCE_FINGERPRINT,
            "event_adjudication": EXPECTED_ADJUDICATION_FINGERPRINT,
        },
        "approved_scope": {
            "event_count": EXPECTED_EVENT_COUNT,
            "source_count": EXPECTED_SOURCE_COUNT,
            "evidence_item_count": EXPECTED_EVIDENCE_ITEM_COUNT,
            "open_evidence_gate_after_strict_offline_binding": True,
        },
        "prohibited_scope": {
            "automatic_evidence_approval": True,
            "paid_execution": True,
            "live_execution": True,
            "direct_provider_execution": True,
            "runware_execution": True,
        },
        "automatic_evidence_approval": AUTOMATIC_EVIDENCE_APPROVAL,
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "live_provider_execution": LIVE_EXECUTION_STATUS,
    }
    approval["record_fingerprint"] = canonical_sha256(approval)
    return approval


def build_direction_contract() -> dict:
    contract = {
        "schema_version": DIRECTION_SCHEMA,
        "status": "ACTIVE_CREATOR_DIRECTIVE",
        "series_id": "siraj-islamic-history-chronology",
        "episode_id": "episode-001-adam",
        "timezone": TIMEZONE,
        "creator_directive_recorded_at_baghdad": APPROVED_AT_BAGHDAD,
        "format_identity": "PRESTIGE_HISTORICAL_CINEMATIC_SERIES",
        "production_profile": (
            "WORLD_CLASS_PRESTIGE_HISTORICAL_CINEMA_V1"
        ),
        "quality_ambition": (
            "Compete in dramatic power, visual authorship, narrative "
            "precision, atmosphere, pacing, and emotional impact with "
            "the greatest historical cinema and prestige series."
        ),
        "evidence_role": (
            "Evidence is the factual backbone and safety boundary; it "
            "must not force a lecture, talking-head, slideshow, or dry "
            "documentary presentation style."
        ),
        "mandatory_principles": [
            "Cinematic dramatic construction rather than information dumping",
            "Character-centred emotional progression without invented doctrine",
            "Visual storytelling, subtext, silence, rhythm, and escalation",
            "Every scene must carry dramatic function and visual authorship",
            "World-building through scale, atmosphere, texture, sound, and light",
            "Prestige-series continuity across episodes and seasons",
            "Evidence-bound narration with clear qualification where required",
            "Religious visual safety without sacrificing cinematic power",
            "No depiction of Allah, angels, prophets, or the unseen as literal bodies",
            "Symbolic and environmental imagery must remain non-assertive",
        ],
        "forbidden_failure_modes": [
            "Dry explanatory documentary voice",
            "Lecture structure",
            "Talking-head dependence",
            "Slide-show montage",
            "Generic stock-footage assembly",
            "Flat chronological recitation",
            "Repeated exposition without dramatic movement",
            "Cheap spectacle detached from evidence",
            "Visual literalisation of the unseen",
            "Invented dialogue presented as historical fact",
        ],
        "dramatic_engine": {
            "episode_arc": [
                "mystery",
                "cosmic scale",
                "creation",
                "honour",
                "knowledge",
                "command",
                "obedience versus pride",
                "human intimacy",
                "paradise",
                "approaching trial",
            ],
            "scene_design": (
                "Each scene requires objective, pressure, turn, image-system, "
                "sound intention, and a transition that increases narrative force."
            ),
            "pacing": (
                "Controlled prestige pacing: deliberate when awe is needed, "
                "compressed when exposition threatens momentum, and explosive "
                "only at genuine dramatic turns."
            ),
        },
        "visual_language": {
            "target": "AUTHORIAL_EPIC_INTIMATE_CINEMA",
            "principles": [
                "monumental scale balanced with intimate human detail",
                "motivated camera movement",
                "meaningful composition and negative space",
                "distinct visual motif for every thematic movement",
                "coherent colour, texture, lens, and lighting systems",
                "transitions motivated by image, motion, sound, or idea",
            ],
        },
        "sound_and_music": {
            "target": "NARRATIVE_SOUND_DESIGN_NOT_BACKGROUND_DECORATION",
            "principles": [
                "silence used as dramatic material",
                "music built around thematic development",
                "sound perspective establishes scale and presence",
                "no generic continuous underscore",
                "narration must interact with picture rather than duplicate it",
            ],
        },
        "approval_policy": {
            "script_approval_required": True,
            "religious_safety_approval_required": True,
            "storyboard_approval_required": True,
            "master_visual_approval_required": True,
            "paid_or_live_execution_requires_separate_explicit_approval": True,
        },
        "paid_execution": PAID_EXECUTION,
        "live_provider_execution": LIVE_EXECUTION_STATUS,
    }
    contract["contract_id"] = (
        "siraj_prestige_cinematic_direction_"
        + canonical_sha256(contract)[:16]
    )
    return contract


def build_final_packages(
    *,
    source_candidate: Mapping[str, object],
    evidence_candidate: Mapping[str, object],
    adjudication_candidate: Mapping[str, object],
) -> tuple[dict, dict, dict, dict]:
    human = build_human_approval_record()
    approval = build_final_human_approval()

    source_package = {
        "schema_version": source_candidate["target_schema_version"],
        "package_id": (
            "adam_approved_source_package_"
            + EXPECTED_SOURCE_FINGERPRINT[:16]
        ),
        "episode_id": source_candidate["episode_id"],
        "package_status": "APPROVED",
        "input_fingerprint": source_candidate["input_fingerprint"],
        "approval": human,
        "human_approval": True,
        "source_count": source_candidate["source_count"],
        "source_items": copy.deepcopy(source_candidate["source_items"]),
        "automatic_evidence_approval": AUTOMATIC_EVIDENCE_APPROVAL,
        "paid_execution": PAID_EXECUTION,
        "live_provider_execution": LIVE_EXECUTION_STATUS,
    }

    final_package_id = (
        "adam_approved_evidence_package_"
        + EXPECTED_EVIDENCE_FINGERPRINT[:16]
    )
    evidence_package = {
        "schema_version": evidence_candidate["target_schema_version"],
        "package_id": final_package_id,
        "episode_id": evidence_candidate["episode_id"],
        "source_package_fingerprint":
            evidence_candidate["source_package_fingerprint"],
        "approval": human,
        "evidence_items": copy.deepcopy(
            evidence_candidate["evidence_items"]
        ),
    }

    adjudication = {
        "schema_version":
            adjudication_candidate["target_schema_version"],
        "adjudication_id": (
            "adam_approved_event_adjudication_"
            + EXPECTED_ADJUDICATION_FINGERPRINT[:16]
        ),
        "episode_id": adjudication_candidate["episode_id"],
        "evidence_package_id": final_package_id,
        "approval": human,
        "decisions": copy.deepcopy(
            adjudication_candidate["decisions"]
        ),
    }

    ApprovedEvidencePackage.from_mapping(evidence_package)
    ApprovedEventEvidenceAdjudication.from_mapping(adjudication)
    return approval, source_package, evidence_package, adjudication


def build_prebinding_episode_definition(
    *,
    episode_definition: Mapping[str, object],
    source_package: Mapping[str, object],
    evidence_package: Mapping[str, object],
    adjudication: Mapping[str, object],
    direction: Mapping[str, object],
) -> dict:
    definition = copy.deepcopy(dict(episode_definition))
    evidence_fingerprint = canonical_json_sha256(evidence_package)
    adjudication_fingerprint = canonical_json_sha256(adjudication)

    definition["source_package"] = {
        "approval_status": "APPROVED",
        "path": FINAL_SOURCE_RELATIVE,
        "input_fingerprint": source_package["input_fingerprint"],
        "approval_id": source_package["approval"]["approval_id"],
    }
    definition["evidence_package"] = {
        "approval_status": "APPROVED",
        "path": FINAL_EVIDENCE_RELATIVE,
        "input_fingerprint": evidence_fingerprint,
        "approval_id": evidence_package["approval"]["approval_id"],
    }
    definition["event_evidence_adjudication"] = {
        "approval_status": "APPROVED",
        "path": FINAL_ADJUDICATION_RELATIVE,
        "input_fingerprint": adjudication_fingerprint,
        "approval_id": adjudication["approval"]["approval_id"],
    }
    historical = copy.deepcopy(definition["historical_scope"])
    historical["status"] = "APPROVED"
    definition["historical_scope"] = historical

    definition["production_profile"] = direction["production_profile"]
    definition["format_identity"] = direction["format_identity"]
    definition["cinematic_direction"] = {
        "status": "ACTIVE_CREATOR_DIRECTIVE",
        "path": DIRECTION_RELATIVE,
        "contract_id": direction["contract_id"],
        "anti_documentary_presentation": True,
    }
    definition["timezone_policy"] = {
        "canonical_local_timezone": TIMEZONE,
        "approval_time_baghdad": APPROVED_AT_BAGHDAD,
        "machine_timestamp_standard": "UTC_Z",
    }
    definition["evidence_gate_status"] = (
        "WITHHELD_DURING_STRICT_OFFLINE_BINDING"
    )
    definition["live_execution_status"] = LIVE_EXECUTION_STATUS
    definition["paid_execution"] = PAID_EXECUTION
    definition["updated_at"] = APPROVED_AT_UTC
    definition["updated_at_baghdad"] = APPROVED_AT_BAGHDAD
    return definition


def strict_bind(
    *,
    episode_definition: Mapping[str, object],
    event_map: Sequence[Mapping[str, object]],
    editorial_blueprint: Mapping[str, object],
    source_package: Mapping[str, object],
    evidence_package: Mapping[str, object],
    adjudication: Mapping[str, object],
) -> dict:
    evidence_fingerprint = canonical_json_sha256(evidence_package)
    adjudication_fingerprint = canonical_json_sha256(adjudication)

    result = ApprovedEvidenceBinder().bind_from_data(
        episode_definition=episode_definition,
        event_map=event_map,
        editorial_blueprint=editorial_blueprint,
        approved_source_package=source_package,
        evidence_package=ApprovedEvidencePackage.from_mapping(
            evidence_package
        ),
        adjudication=ApprovedEventEvidenceAdjudication.from_mapping(
            adjudication
        ),
        evidence_package_fingerprint=evidence_fingerprint,
        adjudication_fingerprint=adjudication_fingerprint,
    )
    manifest = result.to_manifest()

    if manifest.get("evidence_gate_status") != EVIDENCE_GATE_OPEN:
        raise FinalEvidenceApprovalError(
            "Strict binder did not open the evidence gate."
        )
    if manifest.get("live_execution_status") != LIVE_EXECUTION_STATUS:
        raise FinalEvidenceApprovalError(
            "Strict binder changed live execution status."
        )
    runware = manifest.get("runware_execution_status")
    if not isinstance(runware, str) or not runware.startswith("BLOCKED"):
        raise FinalEvidenceApprovalError(
            "Runware execution is not blocked after binding."
        )

    resolution = manifest.get("event_resolution")
    if not isinstance(resolution, Mapping):
        raise FinalEvidenceApprovalError(
            "Binding result is missing event resolution."
        )
    expected_counts = {
        "included_event_ids": EXPECTED_INCLUDED_EVENT_COUNT,
        "qualified_event_ids": EXPECTED_QUALIFIED_EVENT_COUNT,
        "omitted_event_ids": EXPECTED_OMITTED_EVENT_COUNT,
        "editorial_event_ids": EXPECTED_EDITORIAL_EVENT_COUNT,
    }
    for key, expected in expected_counts.items():
        value = resolution.get(key)
        if not isinstance(value, list) or len(value) != expected:
            raise FinalEvidenceApprovalError(
                f"Unexpected strict binding count for {key}."
            )
    storyboard = manifest.get("storyboard")
    if not isinstance(storyboard, Mapping) or storyboard.get(
        "frame_count"
    ) != EXPECTED_STORYBOARD_FRAME_COUNT:
        raise FinalEvidenceApprovalError(
            "Strict binding did not preserve the 14-frame storyboard."
        )
    return manifest


def build_final_episode_definition(
    *,
    prebinding_definition: Mapping[str, object],
    bound_blueprint: Mapping[str, object],
    binding_receipt: Mapping[str, object],
) -> dict:
    definition = copy.deepcopy(dict(prebinding_definition))
    definition["evidence_gate_status"] = EVIDENCE_GATE_OPEN
    definition["evidence_binding"] = {
        "status": "BOUND_OFFLINE",
        "path": FINAL_BINDING_RELATIVE,
        "binding_id": bound_blueprint["binding_id"],
        "receipt_path": FINAL_RECEIPT_RELATIVE,
        "receipt_id": binding_receipt["receipt_id"],
        "live_execution_status": LIVE_EXECUTION_STATUS,
        "paid_execution": PAID_EXECUTION,
    }
    definition["next_stage"] = (
        "EVIDENCE_BOUND_CINEMATIC_SCRIPT_AND_STORYBOARD_DEVELOPMENT"
    )
    return definition


def build_binding_receipt(
    *,
    approval: Mapping[str, object],
    source_package: Mapping[str, object],
    evidence_package: Mapping[str, object],
    adjudication: Mapping[str, object],
    bound_blueprint: Mapping[str, object],
    direction: Mapping[str, object],
) -> dict:
    receipt = {
        "schema_version": BINDING_RECEIPT_SCHEMA,
        "status": "PASS_APPROVED_EVIDENCE_STRICT_OFFLINE_BINDING",
        "episode_id": "episode-001-adam",
        "approval_id": approval["approval_id"],
        "approval_record_fingerprint": approval["record_fingerprint"],
        "approved_at_baghdad": APPROVED_AT_BAGHDAD,
        "approved_at_utc": APPROVED_AT_UTC,
        "timezone": TIMEZONE,
        "source_package_id": source_package["package_id"],
        "source_package_input_fingerprint":
            source_package["input_fingerprint"],
        "evidence_package_id": evidence_package["package_id"],
        "evidence_package_fingerprint":
            canonical_json_sha256(evidence_package),
        "adjudication_id": adjudication["adjudication_id"],
        "adjudication_fingerprint":
            canonical_json_sha256(adjudication),
        "binding_id": bound_blueprint["binding_id"],
        "direction_contract_id": direction["contract_id"],
        "event_count": EXPECTED_EVENT_COUNT,
        "source_count": EXPECTED_SOURCE_COUNT,
        "evidence_item_count": EXPECTED_EVIDENCE_ITEM_COUNT,
        "storyboard_frame_count": EXPECTED_STORYBOARD_FRAME_COUNT,
        "evidence_gate_status": EVIDENCE_GATE_OPEN,
        "live_execution_status": LIVE_EXECUTION_STATUS,
        "runware_execution_status":
            bound_blueprint["runware_execution_status"],
        "paid_execution": PAID_EXECUTION,
        "direct_execution": DIRECT_EXECUTION,
        "next_stage": (
            "PRESTIGE_CINEMATIC_SCRIPT_AND_EVIDENCE_BOUND_STORYBOARD"
        ),
    }
    receipt["receipt_id"] = (
        "adam_approved_evidence_binding_receipt_"
        + canonical_sha256(receipt)[:16]
    )
    return receipt


def build_all(
    *,
    source_candidate: Mapping[str, object],
    evidence_candidate: Mapping[str, object],
    adjudication_candidate: Mapping[str, object],
    approval_request: Mapping[str, object],
    episode_definition: Mapping[str, object],
    event_map: Sequence[Mapping[str, object]],
    editorial_blueprint: Mapping[str, object],
) -> dict[str, dict]:
    validate_approval_inputs(
        source_candidate=source_candidate,
        evidence_candidate=evidence_candidate,
        adjudication_candidate=adjudication_candidate,
        approval_request=approval_request,
    )
    direction = build_direction_contract()
    (
        approval,
        source_package,
        evidence_package,
        adjudication,
    ) = build_final_packages(
        source_candidate=source_candidate,
        evidence_candidate=evidence_candidate,
        adjudication_candidate=adjudication_candidate,
    )
    prebinding = build_prebinding_episode_definition(
        episode_definition=episode_definition,
        source_package=source_package,
        evidence_package=evidence_package,
        adjudication=adjudication,
        direction=direction,
    )
    bound = strict_bind(
        episode_definition=prebinding,
        event_map=event_map,
        editorial_blueprint=editorial_blueprint,
        source_package=source_package,
        evidence_package=evidence_package,
        adjudication=adjudication,
    )
    receipt = build_binding_receipt(
        approval=approval,
        source_package=source_package,
        evidence_package=evidence_package,
        adjudication=adjudication,
        bound_blueprint=bound,
        direction=direction,
    )
    final_definition = build_final_episode_definition(
        prebinding_definition=prebinding,
        bound_blueprint=bound,
        binding_receipt=receipt,
    )
    return {
        "approval": approval,
        "direction": direction,
        "source_package": source_package,
        "evidence_package": evidence_package,
        "adjudication": adjudication,
        "bound_blueprint": bound,
        "binding_receipt": receipt,
        "episode_definition": final_definition,
    }


def write_report(
    *,
    output_root: Path,
    artifacts: Mapping[str, Mapping[str, object]],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "approval": output_root / "final-evidence-human-approval-v1.json",
        "direction": output_root
        / "prestige-historical-cinematic-direction-v1.json",
        "source_package": output_root / "source-package-v1.json",
        "evidence_package": output_root
        / "approved-evidence-package-v1.json",
        "adjudication": output_root
        / "event-evidence-adjudication-v1.json",
        "bound_blueprint": output_root
        / "evidence-bound-cinematic-blueprint-v1.json",
        "binding_receipt": output_root
        / "approved-evidence-binding-receipt-v1.json",
        "episode_definition": output_root
        / "episode-definition-v1.json",
        "summary": output_root
        / "final-evidence-approval-binding-summary.csv",
        "readme": output_root / "README.md",
    }
    for key in (
        "approval",
        "direction",
        "source_package",
        "evidence_package",
        "adjudication",
        "bound_blueprint",
        "binding_receipt",
        "episode_definition",
    ):
        write_json(outputs[key], artifacts[key])

    resolution = artifacts["bound_blueprint"]["event_resolution"]
    with outputs["summary"].open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        fields = ["metric", "value"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        rows = {
            "event_count": EXPECTED_EVENT_COUNT,
            "source_count": EXPECTED_SOURCE_COUNT,
            "evidence_item_count": EXPECTED_EVIDENCE_ITEM_COUNT,
            "included_event_count": len(
                resolution["included_event_ids"]
            ),
            "qualified_event_count": len(
                resolution["qualified_event_ids"]
            ),
            "omitted_event_count": len(
                resolution["omitted_event_ids"]
            ),
            "editorial_event_count": len(
                resolution["editorial_event_ids"]
            ),
            "storyboard_frame_count":
                artifacts["bound_blueprint"]["storyboard"][
                    "frame_count"
                ],
            "evidence_gate_status": EVIDENCE_GATE_OPEN,
            "live_execution_status": LIVE_EXECUTION_STATUS,
            "paid_execution": PAID_EXECUTION,
            "timezone": TIMEZONE,
            "format_identity":
                artifacts["direction"]["format_identity"],
        }
        for metric, value in rows.items():
            writer.writerow({"metric": metric, "value": value})

    outputs["readme"].write_text(
        "# Adam final evidence approval and strict offline binding\n\n"
        "The creator's exact approval is recorded with both Asia/Baghdad "
        "local time and the UTC timestamp required by the strict binder. "
        "The approved source package contains 44 records; the approved "
        "evidence package contains 57 evidence items; all 37 events are "
        "adjudicated; and the existing 14-frame cinematic blueprint is "
        "strictly bound offline. The evidence gate is open. Runware, live, "
        "direct, and paid execution remain blocked.\n\n"
        "The active creative contract defines SIRAJ as a world-class "
        "prestige historical cinematic series. Evidence remains the factual "
        "backbone, but dry documentary, lecture, slideshow, generic stock "
        "montage, and flat exposition are explicitly forbidden.\n",
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
