"""Ingest the approved Adam source review under delegated review policy."""
from __future__ import annotations

import hashlib
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Mapping

INGESTION_SCHEMA = "siraj-source-review-ingestion-v1"
BINDING_SCHEMA = "siraj-routine-source-binding-candidate-v1"
ESCALATION_SCHEMA = "siraj-delegated-evidence-escalation-queue-v1"
DECISION_SCHEMA = "siraj-source-review-human-decision-v1"
DELEGATION_SCHEMA = "siraj-delegated-evidence-review-policy-v1"
AUDIT_SCHEMA = "siraj-source-review-normalization-audit-v1"
EXTERNAL_PACK_SCHEMA = "siraj-external-event-source-candidate-pack-v1"

STATUS = "SOURCE_REVIEW_INGESTED"
GATE = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTO_APPROVAL = "FORBIDDEN"
LIVE_EXECUTION = "BLOCKED"

EXPECTED_SOURCE_COUNT = 22
EXPECTED_QURAN_COUNT = 11
EXPECTED_HADITH_COUNT = 11
EXPECTED_EVENT_COUNT = 14
EXPECTED_EVENT_LINK_COUNT = 28
EXPECTED_DECISION_COUNTS = {
    "confirm_with_correction": 1,
    "defer_authentication": 21,
}

USER_ESCALATION_SOURCE_IDS = (
    "SRC-ABUDAWUD-4700",
    "SRC-MUSLIM-2841",
    "SRC-TIRMIDHI-2155",
)
HIGH_IMPORTANCE_TREATMENTS = {
    "chronology_interpretation_review_required",
    "theological_interpretation_review_required",
}
QURAN_KINDS = {"QURAN_VERSE", "QURAN_VERSE_RANGE"}
HADITH_KIND = "HADITH_COLLECTION_RECORD"


class DelegatedSourceReviewError(ValueError):
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


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalized_json_document_sha256(value: object) -> str:
    # Hash deterministic JSON independent of checkout line endings.
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DelegatedSourceReviewError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise DelegatedSourceReviewError(f"Expected object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def validate_delegation_policy(policy: Mapping[str, object]) -> None:
    if policy.get("schema_version") != DELEGATION_SCHEMA:
        raise DelegatedSourceReviewError("Unexpected delegation schema.")
    if policy.get("status") != "ACTIVE_USER_DELEGATION":
        raise DelegatedSourceReviewError("Delegation is not active.")
    scope = policy.get("delegation_scope")
    if not isinstance(scope, Mapping):
        raise DelegatedSourceReviewError("Delegation scope is missing.")
    if scope.get("routine_evidence") != "AI_DECISION_AUTHORIZED":
        raise DelegatedSourceReviewError(
            "Routine evidence is not delegated."
        )
    if (
        scope.get("complex_or_high_importance_evidence")
        != "USER_REVIEW_REQUIRED"
    ):
        raise DelegatedSourceReviewError(
            "Complex evidence escalation is missing."
        )
    if policy.get("evidence_gate_status") != GATE:
        raise DelegatedSourceReviewError("Delegation cannot open the gate.")
    if policy.get("live_provider_execution") != LIVE_EXECUTION:
        raise DelegatedSourceReviewError(
            "Delegation cannot enable providers."
        )


def validate_normalization_audit(
    audit: Mapping[str, object],
    *,
    decision_sha256: str,
) -> None:
    if audit.get("schema_version") != AUDIT_SCHEMA:
        raise DelegatedSourceReviewError("Unexpected audit schema.")
    if audit.get("status") != "PASS":
        raise DelegatedSourceReviewError("Normalization audit did not pass.")
    if audit.get("source_count") != EXPECTED_SOURCE_COUNT:
        raise DelegatedSourceReviewError("Unexpected audit source count.")
    if audit.get("normalizations_applied") != 0:
        raise DelegatedSourceReviewError(
            "No decision normalization may bypass the authoritative validator."
        )
    if audit.get("rejected_normalizations") != 10:
        raise DelegatedSourceReviewError(
            "Expected ten rejected validator-incompatible normalizations."
        )
    if audit.get("output_sha256") != decision_sha256:
        raise DelegatedSourceReviewError(
            "Audit output hash does not match decision file."
        )
    if audit.get("validation_issues") != []:
        raise DelegatedSourceReviewError(
            "Normalization audit contains validation issues."
        )


def validate_human_review_document(
    decision: Mapping[str, object],
) -> None:
    if decision.get("schema_version") != DECISION_SCHEMA:
        raise DelegatedSourceReviewError("Unexpected decision schema.")
    if decision.get("status") != "HUMAN_SOURCE_REVIEW_APPROVED":
        raise DelegatedSourceReviewError("Source review is not approved.")
    if decision.get("episode_id") != "episode-001-adam":
        raise DelegatedSourceReviewError("Unexpected episode id.")
    if decision.get("source_count") != EXPECTED_SOURCE_COUNT:
        raise DelegatedSourceReviewError("Expected 22 sources.")
    if decision.get("human_approval") is not True:
        raise DelegatedSourceReviewError("Human approval is absent.")
    if decision.get("human_comparison_complete") is not True:
        raise DelegatedSourceReviewError(
            "Human comparison is not complete."
        )
    if decision.get("source_verification_complete") is not True:
        raise DelegatedSourceReviewError(
            "Source text/locator verification is not complete."
        )
    if decision.get("opens_evidence_gate") is not False:
        raise DelegatedSourceReviewError(
            "Decision document cannot open the evidence gate."
        )
    if decision.get("evidence_gate_status") != GATE:
        raise DelegatedSourceReviewError(
            "Evidence gate must remain withheld."
        )
    if decision.get("automatic_evidence_approval") != AUTO_APPROVAL:
        raise DelegatedSourceReviewError(
            "Automatic evidence approval must remain forbidden."
        )
    if decision.get("live_provider_execution") != LIVE_EXECUTION:
        raise DelegatedSourceReviewError(
            "Provider execution must remain blocked."
        )

    records = decision.get("decisions")
    if not isinstance(records, list) or len(records) != EXPECTED_SOURCE_COUNT:
        raise DelegatedSourceReviewError(
            "Decision document must contain 22 records."
        )
    ids = [record.get("source_candidate_id") for record in records]
    if len(set(ids)) != EXPECTED_SOURCE_COUNT:
        raise DelegatedSourceReviewError("Source ids are not unique.")

    counts = Counter(record.get("decision") for record in records)
    if dict(sorted(counts.items())) != EXPECTED_DECISION_COUNTS:
        raise DelegatedSourceReviewError(
            f"Unexpected decision counts: {dict(counts)}"
        )

    quran = 0
    hadith = 0
    for record in records:
        source_id = record["source_candidate_id"]
        source_kind = record.get("source_kind")
        if source_kind in QURAN_KINDS:
            quran += 1
            if record.get("decision") not in {
                "defer_authentication",
                "confirm_with_correction",
            }:
                raise DelegatedSourceReviewError(
                    f"Quran source has validator-incompatible decision: {source_id}"
                )
        elif source_kind == HADITH_KIND:
            hadith += 1
            if record.get("decision") != "defer_authentication":
                raise DelegatedSourceReviewError(
                    f"Hadith source must defer authentication: {source_id}"
                )
        else:
            raise DelegatedSourceReviewError(
                f"Unexpected source kind: {source_kind}"
            )

        if record.get("human_compared_to_source") is not True:
            raise DelegatedSourceReviewError(
                f"Human comparison absent: {source_id}"
            )
        if record.get("human_decision") is not True:
            raise DelegatedSourceReviewError(
                f"Human decision absent: {source_id}"
            )
        if record.get("source_verified") is not True:
            raise DelegatedSourceReviewError(
                f"Source text/locator unverified: {source_id}"
            )
        if not str(record.get("verified_by", "")).strip():
            raise DelegatedSourceReviewError(
                f"Reviewer identity absent: {source_id}"
            )
        if not str(record.get("verified_at", "")).strip():
            raise DelegatedSourceReviewError(
                f"Review time absent: {source_id}"
            )
        for field in (
            "authentication_verified",
            "origin_classification_verified",
            "approved_for_event_binding",
        ):
            if record.get(field) is not False:
                raise DelegatedSourceReviewError(
                    f"{field} must remain false: {source_id}"
                )
        excerpt = str(record.get("approved_exact_excerpt", ""))
        if not excerpt:
            raise DelegatedSourceReviewError(
                f"Approved excerpt absent: {source_id}"
            )
        if (
            record.get("approved_exact_excerpt_sha256")
            != text_sha256(excerpt)
        ):
            raise DelegatedSourceReviewError(
                f"Approved excerpt hash mismatch: {source_id}"
            )

    if quran != EXPECTED_QURAN_COUNT:
        raise DelegatedSourceReviewError("Expected eleven Quran sources.")
    if hadith != EXPECTED_HADITH_COUNT:
        raise DelegatedSourceReviewError("Expected eleven hadith sources.")


def validate_external_pack(pack: Mapping[str, object]) -> None:
    if pack.get("schema_version") != EXTERNAL_PACK_SCHEMA:
        raise DelegatedSourceReviewError("Unexpected external pack schema.")
    if pack.get("event_count") != EXPECTED_EVENT_COUNT:
        raise DelegatedSourceReviewError("Expected fourteen events.")
    if pack.get("event_source_link_count") != EXPECTED_EVENT_LINK_COUNT:
        raise DelegatedSourceReviewError(
            "Expected twenty-eight event/source links."
        )
    events = pack.get("events")
    if not isinstance(events, list) or len(events) != EXPECTED_EVENT_COUNT:
        raise DelegatedSourceReviewError("External event coverage is incomplete.")


def _event_index(
    pack: Mapping[str, object],
) -> tuple[dict[str, list[str]], dict[str, dict]]:
    by_source: dict[str, list[str]] = defaultdict(list)
    by_event: dict[str, dict] = {}
    for event in pack["events"]:
        event_id = event["event_id"]
        by_event[event_id] = dict(event)
        for source_id in event["source_candidate_ids"]:
            by_source[source_id].append(event_id)
    return (
        {key: sorted(value) for key, value in sorted(by_source.items())},
        dict(sorted(by_event.items())),
    )


def _source_route(record: Mapping[str, object]) -> str:
    source_id = record["source_candidate_id"]
    if record["source_kind"] in QURAN_KINDS:
        return "AI_DELEGATED_ROUTINE_EVENT_SCOPE_REVIEW"
    if source_id in USER_ESCALATION_SOURCE_IDS:
        return "USER_REVIEW_REQUIRED_HIGH_IMPORTANCE"
    return "AI_DELEGATED_AUTHENTICATION_RESEARCH"


def build_ingestion(
    *,
    decision: Mapping[str, object],
    delegation: Mapping[str, object],
    audit: Mapping[str, object],
    external_pack: Mapping[str, object],
) -> dict:
    validate_human_review_document(decision)
    validate_delegation_policy(delegation)
    validate_external_pack(external_pack)
    by_source, _ = _event_index(external_pack)

    records = []
    for item in sorted(
        decision["decisions"],
        key=lambda value: value["source_candidate_id"],
    ):
        source_id = item["source_candidate_id"]
        records.append(
            {
                "source_candidate_id": source_id,
                "source_kind": item["source_kind"],
                "decision": item["decision"],
                "approved_locator": item["approved_locator"],
                "approved_exact_excerpt_sha256": item[
                    "approved_exact_excerpt_sha256"
                ],
                "event_ids": by_source.get(source_id, []),
                "human_compared_to_source": True,
                "source_text_locator_verified": True,
                "authentication_verified": False,
                "origin_classification_verified": False,
                "event_binding_approved": False,
                "next_route": _source_route(item),
            }
        )

    ingestion = {
        "schema_version": INGESTION_SCHEMA,
        "status": STATUS,
        "episode_id": "episode-001-adam",
        "decision_document_sha256": canonical_sha256(decision),
        "delegation_policy_id": delegation["policy_id"],
        "delegation_policy_sha256": canonical_sha256(delegation),
        "normalization_audit_sha256": canonical_sha256(audit),
        "source_count": len(records),
        "quran_source_count": sum(
            item["source_kind"] in QURAN_KINDS for item in records
        ),
        "hadith_source_count": sum(
            item["source_kind"] == HADITH_KIND for item in records
        ),
        "human_source_review_approved": True,
        "source_text_locator_verification_complete": True,
        "source_authentication_complete": False,
        "origin_classification_complete": False,
        "event_binding_complete": False,
        "records": records,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    ingestion["ingestion_id"] = (
        "adam_source_review_ingestion_"
        + canonical_sha256(ingestion)[:16]
    )
    return ingestion


def build_binding_candidate(
    *,
    decision: Mapping[str, object],
    external_pack: Mapping[str, object],
    ingestion: Mapping[str, object],
) -> dict:
    by_source, by_event = _event_index(external_pack)
    decision_index = {
        item["source_candidate_id"]: item for item in decision["decisions"]
    }

    sources = []
    for source_id, item in sorted(decision_index.items()):
        if item["source_kind"] not in QURAN_KINDS:
            continue
        sources.append(
            {
                "source_candidate_id": source_id,
                "source_kind": item["source_kind"],
                "approved_locator": item["approved_locator"],
                "approved_exact_excerpt": item["approved_exact_excerpt"],
                "approved_exact_excerpt_sha256": item[
                    "approved_exact_excerpt_sha256"
                ],
                "decision": item["decision"],
                "event_ids": by_source.get(source_id, []),
                "source_text_locator_verified": True,
                "routine_delegation_applies": True,
                "event_binding_approved": False,
                "binding_status": (
                    "ROUTINE_QURAN_SOURCE_READY_FOR_EVENT_SCOPE_REVIEW"
                ),
            }
        )

    event_rows = []
    for event_id, event in by_event.items():
        quran_ids = [
            source_id
            for source_id in event["source_candidate_ids"]
            if decision_index[source_id]["source_kind"] in QURAN_KINDS
        ]
        if not quran_ids:
            continue
        treatments = sorted(
            {
                layer.get("treatment", "")
                for layer in event.get("claim_layers", [])
            }
        )
        event_rows.append(
            {
                "event_id": event_id,
                "title": event["title"],
                "quran_source_candidate_ids": sorted(quran_ids),
                "claim_treatments": treatments,
                "routine_text_locator_review_complete": True,
                "event_scope_review_complete": False,
                "event_binding_approved": False,
            }
        )

    candidate = {
        "schema_version": BINDING_SCHEMA,
        "status": "ROUTINE_QURAN_BINDING_CANDIDATE_READY",
        "episode_id": "episode-001-adam",
        "source_review_ingestion_id": ingestion["ingestion_id"],
        "source_count": len(sources),
        "event_count": len(event_rows),
        "sources": sources,
        "events": event_rows,
        "human_source_review_approved": True,
        "routine_delegation_applies": True,
        "event_scope_review_complete": False,
        "event_binding_complete": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    candidate["binding_candidate_id"] = (
        "adam_routine_source_binding_"
        + canonical_sha256(candidate)[:16]
    )
    return candidate


def build_escalation_queue(
    *,
    decision: Mapping[str, object],
    external_pack: Mapping[str, object],
    ingestion: Mapping[str, object],
) -> dict:
    by_source, by_event = _event_index(external_pack)
    decision_index = {
        item["source_candidate_id"]: item for item in decision["decisions"]
    }

    source_items = []
    for source_id, item in sorted(decision_index.items()):
        if item["source_kind"] != HADITH_KIND:
            continue
        user_required = source_id in USER_ESCALATION_SOURCE_IDS
        source_items.append(
            {
                "source_candidate_id": source_id,
                "approved_locator": item["approved_locator"],
                "approved_exact_excerpt_sha256": item[
                    "approved_exact_excerpt_sha256"
                ],
                "event_ids": by_source.get(source_id, []),
                "source_text_locator_verified": True,
                "authentication_verified": False,
                "origin_classification_verified": False,
                "route": (
                    "USER_REVIEW_REQUIRED_HIGH_IMPORTANCE"
                    if user_required
                    else "AI_DELEGATED_AUTHENTICATION_RESEARCH"
                ),
                "reason": (
                    "HIGH_IMPORTANCE_HADITH_OR_THEOLOGICAL_INTERPRETATION"
                    if user_required
                    else "ROUTINE_AUTHENTICATION_AND_CLAIM_SCOPE_RESEARCH"
                ),
            }
        )

    event_items = []
    for event_id, event in by_event.items():
        treatments = sorted(
            {
                layer.get("treatment", "")
                for layer in event.get("claim_layers", [])
            }
        )
        has_high = any(
            treatment in HIGH_IMPORTANCE_TREATMENTS
            for treatment in treatments
        )
        has_review = any(
            "review_required" in treatment
            or "pending_authority_review" in treatment
            for treatment in treatments
        )
        hadith_ids = [
            source_id
            for source_id in event["source_candidate_ids"]
            if decision_index[source_id]["source_kind"] == HADITH_KIND
        ]
        if not has_review and not hadith_ids:
            continue
        event_items.append(
            {
                "event_id": event_id,
                "title": event["title"],
                "claim_treatments": treatments,
                "hadith_source_candidate_ids": sorted(hadith_ids),
                "route": (
                    "USER_REVIEW_REQUIRED_HIGH_IMPORTANCE"
                    if has_high
                    else "AI_DELEGATED_COMPLEX_REVIEW"
                    if has_review
                    else "AI_DELEGATED_AUTHENTICATION_RESEARCH"
                ),
                "event_decision_complete": False,
            }
        )

    queue = {
        "schema_version": ESCALATION_SCHEMA,
        "status": "DELEGATED_REVIEW_QUEUE_READY",
        "episode_id": "episode-001-adam",
        "source_review_ingestion_id": ingestion["ingestion_id"],
        "hadith_source_count": len(source_items),
        "user_escalation_source_count": sum(
            item["route"] == "USER_REVIEW_REQUIRED_HIGH_IMPORTANCE"
            for item in source_items
        ),
        "ai_delegated_source_count": sum(
            item["route"] == "AI_DELEGATED_AUTHENTICATION_RESEARCH"
            for item in source_items
        ),
        "source_items": source_items,
        "event_item_count": len(event_items),
        "event_items": event_items,
        "source_authentication_complete": False,
        "complex_event_review_complete": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    queue["queue_id"] = (
        "adam_delegated_evidence_queue_"
        + canonical_sha256(queue)[:16]
    )
    return queue


def write_outputs(
    *,
    output_root: Path,
    ingestion: Mapping[str, object],
    binding: Mapping[str, object],
    escalation: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "ingestion": output_root / "source-review-ingestion-v1.json",
        "binding": output_root / "routine-source-binding-candidate-v1.json",
        "escalation": output_root / "delegated-evidence-escalation-queue-v1.json",
        "readme": output_root / "README.md",
    }
    write_json(outputs["ingestion"], ingestion)
    write_json(outputs["binding"], binding)
    write_json(outputs["escalation"], escalation)
    outputs["readme"].write_text(
        "# Adam delegated source-review ingestion v1\n\n"
        "The human-approved comparison of twenty-two source texts and "
        "locators has been ingested. Eleven Quran records are ready for "
        "delegated event-scope review. Eleven hadith records retain "
        "authentication and origin-classification guards. Three high-"
        "importance hadith matters are reserved for explicit user review; "
        "the remaining research is delegated to AI. No event binding, full "
        "episode adjudication, evidence-gate opening, or provider execution "
        "is authorized by this stage.\n",
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
