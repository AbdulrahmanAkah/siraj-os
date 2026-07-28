"""Build a non-binding human review packet for the three Adam evidence gaps.

This module does not approve evidence, does not create an approved evidence package,
and cannot open the evidence gate. It converts the tracked source-origin classification
and proposed adjudication into a compact review packet and a blank approval template.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

REVIEW_PACKET_SCHEMA = "siraj-gap-human-review-packet-v1"
APPROVAL_TEMPLATE_SCHEMA = "siraj-gap-human-approval-template-v1"
REVIEW_PACKET_STATUS = "HUMAN_REVIEW_READY"
APPROVAL_TEMPLATE_STATUS = "TEMPLATE_NOT_APPROVED"
EVIDENCE_GATE_STATUS = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTOMATIC_APPROVAL_STATUS = "FORBIDDEN"
LIVE_EXECUTION_STATUS = "BLOCKED"
TARGET_EVENT_IDS = ("EV-ADAM-031", "EV-ADAM-071", "EV-ADAM-091")


class GapHumanReviewError(ValueError):
    """Raised when the gap review packet is unsafe or inconsistent."""


def canonical_json_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GapHumanReviewError(f"{label} must be an object.")
    return value


def _objects(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise GapHumanReviewError(f"{label} must be a list of objects.")
    return list(value)


def _strings(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise GapHumanReviewError(f"{label} must be a list of nonblank strings.")
    result = [item.strip() for item in value]
    if len(result) != len(set(result)):
        raise GapHumanReviewError(f"{label} must not contain duplicates.")
    return result


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GapHumanReviewError(f"{key} must be a nonblank string.")
    return value.strip()


def _assert_safe(value: object, path: str = "root") -> None:
    secret_fragments = (
        "api_key", "apikey", "access_token", "refresh_token", "password",
        "secret", "credential", "cookie",
    )
    raw_text_fragments = (
        "raw_text", "page_text", "full_text", "quoted_text", "source_excerpt",
    )
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in secret_fragments):
                raise GapHumanReviewError(f"Secret-like field is forbidden: {path}.{key}")
            if any(fragment in lowered for fragment in raw_text_fragments):
                raise GapHumanReviewError(f"Raw source text field is forbidden: {path}.{key}")
            _assert_safe(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_safe(item, f"{path}[{index}]")


def _classification_event_map(classification: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    events = _objects(classification.get("events"), "classification.events")
    by_id = {_required_text(item, "event_id"): item for item in events}
    if tuple(by_id) != TARGET_EVENT_IDS:
        raise GapHumanReviewError("Classification must preserve the exact three Adam gaps.")
    return by_id


def _proposal_decision_map(proposal: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    decisions = _objects(proposal.get("decisions"), "proposal.decisions")
    by_id = {_required_text(item, "event_id"): item for item in decisions}
    if tuple(by_id) != TARGET_EVENT_IDS:
        raise GapHumanReviewError("Proposal must preserve the exact three Adam gaps.")
    return by_id


def _source_record_map(classification: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    records = _objects(classification.get("source_records"), "source_records")
    by_id = {_required_text(item, "source_record_id"): item for item in records}
    if len(by_id) != len(records):
        raise GapHumanReviewError("Source record ids must be unique.")
    return by_id


def _collect_event_source_record_ids(event_id: str, event: Mapping[str, object]) -> list[str]:
    ids: list[str] = []
    if event_id == "EV-ADAM-031":
        for claim in _objects(event.get("claims"), "EV-ADAM-031.claims"):
            if claim.get("claim_id") == "ADAM-031-SNEEZE-PRAISE":
                ids.extend(_strings(claim.get("source_record_ids"), "sneeze.source_record_ids"))
    elif event_id == "EV-ADAM-071":
        synthesis = _object(event.get("supported_synthesis"), "supported_synthesis")
        ids.extend(
            _strings(
                synthesis.get("premise_source_record_ids"),
                "supported_synthesis.premise_source_record_ids",
            )
        )
        loneliness = _object(event.get("loneliness_report"), "loneliness_report")
        ids.extend(_strings(loneliness.get("source_record_ids"), "loneliness.source_record_ids"))
    elif event_id == "EV-ADAM-091":
        ids.extend(_strings(event.get("source_record_ids"), "tree.source_record_ids"))
    return list(dict.fromkeys(ids))


def build_review_packet(
    *,
    classification: Mapping[str, object],
    proposal: Mapping[str, object],
) -> dict[str, object]:
    _assert_safe(classification)
    _assert_safe(proposal)
    if classification.get("schema_version") != "siraj-source-origin-classification-v1":
        raise GapHumanReviewError("Unexpected source-origin classification schema.")
    if classification.get("status") != "SOURCE_ORIGIN_CLASSIFIED_REVIEW_PENDING":
        raise GapHumanReviewError("Source-origin classification is not review pending.")
    if classification.get("evidence_gate_status") != EVIDENCE_GATE_STATUS:
        raise GapHumanReviewError("Classification must keep the evidence gate withheld.")
    if classification.get("automatic_evidence_approval") != AUTOMATIC_APPROVAL_STATUS:
        raise GapHumanReviewError("Automatic evidence approval must remain forbidden.")
    if classification.get("human_evidence_approval") is not False:
        raise GapHumanReviewError("Classification cannot contain human evidence approval.")

    if proposal.get("schema_version") != "siraj-proposed-gap-adjudication-v1":
        raise GapHumanReviewError("Unexpected proposed adjudication schema.")
    if proposal.get("status") != "HUMAN_EVIDENCE_APPROVAL_PENDING":
        raise GapHumanReviewError("Proposed adjudication must remain approval pending.")
    if proposal.get("binding") is not False or proposal.get("opens_evidence_gate") is not False:
        raise GapHumanReviewError("Proposed adjudication cannot be binding or open the gate.")
    if proposal.get("human_approval") is not False:
        raise GapHumanReviewError("Proposal cannot contain human approval.")
    if proposal.get("classification_sha256") != canonical_json_sha256(classification):
        raise GapHumanReviewError("Proposal classification fingerprint is stale.")

    class_events = _classification_event_map(classification)
    decisions = _proposal_decision_map(proposal)
    sources = _source_record_map(classification)

    review_items: list[dict[str, object]] = []
    expected_dispositions = {
        "EV-ADAM-031": "include_assertive",
        "EV-ADAM-071": "include_qualified",
        "EV-ADAM-091": "include_qualified",
    }
    for event_id in TARGET_EVENT_IDS:
        decision = decisions[event_id]
        disposition = _required_text(decision, "proposed_disposition")
        if disposition != expected_dispositions[event_id]:
            raise GapHumanReviewError(f"Unexpected proposed disposition for {event_id}.")
        source_record_ids = _collect_event_source_record_ids(event_id, class_events[event_id])
        if not source_record_ids:
            raise GapHumanReviewError(f"No review source records for {event_id}.")
        unknown = sorted(set(source_record_ids).difference(sources))
        if unknown:
            raise GapHumanReviewError(f"Unknown source records for {event_id}: {unknown}")
        source_summaries = []
        for source_id in source_record_ids:
            source = sources[source_id]
            source_summaries.append(
                {
                    "source_record_id": source_id,
                    "work": _required_text(source, "work"),
                    "record": _required_text(source, "record"),
                    "origin_classification": _required_text(
                        source, "origin_classification"
                    ),
                    "references": _strings(source.get("references"), "references"),
                    "automatic_grade": source.get("automatic_grade"),
                }
            )
        review_items.append(
            {
                "event_id": event_id,
                "proposed_disposition": disposition,
                "proposed_narration": _required_text(decision, "proposed_narration"),
                "source_record_ids": source_record_ids,
                "source_summaries": source_summaries,
                "human_review_question": {
                    "EV-ADAM-031": (
                        "هل تعتمد إدراج عطاس آدم وحمده لله بصيغة جازمة ضمن حدود الحديث الصحيح، "
                        "مع منع أي ادعاء بالأولية؟"
                    ),
                    "EV-ADAM-071": (
                        "هل تعتمد أن حواء خُلقت من ضلع آدم استنتاجًا من المقدمتين الثابتتين، "
                        "وإيراد خبر الوحدة منسوبًا إلى بعض روايات التفسير، مع حذف التفاصيل الإسرائيلية افتراضيًا؟"
                    ),
                    "EV-ADAM-091": (
                        "هل تعتمد صيغة عدم ثبوت تعيين نوع الشجرة، مع إبقائها غير محددة بصريًا؟"
                    ),
                }[event_id],
                "human_decision": False,
                "reviewer_notes": "",
            }
        )

    fingerprint_payload = {
        "classification_sha256": canonical_json_sha256(classification),
        "proposal_sha256": canonical_json_sha256(proposal),
        "review_items": review_items,
    }
    packet = {
        "schema_version": REVIEW_PACKET_SCHEMA,
        "packet_id": "adam_gap_human_review_" + canonical_json_sha256(fingerprint_payload)[:16],
        "episode_id": "episode-001-adam",
        "status": REVIEW_PACKET_STATUS,
        "evidence_gate_status": EVIDENCE_GATE_STATUS,
        "automatic_evidence_approval": AUTOMATIC_APPROVAL_STATUS,
        "human_evidence_approval": False,
        "binding": False,
        "live_provider_execution": LIVE_EXECUTION_STATUS,
        "classification_id": classification.get("classification_id"),
        "classification_sha256": canonical_json_sha256(classification),
        "proposal_id": proposal.get("proposal_id"),
        "proposal_sha256": canonical_json_sha256(proposal),
        "evidence_binding_readiness": {
            "ready": False,
            "blocking_requirements": [
                "explicit human approval of each event decision",
                "approved source package",
                "source file checksum for each approved evidence item",
                "excerpt checksum for each approved evidence item",
                "complete adjudication for every required episode event before gate opening",
            ],
        },
        "review_items": review_items,
    }
    validate_review_packet(packet)
    return packet


def approval_template(packet: Mapping[str, object]) -> dict[str, object]:
    validate_review_packet(packet)
    decisions = []
    for item in _objects(packet.get("review_items"), "review_items"):
        decisions.append(
            {
                "event_id": _required_text(item, "event_id"),
                "proposed_disposition": _required_text(item, "proposed_disposition"),
                "approved": False,
                "human_decision": False,
                "reviewer_notes": "",
            }
        )
    template = {
        "schema_version": APPROVAL_TEMPLATE_SCHEMA,
        "status": APPROVAL_TEMPLATE_STATUS,
        "episode_id": "episode-001-adam",
        "review_packet_id": packet.get("packet_id"),
        "review_packet_sha256": canonical_json_sha256(packet),
        "approved_by": "",
        "approved_at": "",
        "human_approval": False,
        "automatic_evidence_approval": AUTOMATIC_APPROVAL_STATUS,
        "evidence_gate_status": EVIDENCE_GATE_STATUS,
        "opens_evidence_gate": False,
        "decisions": decisions,
    }
    validate_approval_template(template, packet=packet)
    return template


def validate_review_packet(payload: Mapping[str, object]) -> None:
    _assert_safe(payload)
    if payload.get("schema_version") != REVIEW_PACKET_SCHEMA:
        raise GapHumanReviewError("Unexpected review packet schema.")
    if payload.get("status") != REVIEW_PACKET_STATUS:
        raise GapHumanReviewError("Review packet status changed.")
    if payload.get("evidence_gate_status") != EVIDENCE_GATE_STATUS:
        raise GapHumanReviewError("Review packet cannot open the evidence gate.")
    if payload.get("automatic_evidence_approval") != AUTOMATIC_APPROVAL_STATUS:
        raise GapHumanReviewError("Automatic evidence approval must remain forbidden.")
    if payload.get("human_evidence_approval") is not False:
        raise GapHumanReviewError("Review packet cannot contain human approval.")
    if payload.get("binding") is not False:
        raise GapHumanReviewError("Review packet cannot be binding.")
    if payload.get("live_provider_execution") != LIVE_EXECUTION_STATUS:
        raise GapHumanReviewError("Review packet cannot enable live providers.")
    items = _objects(payload.get("review_items"), "review_items")
    ids = tuple(_required_text(item, "event_id") for item in items)
    if ids != TARGET_EVENT_IDS:
        raise GapHumanReviewError("Review packet event order changed.")
    for item in items:
        if item.get("human_decision") is not False:
            raise GapHumanReviewError("Review packet decisions must remain human-pending.")
        if not _strings(item.get("source_record_ids"), "source_record_ids"):
            raise GapHumanReviewError("Each review item requires source records.")
    readiness = _object(payload.get("evidence_binding_readiness"), "readiness")
    if readiness.get("ready") is not False:
        raise GapHumanReviewError("Review packet cannot claim binding readiness.")


def validate_approval_template(
    payload: Mapping[str, object],
    *,
    packet: Mapping[str, object] | None = None,
) -> None:
    _assert_safe(payload)
    if payload.get("schema_version") != APPROVAL_TEMPLATE_SCHEMA:
        raise GapHumanReviewError("Unexpected approval template schema.")
    if payload.get("status") != APPROVAL_TEMPLATE_STATUS:
        raise GapHumanReviewError("Approval template must remain non-approved.")
    if payload.get("approved_by") != "" or payload.get("approved_at") != "":
        raise GapHumanReviewError("Approval identity and timestamp must remain blank.")
    if payload.get("human_approval") is not False:
        raise GapHumanReviewError("Approval template cannot contain human approval.")
    if payload.get("automatic_evidence_approval") != AUTOMATIC_APPROVAL_STATUS:
        raise GapHumanReviewError("Automatic evidence approval must remain forbidden.")
    if payload.get("evidence_gate_status") != EVIDENCE_GATE_STATUS:
        raise GapHumanReviewError("Approval template cannot open the evidence gate.")
    if payload.get("opens_evidence_gate") is not False:
        raise GapHumanReviewError("Gap approval alone cannot open the evidence gate.")
    decisions = _objects(payload.get("decisions"), "decisions")
    ids = tuple(_required_text(item, "event_id") for item in decisions)
    if ids != TARGET_EVENT_IDS:
        raise GapHumanReviewError("Approval template event order changed.")
    for item in decisions:
        if item.get("approved") is not False or item.get("human_decision") is not False:
            raise GapHumanReviewError("Template decisions must remain blank/pending.")
    if packet is not None:
        validate_review_packet(packet)
        if payload.get("review_packet_id") != packet.get("packet_id"):
            raise GapHumanReviewError("Approval template references the wrong packet.")
        if payload.get("review_packet_sha256") != canonical_json_sha256(packet):
            raise GapHumanReviewError("Approval template packet fingerprint is stale.")


def load_and_build(
    *,
    classification_path: Path,
    proposal_path: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    try:
        classification = json.loads(Path(classification_path).read_text(encoding="utf-8-sig"))
        proposal = json.loads(Path(proposal_path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GapHumanReviewError("Invalid gap review input JSON.") from error
    packet = build_review_packet(
        classification=_object(classification, "classification"),
        proposal=_object(proposal, "proposal"),
    )
    return packet, approval_template(packet)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
