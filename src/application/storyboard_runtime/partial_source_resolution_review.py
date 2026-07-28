"""Refine partial Adam source matches and build the final human review docket.

This module consumes the local remote-source materialization report and the
source-human-comparison report. It performs deterministic fuzzy Arabic alignment
for the five partial matches, prepares bounded resolution cards and NotebookLM
prompts, and creates one blank human decision register covering all twenty-two
sources.

No automated result is a human comparison, source verification, hadith grade,
source authentication, origin classification, narration approval, evidence
approval, gate opening, or provider authorization.
"""
from __future__ import annotations

import csv
import difflib
import hashlib
import json
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Mapping, Sequence

RESOLUTION_SCHEMA = "siraj-partial-source-resolution-v1"
DOCKET_SCHEMA = "siraj-source-review-docket-v1"
DECISION_SCHEMA = "siraj-source-review-decision-template-v1"
POLICY_SCHEMA = "siraj-source-review-policy-v1"
EVENT_SCHEMA = "siraj-event-source-review-readiness-v1"
NOTEBOOKLM_SCHEMA = "siraj-source-resolution-notebooklm-prompt-pack-v1"
STATUS = "SOURCE_REVIEW_DOCKET_READY"
GATE = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTO_APPROVAL = "FORBIDDEN"
LIVE_EXECUTION = "BLOCKED"

EXPECTED_MATERIALIZATION_SCHEMA = "siraj-remote-source-materialization-v1"
EXPECTED_COMPARISON_SCHEMA = "siraj-source-human-comparison-packet-v1"
EXPECTED_DIFF_SCHEMA = "siraj-source-text-comparison-v1"
EXPECTED_EVENT_PACK_SCHEMA = "siraj-external-event-source-candidate-pack-v1"
EXPECTED_SOURCE_COUNT = 22
EXPECTED_READY_COUNT = 17
EXPECTED_PARTIAL_COUNT = 5
EXPECTED_EVENT_COUNT = 14
EXPECTED_EVENT_LINK_COUNT = 28

READY = "READY_FOR_HUMAN_CONFIRMATION"
REFINED_READY = "REFINED_READY_FOR_HUMAN_CONFIRMATION"
RESOLUTION_REQUIRED = "TARGETED_HUMAN_RESOLUTION_REQUIRED"

ALLOWED_HUMAN_DECISIONS = (
    "confirm_exact_source_text",
    "confirm_with_correction",
    "reject_locator",
    "defer_authentication",
)

DIACRITICS_RE = re.compile(
    r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]"
)


class PartialSourceResolutionError(ValueError):
    pass


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PartialSourceResolutionError(f"Invalid JSON: {path}") from exc


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def normalize_arabic(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = DIACRITICS_RE.sub("", value)
    value = value.replace("\u0640", "")
    for source, target in {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ؤ": "و", "ئ": "ي", "ة": "ه",
    }.items():
        value = value.replace(source, target)
    value = re.sub(r"[^\u0600-\u06ff0-9A-Za-z]+", " ", value)
    return " ".join(value.split()).strip()


def soft_stem(token: str) -> str:
    token = normalize_arabic(token)
    if not token:
        return ""
    prefixes = ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ك", "ل")
    suffixes = (
        "كما", "هما", "كم", "كن", "هم", "هن", "نا", "ها",
        "ات", "ون", "ين", "ان", "ه", "ي", "ك",
    )
    for prefix in prefixes:
        if token.startswith(prefix) and len(token) - len(prefix) >= 3:
            token = token[len(prefix):]
            break
    for suffix in suffixes:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            token = token[:-len(suffix)]
            break
    return token


def token_equivalence_score(left: str, right: str) -> float:
    left_norm = normalize_arabic(left)
    right_norm = normalize_arabic(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if soft_stem(left_norm) == soft_stem(right_norm):
        return 0.92
    return round(
        difflib.SequenceMatcher(
            None, left_norm, right_norm, autojunk=False
        ).ratio(),
        6,
    )


def char_ngrams(value: str, size: int = 3) -> set[str]:
    value = normalize_arabic(value).replace(" ", "")
    if not value:
        return set()
    if len(value) < size:
        return {value}
    return {
        value[index:index + size]
        for index in range(len(value) - size + 1)
    }


def char_ngram_jaccard(left: str, right: str) -> float:
    left_set = char_ngrams(left)
    right_set = char_ngrams(right)
    union = left_set | right_set
    if not union:
        return 0.0
    return round(len(left_set & right_set) / len(union), 6)


def fuzzy_token_alignment(
    anchor: str, candidate: str, threshold: float = 0.74
) -> dict:
    anchor_tokens = normalize_arabic(anchor).split()
    candidate_tokens = normalize_arabic(candidate).split()
    available = set(range(len(candidate_tokens)))
    matches = []
    missing = []
    for anchor_index, anchor_token in enumerate(anchor_tokens):
        ranked = sorted(
            (
                token_equivalence_score(
                    anchor_token, candidate_tokens[candidate_index]
                ),
                candidate_index,
            )
            for candidate_index in available
        )
        if not ranked:
            missing.append(anchor_token)
            continue
        score, candidate_index = ranked[-1]
        if score < threshold:
            missing.append(anchor_token)
            continue
        available.remove(candidate_index)
        matches.append({
            "anchor_index": anchor_index,
            "anchor_token": anchor_token,
            "candidate_index": candidate_index,
            "candidate_token": candidate_tokens[candidate_index],
            "equivalence_score": score,
        })
    recall = (
        len(matches) / len(anchor_tokens)
        if anchor_tokens else 0.0
    )
    precision = (
        len(matches) / len(candidate_tokens)
        if candidate_tokens else 0.0
    )
    f1 = (
        2 * recall * precision / (recall + precision)
        if recall + precision else 0.0
    )
    extras = [
        candidate_tokens[index] for index in sorted(available)
    ]
    ordered_indices = [
        item["candidate_index"] for item in matches
    ]
    monotonic_pairs = sum(
        ordered_indices[index] < ordered_indices[index + 1]
        for index in range(len(ordered_indices) - 1)
    )
    order_ratio = (
        monotonic_pairs / (len(ordered_indices) - 1)
        if len(ordered_indices) > 1 else (
            1.0 if ordered_indices else 0.0
        )
    )
    return {
        "anchor_token_count": len(anchor_tokens),
        "candidate_token_count": len(candidate_tokens),
        "matched_token_count": len(matches),
        "fuzzy_token_recall": round(recall, 6),
        "fuzzy_token_precision": round(precision, 6),
        "fuzzy_token_f1": round(f1, 6),
        "matched_token_order_ratio": round(order_ratio, 6),
        "matches": matches,
        "missing_anchor_tokens": missing,
        "extra_candidate_tokens": extras,
    }


def enhanced_resolution_metrics(
    anchor: str, suggested_window: str, extracted: str
) -> dict:
    candidate = suggested_window.strip() or extracted.strip()
    alignment = fuzzy_token_alignment(anchor, candidate)
    sequence_ratio = difflib.SequenceMatcher(
        None,
        normalize_arabic(anchor).split(),
        normalize_arabic(candidate).split(),
        autojunk=False,
    ).ratio()
    ngram = char_ngram_jaccard(anchor, candidate)
    weighted = (
        alignment["fuzzy_token_recall"] * 0.46
        + alignment["fuzzy_token_f1"] * 0.20
        + alignment["matched_token_order_ratio"] * 0.12
        + sequence_ratio * 0.12
        + ngram * 0.10
    )
    return {
        **alignment,
        "sequence_ratio": round(sequence_ratio, 6),
        "char_trigram_jaccard": ngram,
        "weighted_resolution_score": round(weighted, 6),
        "candidate_text": candidate,
        "candidate_text_sha256": (
            text_sha256(candidate) if candidate else ""
        ),
    }


def refined_readiness(
    original_readiness: str, metrics: Mapping[str, object]
) -> str:
    if original_readiness == READY:
        return READY
    recall = float(metrics.get("fuzzy_token_recall", 0))
    order_ratio = float(
        metrics.get("matched_token_order_ratio", 0)
    )
    weighted = float(
        metrics.get("weighted_resolution_score", 0)
    )
    ngram = float(metrics.get("char_trigram_jaccard", 0))
    if (
        recall >= 0.86
        and order_ratio >= 0.70
        and weighted >= 0.74
        and ngram >= 0.40
    ):
        return REFINED_READY
    return RESOLUTION_REQUIRED


def load_materialization(path: Path) -> dict:
    data = read_json(path)
    if not isinstance(data, Mapping):
        raise PartialSourceResolutionError(
            "Materialization must be an object."
        )
    if data.get("schema_version") != EXPECTED_MATERIALIZATION_SCHEMA:
        raise PartialSourceResolutionError(
            "Unexpected materialization schema."
        )
    if data.get("source_count") != EXPECTED_SOURCE_COUNT:
        raise PartialSourceResolutionError(
            "Expected 22 materialized sources."
        )
    if data.get("status_counts") != {
        "FETCHED_EXTRACTED_ANCHOR_MATCH": EXPECTED_READY_COUNT,
        "FETCHED_EXTRACTED_PARTIAL_MATCH": EXPECTED_PARTIAL_COUNT,
    }:
        raise PartialSourceResolutionError(
            "Materialization counts changed."
        )
    return dict(data)


def load_comparison_packet(path: Path) -> dict:
    data = read_json(path)
    if not isinstance(data, Mapping):
        raise PartialSourceResolutionError(
            "Comparison packet must be an object."
        )
    if data.get("schema_version") != EXPECTED_COMPARISON_SCHEMA:
        raise PartialSourceResolutionError(
            "Unexpected comparison packet schema."
        )
    if data.get("source_count") != EXPECTED_SOURCE_COUNT:
        raise PartialSourceResolutionError(
            "Expected 22 compared sources."
        )
    if data.get("comparison_readiness_counts") != {
        "NEEDS_TARGETED_HUMAN_RESOLUTION": EXPECTED_PARTIAL_COUNT,
        "READY_FOR_HUMAN_CONFIRMATION": EXPECTED_READY_COUNT,
    }:
        raise PartialSourceResolutionError(
            "Comparison readiness counts changed."
        )
    return dict(data)


def load_comparisons(root: Path, packet: Mapping[str, object]) -> dict[str, dict]:
    expected_ids = {
        item["source_candidate_id"] for item in packet["sources"]
    }
    comparisons = {}
    for path in sorted((root / "comparisons").glob("*.json")):
        item = read_json(path)
        if not isinstance(item, Mapping):
            raise PartialSourceResolutionError(
                f"Comparison must be an object: {path}"
            )
        if item.get("schema_version") != EXPECTED_DIFF_SCHEMA:
            raise PartialSourceResolutionError(
                f"Unexpected comparison schema: {path}"
            )
        source_id = str(item.get("source_candidate_id", ""))
        if source_id in comparisons:
            raise PartialSourceResolutionError(
                f"Duplicate comparison source: {source_id}"
            )
        comparisons[source_id] = dict(item)
    if set(comparisons) != expected_ids:
        raise PartialSourceResolutionError(
            "Comparison file coverage does not match packet."
        )
    return comparisons


def load_event_pack(path: Path) -> dict:
    data = read_json(path)
    if not isinstance(data, Mapping):
        raise PartialSourceResolutionError(
            "Event/source pack must be an object."
        )
    if data.get("schema_version") != EXPECTED_EVENT_PACK_SCHEMA:
        raise PartialSourceResolutionError(
            "Unexpected event/source pack schema."
        )
    if data.get("event_count") != EXPECTED_EVENT_COUNT:
        raise PartialSourceResolutionError(
            "Expected fourteen factual events."
        )
    if data.get("event_source_link_count") != EXPECTED_EVENT_LINK_COUNT:
        raise PartialSourceResolutionError(
            "Expected 28 event/source links."
        )
    return dict(data)


def build_policy() -> dict:
    policy = {
        "schema_version": POLICY_SCHEMA,
        "status": "SOURCE_REVIEW_POLICY_ACTIVE",
        "episode_id": "episode-001-adam",
        "allowed_human_decisions": list(
            ALLOWED_HUMAN_DECISIONS
        ),
        "decision_meanings": {
            "confirm_exact_source_text": (
                "The human compared the archived/authorized source and "
                "confirms the exact excerpt and locator."
            ),
            "confirm_with_correction": (
                "The human corrected machine text or locator and records "
                "the corrected exact excerpt and context."
            ),
            "reject_locator": (
                "The candidate locator or extracted text is not accepted "
                "for this source claim."
            ),
            "defer_authentication": (
                "Text and locator may be recorded, but authentication or "
                "origin classification remains unresolved."
            ),
        },
        "required_human_fields_for_confirmation": [
            "decision",
            "approved_locator",
            "approved_exact_excerpt",
            "approved_exact_excerpt_sha256",
            "approved_context_before_after",
            "human_compared_to_source",
            "verified_by",
            "verified_at",
        ],
        "separate_decision_layers": [
            "exact source text and locator",
            "hadith authentication",
            "source-origin classification",
            "event narration disposition",
            "episode evidence approval",
        ],
        "prohibitions": [
            "automatic human confirmation",
            "automatic source verification",
            "automatic hadith grading",
            "automatic source authentication",
            "automatic source-origin classification",
            "automatic narration disposition",
            "automatic evidence approval",
            "opening the evidence gate",
            "provider execution",
        ],
        "human_approval": False,
        "source_verification_complete": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    policy["policy_id"] = (
        "adam_source_review_policy_"
        + canonical_sha256(policy)[:16]
    )
    validate_policy(policy)
    return policy


def build_resolution_and_docket(
    *,
    materialization: Mapping[str, object],
    comparison_packet: Mapping[str, object],
    comparisons: Mapping[str, Mapping[str, object]],
    event_pack: Mapping[str, object],
    policy: Mapping[str, object],
) -> tuple[dict, dict, dict, dict]:
    materialized_index = {
        item["source_candidate_id"]: item
        for item in materialization["sources"]
    }
    packet_index = {
        item["source_candidate_id"]: item
        for item in comparison_packet["sources"]
    }
    resolution_records = []
    docket_sources = []
    for source_id in sorted(packet_index):
        packet_source = packet_index[source_id]
        comparison = comparisons[source_id]
        materialized = materialized_index[source_id]
        window = comparison["comparison"]["window_text"]
        metrics = enhanced_resolution_metrics(
            str(comparison["research_anchor_text"]),
            str(window),
            str(comparison["machine_extracted_text"]),
        )
        refined = refined_readiness(
            str(packet_source["comparison_readiness"]),
            metrics,
        )
        record = {
            "schema_version": RESOLUTION_SCHEMA,
            "episode_id": "episode-001-adam",
            "source_candidate_id": source_id,
            "locator": packet_source["locator"],
            "source_kind": packet_source["source_kind"],
            "original_materialization_status": packet_source[
                "materialization_status"
            ],
            "original_comparison_readiness": packet_source[
                "comparison_readiness"
            ],
            "comparison_id": packet_source["comparison_id"],
            "research_anchor_text": comparison[
                "research_anchor_text"
            ],
            "research_anchor_sha256": comparison[
                "research_anchor_sha256"
            ],
            "machine_extracted_text": comparison[
                "machine_extracted_text"
            ],
            "machine_extracted_text_sha256": comparison[
                "machine_extracted_text_sha256"
            ],
            "original_suggested_window": window,
            "original_suggested_window_sha256": comparison[
                "comparison"
            ]["window_sha256"],
            "enhanced_metrics": metrics,
            "refined_readiness": refined,
            "requires_targeted_human_resolution": (
                refined == RESOLUTION_REQUIRED
            ),
            "human_compared_to_source": False,
            "source_verified": False,
            "authentication_verified": False,
            "origin_classification_verified": False,
            "human_decision": False,
        }
        record["resolution_record_id"] = (
            "partial_source_resolution_"
            + canonical_sha256(record)[:16]
        )
        resolution_records.append(record)
        docket_sources.append({
            "source_candidate_id": source_id,
            "locator": packet_source["locator"],
            "source_kind": packet_source["source_kind"],
            "materialization_status": packet_source[
                "materialization_status"
            ],
            "original_comparison_readiness": packet_source[
                "comparison_readiness"
            ],
            "refined_readiness": refined,
            "resolution_record_id": record[
                "resolution_record_id"
            ],
            "suggested_exact_excerpt": metrics[
                "candidate_text"
            ],
            "suggested_exact_excerpt_sha256": metrics[
                "candidate_text_sha256"
            ],
            "allowed_human_decisions": list(
                ALLOWED_HUMAN_DECISIONS
            ),
            "human_decision": False,
            "source_verified": False,
        })

    original_partial_ids = [
        item["source_candidate_id"]
        for item in resolution_records
        if item["original_comparison_readiness"]
        == "NEEDS_TARGETED_HUMAN_RESOLUTION"
    ]
    refined_counts = dict(sorted(Counter(
        item["refined_readiness"] for item in resolution_records
    ).items()))
    unresolved_ids = [
        item["source_candidate_id"]
        for item in resolution_records
        if item["refined_readiness"] == RESOLUTION_REQUIRED
    ]
    newly_ready_ids = [
        item["source_candidate_id"]
        for item in resolution_records
        if (
            item["original_comparison_readiness"]
            == "NEEDS_TARGETED_HUMAN_RESOLUTION"
            and item["refined_readiness"] == REFINED_READY
        )
    ]

    resolution = {
        "schema_version": RESOLUTION_SCHEMA,
        "status": "PARTIAL_SOURCE_REFINEMENT_COMPLETE",
        "episode_id": "episode-001-adam",
        "materialization_id": materialization[
            "materialization_id"
        ],
        "comparison_packet_id": comparison_packet[
            "comparison_packet_id"
        ],
        "policy_id": policy["policy_id"],
        "source_count": len(resolution_records),
        "original_partial_source_count": len(
            original_partial_ids
        ),
        "original_partial_source_ids": original_partial_ids,
        "newly_ready_source_count": len(newly_ready_ids),
        "newly_ready_source_ids": newly_ready_ids,
        "remaining_resolution_source_count": len(
            unresolved_ids
        ),
        "remaining_resolution_source_ids": unresolved_ids,
        "refined_readiness_counts": refined_counts,
        "records": resolution_records,
        "human_comparison_complete": False,
        "source_verification_complete": False,
        "human_approval": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    resolution["resolution_id"] = (
        "adam_partial_source_resolution_"
        + canonical_sha256(resolution)[:16]
    )

    docket = {
        "schema_version": DOCKET_SCHEMA,
        "status": STATUS,
        "episode_id": "episode-001-adam",
        "resolution_id": resolution["resolution_id"],
        "resolution_sha256": canonical_sha256(resolution),
        "policy_id": policy["policy_id"],
        "policy_sha256": canonical_sha256(policy),
        "source_count": len(docket_sources),
        "refined_readiness_counts": refined_counts,
        "remaining_resolution_source_ids": unresolved_ids,
        "sources": docket_sources,
        "human_comparison_complete": False,
        "source_verification_complete": False,
        "human_approval": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    docket["docket_id"] = (
        "adam_source_review_docket_"
        + canonical_sha256(docket)[:16]
    )

    source_index = {
        item["source_candidate_id"]: item
        for item in docket_sources
    }
    event_rows = []
    for event in event_pack["events"]:
        linked = [
            source_index[source_id]
            for source_id in event["source_candidate_ids"]
        ]
        unresolved = [
            item["source_candidate_id"]
            for item in linked
            if item["refined_readiness"]
            == RESOLUTION_REQUIRED
        ]
        event_rows.append({
            "event_id": event["event_id"],
            "title": event["title"],
            "proposed_disposition": event[
                "proposed_disposition"
            ],
            "source_candidate_ids": list(
                event["source_candidate_ids"]
            ),
            "source_candidate_count": len(linked),
            "review_ready_source_count": sum(
                item["refined_readiness"] in {
                    READY, REFINED_READY
                }
                for item in linked
            ),
            "remaining_resolution_source_count": len(
                unresolved
            ),
            "remaining_resolution_source_ids": unresolved,
            "human_decision_complete": False,
            "event_source_verification_complete": False,
            "event_approved": False,
        })
    events = {
        "schema_version": EVENT_SCHEMA,
        "status": "EVENT_SOURCE_REVIEW_READINESS_READY",
        "episode_id": "episode-001-adam",
        "docket_id": docket["docket_id"],
        "event_count": len(event_rows),
        "event_source_link_count": sum(
            item["source_candidate_count"]
            for item in event_rows
        ),
        "events": event_rows,
        "human_comparison_complete": False,
        "source_verification_complete": False,
        "human_approval": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }

    notebook_items = []
    for source_id in unresolved_ids:
        record = next(
            item for item in resolution_records
            if item["source_candidate_id"] == source_id
        )
        notebook_items.append({
            "source_candidate_id": source_id,
            "locator": record["locator"],
            "source_kind": record["source_kind"],
            "prompt": (
                "راجع المصدر المرفق فقط وحدد النص العربي الدقيق الموافق "
                f"للموضع {record['locator']}. قارن النص بمرساة البحث "
                "والنص المستخرج، ثم أعد: (1) النص الحرفي، "
                "(2) السياق السابق واللاحق، (3) رقم الحديث أو الآية/الصفحة، "
                "(4) مواضع الاختلاف، (5) هل الاختلاف لفظي أم يغير المعنى. "
                "لا تصحح الحديث ولا تحكم على الإسناد ولا تصنف أصل الرواية."
            ),
            "research_anchor_text": record[
                "research_anchor_text"
            ],
            "machine_extracted_text": record[
                "machine_extracted_text"
            ],
            "suggested_window": record[
                "enhanced_metrics"
            ]["candidate_text"],
            "missing_anchor_tokens": record[
                "enhanced_metrics"
            ]["missing_anchor_tokens"],
            "extra_candidate_tokens": record[
                "enhanced_metrics"
            ]["extra_candidate_tokens"],
            "human_decision_required": True,
        })
    notebook = {
        "schema_version": NOTEBOOKLM_SCHEMA,
        "status": "NOTEBOOKLM_TARGETED_RESOLUTION_READY",
        "episode_id": "episode-001-adam",
        "docket_id": docket["docket_id"],
        "target_source_count": len(notebook_items),
        "items": notebook_items,
        "automatic_source_verification": False,
        "automatic_authentication": False,
        "human_approval": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }

    validate_resolution(resolution)
    validate_docket(docket)
    validate_event_readiness(events)
    validate_notebooklm(notebook)
    return resolution, docket, events, notebook


def build_decision_template(
    *, docket: Mapping[str, object],
    policy: Mapping[str, object],
) -> dict:
    decisions = []
    for source in docket["sources"]:
        decisions.append({
            "source_candidate_id": source[
                "source_candidate_id"
            ],
            "locator": source["locator"],
            "source_kind": source["source_kind"],
            "refined_readiness": source[
                "refined_readiness"
            ],
            "resolution_record_id": source[
                "resolution_record_id"
            ],
            "suggested_exact_excerpt_sha256": source[
                "suggested_exact_excerpt_sha256"
            ],
            "allowed_decisions": list(
                ALLOWED_HUMAN_DECISIONS
            ),
            "decision": "",
            "approved_locator": "",
            "approved_exact_excerpt": "",
            "approved_exact_excerpt_sha256": "",
            "approved_context_before_after": "",
            "human_compared_to_source": False,
            "source_verified": False,
            "authentication_result": "",
            "authentication_authority": "",
            "authentication_verified": False,
            "origin_classification": "",
            "origin_classification_basis": "",
            "origin_classification_verified": False,
            "approved_for_event_binding": False,
            "human_decision": False,
            "verified_by": "",
            "verified_at": "",
            "reviewer_notes": "",
        })
    template = {
        "schema_version": DECISION_SCHEMA,
        "status": "TEMPLATE_NOT_APPROVED",
        "episode_id": "episode-001-adam",
        "docket_id": docket["docket_id"],
        "docket_sha256": canonical_sha256(docket),
        "policy_id": policy["policy_id"],
        "policy_sha256": canonical_sha256(policy),
        "source_count": len(decisions),
        "decisions": decisions,
        "approved_by": "",
        "approved_at": "",
        "human_comparison_complete": False,
        "source_verification_complete": False,
        "human_approval": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    validate_decision_template(template)
    return template


def build_human_approval_text(
    *, docket: Mapping[str, object],
    decision_template: Mapping[str, object],
) -> str:
    lines = [
        "اعتماد المقارنة البشرية لمصادر حلقة آدم — قالب غير معتمد",
        "",
        f"DOCKET_ID={docket['docket_id']}",
        f"DOCKET_SHA256={canonical_sha256(docket)}",
        f"SOURCE_COUNT={docket['source_count']}",
        "",
        "نطاق القرار:",
        "- مقارنة النص والموضع للمصادر المدرجة فقط.",
        "- لا يعني تصحيح الأحاديث آليًا.",
        "- لا يعني اعتماد تصنيف أصل الروايات.",
        "- لا يعني اعتماد جميع أدلة الحلقة.",
        "- لا يفتح بوابة الأدلة.",
        "- لا يسمح بتشغيل مزودي الإنتاج.",
        "",
        "القرارات المطلوبة:",
    ]
    for item in decision_template["decisions"]:
        lines.extend([
            "",
            f"[{item['source_candidate_id']}] {item['locator']}",
            f"readiness={item['refined_readiness']}",
            "decision=<confirm_exact_source_text | "
            "confirm_with_correction | reject_locator | "
            "defer_authentication>",
            "approved_locator=",
            "approved_exact_excerpt=",
            "approved_context_before_after=",
            "authentication_result=",
            "origin_classification=",
            "reviewer_notes=",
        ])
    lines.extend([
        "",
        "عبارة الاعتماد النهائية بعد استكمال السجل:",
        "أعتمد بشريًا قرارات مقارنة النصوص والمواضع الواردة في "
        "سجل القرار المرفق ضمن نطاقه المحدد فقط، مع بقاء تصحيح "
        "الأحاديث وتصنيف أصل الروايات واعتماد أدلة الحلقة وفتح "
        "بوابة الأدلة وتشغيل مزودي الإنتاج خارج هذا الاعتماد.",
        "",
    ])
    return "\n".join(lines)


def validate_policy(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != POLICY_SCHEMA:
        raise PartialSourceResolutionError(
            "Unexpected policy schema."
        )
    if tuple(data.get("allowed_human_decisions", ())) != (
        ALLOWED_HUMAN_DECISIONS
    ):
        raise PartialSourceResolutionError(
            "Allowed decisions changed."
        )
    if "automatic human confirmation" not in data.get(
        "prohibitions", []
    ):
        raise PartialSourceResolutionError(
            "Automatic confirmation prohibition missing."
        )
    _validate_guards(data)


def validate_resolution(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != RESOLUTION_SCHEMA:
        raise PartialSourceResolutionError(
            "Unexpected resolution schema."
        )
    if data.get("source_count") != EXPECTED_SOURCE_COUNT:
        raise PartialSourceResolutionError(
            "Resolution must cover 22 sources."
        )
    if data.get("original_partial_source_count") != EXPECTED_PARTIAL_COUNT:
        raise PartialSourceResolutionError(
            "Expected five original partial sources."
        )
    records = data.get("records")
    if not isinstance(records, list) or len(records) != EXPECTED_SOURCE_COUNT:
        raise PartialSourceResolutionError(
            "Resolution records missing."
        )
    for item in records:
        if item.get("refined_readiness") not in {
            READY, REFINED_READY, RESOLUTION_REQUIRED
        }:
            raise PartialSourceResolutionError(
                "Unexpected refined readiness."
            )
        false_fields = (
            "human_compared_to_source", "source_verified",
            "authentication_verified",
            "origin_classification_verified", "human_decision",
        )
        if any(item.get(field) is not False for field in false_fields):
            raise PartialSourceResolutionError(
                "Resolution cannot claim human decisions."
            )
    if data.get("human_comparison_complete") is not False:
        raise PartialSourceResolutionError(
            "Human comparison cannot be pre-complete."
        )
    if data.get("source_verification_complete") is not False:
        raise PartialSourceResolutionError(
            "Source verification cannot be pre-complete."
        )
    if data.get("opens_evidence_gate") is not False:
        raise PartialSourceResolutionError(
            "Resolution cannot open the gate."
        )
    _validate_guards(data)


def validate_docket(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != DOCKET_SCHEMA:
        raise PartialSourceResolutionError(
            "Unexpected docket schema."
        )
    if data.get("status") != STATUS:
        raise PartialSourceResolutionError(
            "Unexpected docket status."
        )
    sources = data.get("sources")
    if not isinstance(sources, list) or len(sources) != EXPECTED_SOURCE_COUNT:
        raise PartialSourceResolutionError(
            "Docket must cover 22 sources."
        )
    for item in sources:
        if tuple(item.get("allowed_human_decisions", ())) != (
            ALLOWED_HUMAN_DECISIONS
        ):
            raise PartialSourceResolutionError(
                "Docket decision options changed."
            )
        if item.get("human_decision") is not False:
            raise PartialSourceResolutionError(
                "Docket cannot record a human decision."
            )
        if item.get("source_verified") is not False:
            raise PartialSourceResolutionError(
                "Docket cannot verify sources."
            )
    false_fields = (
        "human_comparison_complete",
        "source_verification_complete",
        "human_approval",
        "full_episode_adjudication_complete",
        "approved_evidence_package_complete",
        "opens_evidence_gate",
    )
    if any(data.get(field) is not False for field in false_fields):
        raise PartialSourceResolutionError(
            "Docket cannot claim completion."
        )
    _validate_guards(data)


def validate_event_readiness(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != EVENT_SCHEMA:
        raise PartialSourceResolutionError(
            "Unexpected event-readiness schema."
        )
    events = data.get("events")
    if not isinstance(events, list) or len(events) != EXPECTED_EVENT_COUNT:
        raise PartialSourceResolutionError(
            "Expected fourteen event rows."
        )
    if data.get("event_source_link_count") != EXPECTED_EVENT_LINK_COUNT:
        raise PartialSourceResolutionError(
            "Expected 28 event/source links."
        )
    for item in events:
        if item.get("human_decision_complete") is not False:
            raise PartialSourceResolutionError(
                "Event decision cannot be pre-complete."
            )
        if item.get("event_source_verification_complete") is not False:
            raise PartialSourceResolutionError(
                "Event verification cannot be pre-complete."
            )
        if item.get("event_approved") is not False:
            raise PartialSourceResolutionError(
                "Event cannot be preapproved."
            )
    _validate_guards(data)


def validate_notebooklm(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != NOTEBOOKLM_SCHEMA:
        raise PartialSourceResolutionError(
            "Unexpected NotebookLM schema."
        )
    items = data.get("items")
    if not isinstance(items, list):
        raise PartialSourceResolutionError(
            "NotebookLM items missing."
        )
    if data.get("target_source_count") != len(items):
        raise PartialSourceResolutionError(
            "NotebookLM target count mismatch."
        )
    for item in items:
        if item.get("human_decision_required") is not True:
            raise PartialSourceResolutionError(
                "NotebookLM output cannot replace a human decision."
            )
    if data.get("automatic_source_verification") is not False:
        raise PartialSourceResolutionError(
            "NotebookLM cannot verify sources."
        )
    if data.get("automatic_authentication") is not False:
        raise PartialSourceResolutionError(
            "NotebookLM cannot authenticate reports."
        )
    _validate_guards(data)


def validate_decision_template(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != DECISION_SCHEMA:
        raise PartialSourceResolutionError(
            "Unexpected decision-template schema."
        )
    if data.get("status") != "TEMPLATE_NOT_APPROVED":
        raise PartialSourceResolutionError(
            "Decision template cannot be approved."
        )
    decisions = data.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != EXPECTED_SOURCE_COUNT:
        raise PartialSourceResolutionError(
            "Decision template must cover 22 sources."
        )
    for item in decisions:
        blank_fields = (
            "decision", "approved_locator",
            "approved_exact_excerpt",
            "approved_exact_excerpt_sha256",
            "approved_context_before_after",
            "authentication_result",
            "authentication_authority",
            "origin_classification",
            "origin_classification_basis",
            "verified_by", "verified_at", "reviewer_notes",
        )
        if any(item.get(field) for field in blank_fields):
            raise PartialSourceResolutionError(
                "Decision fields must remain blank."
            )
        false_fields = (
            "human_compared_to_source", "source_verified",
            "authentication_verified",
            "origin_classification_verified",
            "approved_for_event_binding", "human_decision",
        )
        if any(item.get(field) is not False for field in false_fields):
            raise PartialSourceResolutionError(
                "Decision template cannot be prefilled as approved."
            )
    if data.get("approved_by") or data.get("approved_at"):
        raise PartialSourceResolutionError(
            "Approval metadata must remain blank."
        )
    _validate_guards(data)


def _validate_guards(data: Mapping[str, object]) -> None:
    if data.get("human_approval") not in (None, False):
        raise PartialSourceResolutionError(
            "Artifact cannot claim human approval."
        )
    if data.get("evidence_gate_status") != GATE:
        raise PartialSourceResolutionError(
            "Evidence gate must remain withheld."
        )
    if data.get("automatic_evidence_approval") != AUTO_APPROVAL:
        raise PartialSourceResolutionError(
            "Automatic approval must remain forbidden."
        )
    if data.get("live_provider_execution") != LIVE_EXECUTION:
        raise PartialSourceResolutionError(
            "Provider execution must remain blocked."
        )


def write_local_outputs(
    *,
    output_root: Path,
    resolution: Mapping[str, object],
    docket: Mapping[str, object],
    events: Mapping[str, object],
    notebook: Mapping[str, object],
    policy: Mapping[str, object],
    decision_template: Mapping[str, object],
    approval_text: str,
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "resolution": output_root / "partial-source-resolution-v1.json",
        "docket": output_root / "source-review-docket-v1.json",
        "events": output_root / "event-source-review-readiness-v1.json",
        "notebook": output_root / "source-resolution-notebooklm-prompt-pack-v1.json",
        "policy": output_root / "source-review-policy-v1.json",
        "decisions": output_root / "source-review-decision-v1.template.json",
        "approval": output_root / "human-approval-text.template.txt",
        "queue_csv": output_root / "source-review-decision-register.csv",
        "unresolved_csv": output_root / "targeted-resolution-source-register.csv",
        "event_csv": output_root / "event-source-review-register.csv",
        "summary": output_root / "README.md",
    }
    write_json(outputs["resolution"], resolution)
    write_json(outputs["docket"], docket)
    write_json(outputs["events"], events)
    write_json(outputs["notebook"], notebook)
    write_json(outputs["policy"], policy)
    write_json(outputs["decisions"], decision_template)
    outputs["approval"].write_text(
        approval_text, encoding="utf-8", newline="\n"
    )

    resolution_root = output_root / "resolution-records"
    for item in resolution["records"]:
        write_json(
            resolution_root / (
                item["source_candidate_id"] + ".json"
            ),
            item,
        )

    fields = (
        "source_candidate_id", "locator", "source_kind",
        "original_comparison_readiness", "refined_readiness",
        "suggested_exact_excerpt_sha256", "human_decision",
        "source_verified",
    )
    with outputs["queue_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in docket["sources"]:
            writer.writerow({key: item[key] for key in fields})

    with outputs["unresolved_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in docket["sources"]:
            if item["refined_readiness"] == RESOLUTION_REQUIRED:
                writer.writerow({key: item[key] for key in fields})

    event_fields = (
        "event_id", "title", "proposed_disposition",
        "source_candidate_count", "review_ready_source_count",
        "remaining_resolution_source_count",
        "remaining_resolution_source_ids",
    )
    with outputs["event_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=event_fields)
        writer.writeheader()
        for item in events["events"]:
            writer.writerow({
                **{
                    key: item[key]
                    for key in event_fields[:-1]
                },
                "remaining_resolution_source_ids": ";".join(
                    item["remaining_resolution_source_ids"]
                ),
            })

    card_root = output_root / "source-review-cards"
    card_root.mkdir(parents=True, exist_ok=True)
    record_index = {
        item["source_candidate_id"]: item
        for item in resolution["records"]
    }
    event_links: dict[str, list[str]] = defaultdict(list)
    for event in events["events"]:
        for source_id in event["source_candidate_ids"]:
            event_links[source_id].append(event["event_id"])
    for source in docket["sources"]:
        record = record_index[source["source_candidate_id"]]
        metrics = record["enhanced_metrics"]
        lines = [
            f"# {source['source_candidate_id']}",
            "",
            f"- Locator: `{source['locator']}`",
            f"- Type: `{source['source_kind']}`",
            f"- Original route: `{source['original_comparison_readiness']}`",
            f"- Refined route: `{source['refined_readiness']}`",
            f"- Linked events: {', '.join(event_links[source['source_candidate_id']])}",
            f"- Fuzzy recall: {metrics['fuzzy_token_recall']}",
            f"- Fuzzy F1: {metrics['fuzzy_token_f1']}",
            f"- Token order: {metrics['matched_token_order_ratio']}",
            f"- Sequence ratio: {metrics['sequence_ratio']}",
            f"- Character trigram Jaccard: {metrics['char_trigram_jaccard']}",
            f"- Weighted score: {metrics['weighted_resolution_score']}",
            "- Human compared: no",
            "- Source verified: no",
            "",
            "## Research anchor",
            "",
            "```text",
            record["research_anchor_text"],
            "```",
            "",
            "## Suggested exact-text candidate",
            "",
            "```text",
            metrics["candidate_text"],
            "```",
            "",
            "## Remaining differences",
            "",
            "- Missing anchor tokens: "
            + (", ".join(metrics["missing_anchor_tokens"]) or "none"),
            "- Extra candidate tokens: "
            + (", ".join(metrics["extra_candidate_tokens"]) or "none"),
            "",
            "## Human decision",
            "",
            "- `confirm_exact_source_text`",
            "- `confirm_with_correction`",
            "- `reject_locator`",
            "- `defer_authentication`",
            "",
            "The reviewer must open the archived or authorized source and "
            "record the exact excerpt, context, identity, and time. "
            "Authentication and origin classification remain separate.",
            "",
        ]
        (card_root / (
            source["source_candidate_id"] + ".md"
        )).write_text(
            "\n".join(lines), encoding="utf-8", newline="\n"
        )

    notebook_md = output_root / "NotebookLM-targeted-resolution-prompts.md"
    notebook_lines = [
        "# NotebookLM Targeted Source Resolution",
        "",
        "These prompts support research only. They cannot verify, authenticate, "
        "classify, or approve a source.",
        "",
    ]
    for item in notebook["items"]:
        notebook_lines.extend([
            f"## {item['source_candidate_id']} — {item['locator']}",
            "",
            item["prompt"],
            "",
            "### Research anchor",
            "",
            "```text",
            item["research_anchor_text"],
            "```",
            "",
            "### Machine extraction",
            "",
            "```text",
            item["machine_extracted_text"],
            "```",
            "",
        ])
    notebook_md.write_text(
        "\n".join(notebook_lines),
        encoding="utf-8",
        newline="\n",
    )
    outputs["notebook_md"] = notebook_md

    outputs["summary"].write_text(
        "# Adam Partial Source Resolution and Human Review Docket v1\n\n"
        f"- Sources covered: {docket['source_count']}\n"
        f"- Original partial sources: "
        f"{resolution['original_partial_source_count']}\n"
        f"- Newly ready after deterministic refinement: "
        f"{resolution['newly_ready_source_count']}\n"
        f"- Still requiring targeted human resolution: "
        f"{resolution['remaining_resolution_source_count']}\n"
        f"- Refined readiness counts: "
        f"{json.dumps(resolution['refined_readiness_counts'], ensure_ascii=False, sort_keys=True)}\n"
        f"- Events covered: {events['event_count']}\n"
        f"- Event/source links: {events['event_source_link_count']}\n"
        f"- NotebookLM targeted prompts: {notebook['target_source_count']}\n"
        "- All twenty-two human decisions remain blank.\n"
        "- No source is verified or authenticated.\n"
        "- Evidence gate remains withheld.\n",
        encoding="utf-8",
        newline="\n",
    )

    archive = output_root.with_suffix(".zip")
    with zipfile.ZipFile(
        archive, "w", zipfile.ZIP_DEFLATED
    ) as bundle:
        for path in sorted(output_root.rglob("*")):
            if path.is_file():
                bundle.write(
                    path, path.relative_to(output_root).as_posix()
                )
    outputs["archive"] = archive
    return outputs
