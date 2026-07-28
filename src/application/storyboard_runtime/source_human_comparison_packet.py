"""Build a human-comparison packet from archived Adam source material.

This stage verifies archive integrity, computes deterministic Arabic text
comparisons, isolates the best matching passage, and creates bounded human
review queues. It does not verify a source, authenticate or grade a report,
classify its origin conclusively, approve narration, open evidence gates, or
enable providers.
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

PACKET_SCHEMA = "siraj-source-human-comparison-packet-v1"
POLICY_SCHEMA = "siraj-source-human-comparison-policy-v1"
REVIEW_SCHEMA = "siraj-source-human-comparison-review-template-v1"
DIFF_SCHEMA = "siraj-source-text-comparison-v1"
ARCHIVE_SCHEMA = "siraj-source-archive-integrity-manifest-v1"
EVENT_SCHEMA = "siraj-source-comparison-event-readiness-v1"
STATUS = "HUMAN_SOURCE_COMPARISON_READY"
GATE = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTO_APPROVAL = "FORBIDDEN"
LIVE_EXECUTION = "BLOCKED"

EXPECTED_MATERIALIZATION_SCHEMA = "siraj-remote-source-materialization-v1"
EXPECTED_FETCH_SCHEMA = "siraj-remote-source-fetch-manifest-v1"
EXPECTED_EVENT_PACK_SCHEMA = "siraj-external-event-source-candidate-pack-v1"
EXPECTED_SOURCE_COUNT = 22
EXPECTED_EVENT_COUNT = 14
EXPECTED_LINK_COUNT = 28
EXPECTED_ARCHIVE_COUNT = 24
EXPECTED_STRONG_COUNT = 17
EXPECTED_PARTIAL_COUNT = 5

READY = "READY_FOR_HUMAN_CONFIRMATION"
RESOLUTION = "NEEDS_TARGETED_HUMAN_RESOLUTION"

DIACRITICS_RE = re.compile(
    r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]"
)


class SourceHumanComparisonError(ValueError):
    pass


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceHumanComparisonError(f"Invalid JSON: {path}") from exc


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


def _token_pairs(value: str) -> list[tuple[str, str]]:
    pairs = []
    for original in value.split():
        normalized = normalize_arabic(original)
        for token in normalized.split():
            if token:
                pairs.append((original, token))
    return pairs


def _multiset_difference(
    left: Sequence[str], right: Sequence[str]
) -> list[str]:
    remaining = list(right)
    result = []
    for token in left:
        try:
            remaining.remove(token)
        except ValueError:
            result.append(token)
    return result


def best_matching_window(anchor: str, extracted: str) -> dict:
    anchor_tokens = normalize_arabic(anchor).split()
    pairs = _token_pairs(extracted)
    extracted_tokens = [normalized for _, normalized in pairs]
    if not anchor_tokens or not extracted_tokens:
        return {
            "window_start_token": 0,
            "window_end_token": 0,
            "window_text": "",
            "window_normalized_text": "",
            "window_sha256": "",
            "sequence_ratio": 0.0,
            "token_recall": 0.0,
            "token_precision": 0.0,
            "token_f1": 0.0,
            "missing_anchor_tokens": list(anchor_tokens),
            "extra_window_tokens": [],
        }

    anchor_len = len(anchor_tokens)
    min_len = max(1, anchor_len // 2)
    max_len = min(
        len(extracted_tokens),
        max(anchor_len + 20, int(anchor_len * 1.8)),
    )
    lengths = sorted({
        min_len,
        max(1, int(anchor_len * 0.75)),
        anchor_len,
        min(max_len, int(anchor_len * 1.25)),
        max_len,
    })
    anchor_set = set(anchor_tokens)
    best = None
    for length in lengths:
        if length <= 0 or length > len(extracted_tokens):
            continue
        for start in range(0, len(extracted_tokens) - length + 1):
            window = extracted_tokens[start:start + length]
            window_set = set(window)
            overlap = anchor_set & window_set
            recall = len(overlap) / len(anchor_set) if anchor_set else 0.0
            precision = len(overlap) / len(window_set) if window_set else 0.0
            f1 = (
                2 * recall * precision / (recall + precision)
                if recall + precision else 0.0
            )
            ratio = difflib.SequenceMatcher(
                None, anchor_tokens, window, autojunk=False
            ).ratio()
            score = (
                recall * 0.52
                + f1 * 0.25
                + ratio * 0.23
                - abs(length - anchor_len) / max(anchor_len, 1) * 0.03
            )
            candidate = (
                round(score, 10),
                round(recall, 10),
                round(f1, 10),
                round(ratio, 10),
                -abs(length - anchor_len),
                -start,
                start,
                length,
            )
            if best is None or candidate > best:
                best = candidate

    if best is None:
        raise SourceHumanComparisonError("Unable to select comparison window.")
    start = best[-2]
    length = best[-1]
    end = start + length
    window_tokens = extracted_tokens[start:end]
    window_original = " ".join(original for original, _ in pairs[start:end])
    recall = best[1]
    f1 = best[2]
    ratio = best[3]
    overlap = set(anchor_tokens) & set(window_tokens)
    precision = (
        len(overlap) / len(set(window_tokens))
        if window_tokens else 0.0
    )
    normalized_window = " ".join(window_tokens)
    return {
        "window_start_token": start,
        "window_end_token": end,
        "window_text": window_original,
        "window_normalized_text": normalized_window,
        "window_sha256": text_sha256(window_original),
        "sequence_ratio": round(ratio, 6),
        "token_recall": round(recall, 6),
        "token_precision": round(precision, 6),
        "token_f1": round(f1, 6),
        "missing_anchor_tokens": _multiset_difference(
            anchor_tokens, window_tokens
        ),
        "extra_window_tokens": _multiset_difference(
            window_tokens, anchor_tokens
        ),
    }


def comparison_readiness(
    materialization_status: str,
    comparison: Mapping[str, object],
) -> str:
    recall = float(comparison.get("token_recall", 0))
    ratio = float(comparison.get("sequence_ratio", 0))
    if materialization_status == "FETCHED_EXTRACTED_ANCHOR_MATCH":
        return READY
    if recall >= 0.82 and ratio >= 0.62:
        return READY
    return RESOLUTION


def load_materialization(path: Path) -> dict:
    data = read_json(path)
    if not isinstance(data, Mapping):
        raise SourceHumanComparisonError(
            "Materialization must be an object."
        )
    if data.get("schema_version") != EXPECTED_MATERIALIZATION_SCHEMA:
        raise SourceHumanComparisonError(
            "Unexpected materialization schema."
        )
    sources = data.get("sources")
    if not isinstance(sources, list) or len(sources) != EXPECTED_SOURCE_COUNT:
        raise SourceHumanComparisonError(
            "Expected exactly 22 materialized sources."
        )
    if data.get("fetched_source_count") != EXPECTED_SOURCE_COUNT:
        raise SourceHumanComparisonError(
            "Expected all sources to be fetched."
        )
    if data.get("machine_extracted_source_count") != EXPECTED_SOURCE_COUNT:
        raise SourceHumanComparisonError(
            "Expected all sources to have machine extraction."
        )
    if data.get("anchor_match_source_count") != EXPECTED_STRONG_COUNT:
        raise SourceHumanComparisonError(
            "Expected 17 strong anchor matches."
        )
    if data.get("status_counts") != {
        "FETCHED_EXTRACTED_ANCHOR_MATCH": EXPECTED_STRONG_COUNT,
        "FETCHED_EXTRACTED_PARTIAL_MATCH": EXPECTED_PARTIAL_COUNT,
    }:
        raise SourceHumanComparisonError(
            "Materialization status counts changed."
        )
    if data.get("source_verification_complete") is not False:
        raise SourceHumanComparisonError(
            "Materialization unexpectedly claims verification."
        )
    return dict(data)


def load_fetch_manifest(path: Path) -> dict:
    data = read_json(path)
    if not isinstance(data, Mapping):
        raise SourceHumanComparisonError(
            "Fetch manifest must be an object."
        )
    if data.get("schema_version") != EXPECTED_FETCH_SCHEMA:
        raise SourceHumanComparisonError(
            "Unexpected fetch-manifest schema."
        )
    if data.get("archived_response_count") != EXPECTED_ARCHIVE_COUNT:
        raise SourceHumanComparisonError(
            "Expected 24 archived responses."
        )
    return dict(data)


def load_event_pack(path: Path) -> dict:
    data = read_json(path)
    if not isinstance(data, Mapping):
        raise SourceHumanComparisonError(
            "Event/source pack must be an object."
        )
    if data.get("schema_version") != EXPECTED_EVENT_PACK_SCHEMA:
        raise SourceHumanComparisonError(
            "Unexpected event/source pack schema."
        )
    if data.get("event_count") != EXPECTED_EVENT_COUNT:
        raise SourceHumanComparisonError(
            "Expected fourteen factual events."
        )
    if data.get("event_source_link_count") != EXPECTED_LINK_COUNT:
        raise SourceHumanComparisonError(
            "Expected 28 event/source links."
        )
    return dict(data)


def build_policy() -> dict:
    policy = {
        "schema_version": POLICY_SCHEMA,
        "status": "SOURCE_HUMAN_COMPARISON_POLICY_ACTIVE",
        "episode_id": "episode-001-adam",
        "human_confirmation_requirements": [
            "open the archived response or authorized source",
            "compare the approved exact excerpt character by character",
            "record surrounding context sufficient to prevent quotation drift",
            "confirm the locator and collection identity",
            "record reviewer identity and review time",
            "keep authentication and origin classification separate",
        ],
        "ready_status_meaning": (
            "Machine comparison is strong enough to make human confirmation "
            "bounded; it is not source verification."
        ),
        "resolution_status_meaning": (
            "A human must resolve wording, range, page parsing, or locator "
            "differences before confirmation."
        ),
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
        "adam_source_human_comparison_policy_"
        + canonical_sha256(policy)[:16]
    )
    validate_policy(policy)
    return policy


def build_archive_integrity(
    *, report_root: Path, fetch_manifest: Mapping[str, object]
) -> dict:
    records = []
    success_records = [
        item for item in fetch_manifest.get("records", [])
        if item.get("success")
    ]
    for item in success_records:
        relative = str(item.get("raw_archive_path", ""))
        if not relative:
            raise SourceHumanComparisonError(
                "Successful fetch record lacks archive path."
            )
        path = report_root / relative
        exists = path.is_file()
        actual_size = path.stat().st_size if exists else 0
        actual_sha = bytes_sha256(path.read_bytes()) if exists else ""
        expected_sha = str(item.get("response_sha256", ""))
        expected_size = int(item.get("response_bytes_count", 0))
        records.append({
            "source_candidate_id": item["source_candidate_id"],
            "requested_url": item["requested_url"],
            "final_url": item["final_url"],
            "raw_archive_path": relative,
            "archive_exists": exists,
            "expected_response_sha256": expected_sha,
            "actual_response_sha256": actual_sha,
            "sha256_matches": bool(
                exists and expected_sha and actual_sha == expected_sha
            ),
            "expected_response_bytes_count": expected_size,
            "actual_response_bytes_count": actual_size,
            "size_matches": bool(exists and actual_size == expected_size),
        })
    records.sort(key=lambda item: (
        item["source_candidate_id"],
        item["raw_archive_path"],
    ))
    valid = sum(
        item["archive_exists"]
        and item["sha256_matches"]
        and item["size_matches"]
        for item in records
    )
    manifest = {
        "schema_version": ARCHIVE_SCHEMA,
        "status": (
            "ARCHIVE_INTEGRITY_PASS"
            if valid == len(records)
            else "ARCHIVE_INTEGRITY_FAIL"
        ),
        "episode_id": "episode-001-adam",
        "expected_archive_count": EXPECTED_ARCHIVE_COUNT,
        "archive_record_count": len(records),
        "valid_archive_count": valid,
        "invalid_archive_count": len(records) - valid,
        "records": records,
        "source_verification_complete": False,
        "human_approval": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    manifest["archive_manifest_id"] = (
        "adam_source_archive_integrity_"
        + canonical_sha256(manifest)[:16]
    )
    validate_archive_integrity(manifest)
    return manifest


def build_comparison_packet(
    *, materialization: Mapping[str, object],
    event_pack: Mapping[str, object],
    policy: Mapping[str, object],
    archive_integrity: Mapping[str, object],
) -> tuple[dict, dict[str, dict], dict]:
    comparisons: dict[str, dict] = {}
    source_summaries = []
    for source in materialization["sources"]:
        comparison = best_matching_window(
            str(source["research_anchor_text"]),
            str(source["machine_extracted_text"]),
        )
        readiness = comparison_readiness(
            str(source["materialization_status"]), comparison
        )
        diff = {
            "schema_version": DIFF_SCHEMA,
            "episode_id": "episode-001-adam",
            "source_candidate_id": source["source_candidate_id"],
            "locator": source["locator"],
            "source_kind": source["source_kind"],
            "materialization_record_id": source[
                "materialization_record_id"
            ],
            "materialization_status": source[
                "materialization_status"
            ],
            "research_anchor_text": source["research_anchor_text"],
            "research_anchor_sha256": source[
                "research_anchor_sha256"
            ],
            "machine_extracted_text": source[
                "machine_extracted_text"
            ],
            "machine_extracted_text_sha256": source[
                "machine_extracted_text_sha256"
            ],
            "comparison": comparison,
            "comparison_readiness": readiness,
            "human_compared_to_source": False,
            "source_verified": False,
            "authentication_verified": False,
            "origin_classification_verified": False,
            "human_decision": False,
        }
        diff["comparison_id"] = (
            "source_text_comparison_"
            + canonical_sha256(diff)[:16]
        )
        comparisons[source["source_candidate_id"]] = diff
        source_summaries.append({
            "source_candidate_id": source["source_candidate_id"],
            "locator": source["locator"],
            "source_kind": source["source_kind"],
            "materialization_status": source[
                "materialization_status"
            ],
            "comparison_id": diff["comparison_id"],
            "comparison_readiness": readiness,
            "token_recall": comparison["token_recall"],
            "token_precision": comparison["token_precision"],
            "token_f1": comparison["token_f1"],
            "sequence_ratio": comparison["sequence_ratio"],
            "missing_anchor_token_count": len(
                comparison["missing_anchor_tokens"]
            ),
            "extra_window_token_count": len(
                comparison["extra_window_tokens"]
            ),
            "human_compared_to_source": False,
            "source_verified": False,
        })

    readiness_counts = dict(sorted(Counter(
        item["comparison_readiness"]
        for item in source_summaries
    ).items()))
    packet = {
        "schema_version": PACKET_SCHEMA,
        "status": STATUS,
        "episode_id": "episode-001-adam",
        "materialization_id": materialization[
            "materialization_id"
        ],
        "materialization_sha256": canonical_sha256(materialization),
        "event_pack_id": event_pack["pack_id"],
        "event_pack_sha256": canonical_sha256(event_pack),
        "policy_id": policy["policy_id"],
        "policy_sha256": canonical_sha256(policy),
        "archive_manifest_id": archive_integrity[
            "archive_manifest_id"
        ],
        "archive_manifest_sha256": canonical_sha256(
            archive_integrity
        ),
        "source_count": len(source_summaries),
        "comparison_readiness_counts": readiness_counts,
        "sources": source_summaries,
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
    packet["comparison_packet_id"] = (
        "adam_source_human_comparison_"
        + canonical_sha256(packet)[:16]
    )

    source_index = {
        item["source_candidate_id"]: item
        for item in source_summaries
    }
    events = []
    for event in event_pack["events"]:
        linked = [
            source_index[source_id]
            for source_id in event["source_candidate_ids"]
        ]
        unresolved = [
            item["source_candidate_id"]
            for item in linked
            if item["comparison_readiness"] == RESOLUTION
        ]
        events.append({
            "event_id": event["event_id"],
            "title": event["title"],
            "proposed_disposition": event[
                "proposed_disposition"
            ],
            "source_candidate_ids": list(
                event["source_candidate_ids"]
            ),
            "source_candidate_count": len(linked),
            "ready_for_human_confirmation_count": sum(
                item["comparison_readiness"] == READY
                for item in linked
            ),
            "needs_targeted_resolution_count": len(unresolved),
            "needs_targeted_resolution_source_ids": unresolved,
            "human_comparison_complete": False,
            "source_verification_complete": False,
            "event_approved": False,
        })
    event_readiness = {
        "schema_version": EVENT_SCHEMA,
        "status": "EVENT_HUMAN_COMPARISON_QUEUE_READY",
        "episode_id": "episode-001-adam",
        "comparison_packet_id": packet["comparison_packet_id"],
        "event_count": len(events),
        "event_source_link_count": sum(
            item["source_candidate_count"] for item in events
        ),
        "events": events,
        "human_comparison_complete": False,
        "source_verification_complete": False,
        "human_approval": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    validate_comparison_packet(packet)
    validate_event_readiness(event_readiness)
    return packet, comparisons, event_readiness


def build_review_template(
    *, packet: Mapping[str, object],
    comparisons: Mapping[str, Mapping[str, object]],
) -> dict:
    decisions = []
    for source in packet["sources"]:
        comparison = comparisons[source["source_candidate_id"]]
        decisions.append({
            "source_candidate_id": source["source_candidate_id"],
            "locator": source["locator"],
            "comparison_id": source["comparison_id"],
            "comparison_readiness": source[
                "comparison_readiness"
            ],
            "suggested_window_sha256": comparison[
                "comparison"
            ]["window_sha256"],
            "approved_exact_excerpt": "",
            "approved_exact_excerpt_sha256": "",
            "approved_context_before_after": "",
            "approved_locator": "",
            "human_compared_to_source": False,
            "source_verified": False,
            "authentication_verified": False,
            "origin_classification_verified": False,
            "approved": False,
            "human_decision": False,
            "verified_by": "",
            "verified_at": "",
            "reviewer_notes": "",
        })
    review = {
        "schema_version": REVIEW_SCHEMA,
        "status": "TEMPLATE_NOT_APPROVED",
        "episode_id": "episode-001-adam",
        "comparison_packet_id": packet[
            "comparison_packet_id"
        ],
        "comparison_packet_sha256": canonical_sha256(packet),
        "source_count": len(decisions),
        "decisions": decisions,
        "approved_by": "",
        "approved_at": "",
        "human_comparison_complete": False,
        "source_verification_complete": False,
        "human_approval": False,
        "full_episode_adjudication_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    validate_review_template(review)
    return review


def validate_policy(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != POLICY_SCHEMA:
        raise SourceHumanComparisonError(
            "Unexpected policy schema."
        )
    if "automatic human confirmation" not in data.get(
        "prohibitions", []
    ):
        raise SourceHumanComparisonError(
            "Automatic-confirmation prohibition missing."
        )
    _validate_guards(data)


def validate_archive_integrity(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != ARCHIVE_SCHEMA:
        raise SourceHumanComparisonError(
            "Unexpected archive-integrity schema."
        )
    if data.get("archive_record_count") != EXPECTED_ARCHIVE_COUNT:
        raise SourceHumanComparisonError(
            "Archive-integrity record count changed."
        )
    records = data.get("records")
    if not isinstance(records, list) or len(records) != EXPECTED_ARCHIVE_COUNT:
        raise SourceHumanComparisonError(
            "Expected 24 archive-integrity records."
        )
    for item in records:
        if not item.get("archive_exists"):
            raise SourceHumanComparisonError(
                "Archived source response is missing."
            )
        if not item.get("sha256_matches"):
            raise SourceHumanComparisonError(
                "Archived source checksum mismatch."
            )
        if not item.get("size_matches"):
            raise SourceHumanComparisonError(
                "Archived source size mismatch."
            )
    if data.get("status") != "ARCHIVE_INTEGRITY_PASS":
        raise SourceHumanComparisonError(
            "Archive integrity did not pass."
        )
    _validate_guards(data)


def validate_comparison_packet(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != PACKET_SCHEMA:
        raise SourceHumanComparisonError(
            "Unexpected comparison-packet schema."
        )
    if data.get("status") != STATUS:
        raise SourceHumanComparisonError(
            "Unexpected comparison-packet status."
        )
    sources = data.get("sources")
    if not isinstance(sources, list) or len(sources) != EXPECTED_SOURCE_COUNT:
        raise SourceHumanComparisonError(
            "Comparison packet must cover 22 sources."
        )
    for item in sources:
        if item.get("comparison_readiness") not in {
            READY, RESOLUTION
        }:
            raise SourceHumanComparisonError(
                "Unexpected comparison readiness."
            )
        if item.get("human_compared_to_source") is not False:
            raise SourceHumanComparisonError(
                "Packet cannot claim human comparison."
            )
        if item.get("source_verified") is not False:
            raise SourceHumanComparisonError(
                "Packet cannot verify sources."
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
        raise SourceHumanComparisonError(
            "Packet cannot claim completion or approval."
        )
    _validate_guards(data)


def validate_event_readiness(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != EVENT_SCHEMA:
        raise SourceHumanComparisonError(
            "Unexpected event-readiness schema."
        )
    events = data.get("events")
    if not isinstance(events, list) or len(events) != EXPECTED_EVENT_COUNT:
        raise SourceHumanComparisonError(
            "Event readiness must cover 14 events."
        )
    if data.get("event_source_link_count") != EXPECTED_LINK_COUNT:
        raise SourceHumanComparisonError(
            "Event readiness must contain 28 links."
        )
    for item in events:
        if item.get("human_comparison_complete") is not False:
            raise SourceHumanComparisonError(
                "Event comparison cannot be pre-complete."
            )
        if item.get("source_verification_complete") is not False:
            raise SourceHumanComparisonError(
                "Event verification cannot be pre-complete."
            )
        if item.get("event_approved") is not False:
            raise SourceHumanComparisonError(
                "Event cannot be preapproved."
            )
    _validate_guards(data)


def validate_review_template(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != REVIEW_SCHEMA:
        raise SourceHumanComparisonError(
            "Unexpected review-template schema."
        )
    if data.get("status") != "TEMPLATE_NOT_APPROVED":
        raise SourceHumanComparisonError(
            "Review template cannot be approved."
        )
    decisions = data.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != EXPECTED_SOURCE_COUNT:
        raise SourceHumanComparisonError(
            "Review template must cover 22 sources."
        )
    for item in decisions:
        blank_fields = (
            "approved_exact_excerpt",
            "approved_exact_excerpt_sha256",
            "approved_context_before_after",
            "approved_locator",
            "verified_by",
            "verified_at",
            "reviewer_notes",
        )
        if any(item.get(field) for field in blank_fields):
            raise SourceHumanComparisonError(
                "Human review fields must remain blank."
            )
        false_fields = (
            "human_compared_to_source",
            "source_verified",
            "authentication_verified",
            "origin_classification_verified",
            "approved",
            "human_decision",
        )
        if any(item.get(field) is not False for field in false_fields):
            raise SourceHumanComparisonError(
                "Review cannot claim decisions."
            )
    if data.get("approved_by") or data.get("approved_at"):
        raise SourceHumanComparisonError(
            "Reviewer metadata must remain blank."
        )
    _validate_guards(data)


def _validate_guards(data: Mapping[str, object]) -> None:
    if data.get("human_approval") not in (None, False):
        raise SourceHumanComparisonError(
            "Artifact cannot claim human approval."
        )
    if data.get("evidence_gate_status") != GATE:
        raise SourceHumanComparisonError(
            "Evidence gate must remain withheld."
        )
    if data.get("automatic_evidence_approval") != AUTO_APPROVAL:
        raise SourceHumanComparisonError(
            "Automatic approval must remain forbidden."
        )
    if data.get("live_provider_execution") != LIVE_EXECUTION:
        raise SourceHumanComparisonError(
            "Provider execution must remain blocked."
        )


def write_local_outputs(
    *,
    output_root: Path,
    packet: Mapping[str, object],
    comparisons: Mapping[str, Mapping[str, object]],
    event_readiness: Mapping[str, object],
    archive_integrity: Mapping[str, object],
    policy: Mapping[str, object],
    review: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "packet": output_root / "source-human-comparison-packet-v1.json",
        "archive": output_root / "source-archive-integrity-manifest-v1.json",
        "events": output_root / "source-comparison-event-readiness-v1.json",
        "policy": output_root / "source-human-comparison-policy-v1.json",
        "review": output_root / "source-human-comparison-review-v1.template.json",
        "queue_csv": output_root / "source-human-comparison-queue.csv",
        "partial_csv": output_root / "partial-match-resolution-queue.csv",
        "event_csv": output_root / "event-comparison-readiness.csv",
        "summary": output_root / "README.md",
    }
    write_json(outputs["packet"], packet)
    write_json(outputs["archive"], archive_integrity)
    write_json(outputs["events"], event_readiness)
    write_json(outputs["policy"], policy)
    write_json(outputs["review"], review)

    diff_root = output_root / "comparisons"
    for source_id, comparison in sorted(comparisons.items()):
        write_json(diff_root / f"{source_id}.json", comparison)

    queue_fields = (
        "source_candidate_id", "locator", "source_kind",
        "materialization_status", "comparison_readiness",
        "token_recall", "token_precision", "token_f1",
        "sequence_ratio", "missing_anchor_token_count",
        "extra_window_token_count",
    )
    with outputs["queue_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=queue_fields)
        writer.writeheader()
        for item in packet["sources"]:
            writer.writerow({key: item[key] for key in queue_fields})

    with outputs["partial_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=queue_fields)
        writer.writeheader()
        for item in packet["sources"]:
            if item["comparison_readiness"] == RESOLUTION:
                writer.writerow({key: item[key] for key in queue_fields})

    event_fields = (
        "event_id", "title", "proposed_disposition",
        "source_candidate_count",
        "ready_for_human_confirmation_count",
        "needs_targeted_resolution_count",
        "needs_targeted_resolution_source_ids",
    )
    with outputs["event_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=event_fields)
        writer.writeheader()
        for item in event_readiness["events"]:
            writer.writerow({
                **{key: item[key] for key in event_fields[:-1]},
                "needs_targeted_resolution_source_ids": ";".join(
                    item["needs_targeted_resolution_source_ids"]
                ),
            })

    dossier_root = output_root / "source-dossiers"
    dossier_root.mkdir(parents=True, exist_ok=True)
    source_index = {
        item["source_candidate_id"]: item
        for item in packet["sources"]
    }
    for source_id, comparison in sorted(comparisons.items()):
        summary = source_index[source_id]
        metrics = comparison["comparison"]
        lines = [
            f"# {source_id}",
            "",
            f"- Locator: `{summary['locator']}`",
            f"- Materialization: `{summary['materialization_status']}`",
            f"- Review route: `{summary['comparison_readiness']}`",
            f"- Token recall: {summary['token_recall']}",
            f"- Token precision: {summary['token_precision']}",
            f"- Sequence ratio: {summary['sequence_ratio']}",
            "- Human compared: no",
            "- Source verified: no",
            "",
            "## Research anchor",
            "",
            "```text",
            comparison["research_anchor_text"],
            "```",
            "",
            "## Suggested bounded window",
            "",
            "```text",
            metrics["window_text"],
            "```",
            "",
            "## Differences",
            "",
            "- Missing anchor tokens: "
            + (", ".join(metrics["missing_anchor_tokens"]) or "none"),
            "- Extra window tokens: "
            + (", ".join(metrics["extra_window_tokens"]) or "none"),
            "",
            "## Required human action",
            "",
            "Open the archived source, confirm the locator and exact wording, "
            "record sufficient surrounding context, and fill the review "
            "template. Do not mark authentication or origin classification "
            "unless separately reviewed by a qualified human.",
            "",
        ]
        (dossier_root / f"{source_id}.md").write_text(
            "\n".join(lines), encoding="utf-8", newline="\n"
        )

    batch_root = output_root / "review-batches"
    ready_ids = [
        item["source_candidate_id"]
        for item in packet["sources"]
        if item["comparison_readiness"] == READY
    ]
    resolution_ids = [
        item["source_candidate_id"]
        for item in packet["sources"]
        if item["comparison_readiness"] == RESOLUTION
    ]
    batches = [
        {
            "batch_id": "BATCH-01-QURAN-HUMAN-CONFIRMATION",
            "objective": "Compare Quran extractions with an authorized Mushaf source.",
            "source_candidate_ids": [
                source_id for source_id in ready_ids + resolution_ids
                if comparisons[source_id]["source_kind"].startswith("QURAN")
            ],
        },
        {
            "batch_id": "BATCH-02-HADITH-READY-CONFIRMATION",
            "objective": "Confirm hadith collection locators and exact Arabic text.",
            "source_candidate_ids": [
                source_id for source_id in ready_ids
                if comparisons[source_id]["source_kind"]
                == "HADITH_COLLECTION_RECORD"
            ],
        },
        {
            "batch_id": "BATCH-03-PARTIAL-MATCH-RESOLUTION",
            "objective": "Resolve partial wording, locator, or extraction differences.",
            "source_candidate_ids": resolution_ids,
        },
    ]
    for index, batch in enumerate(batches, 1):
        payload = {
            **batch,
            "source_count": len(batch["source_candidate_ids"]),
            "comparisons": [
                comparisons[source_id]
                for source_id in batch["source_candidate_ids"]
            ],
            "human_comparison_complete": False,
            "source_verification_complete": False,
            "human_approval": False,
        }
        write_json(
            batch_root / f"{index:02d}-{batch['batch_id'].lower()}.json",
            payload,
        )

    outputs["summary"].write_text(
        "# Adam Source Human Comparison Packet v1\n\n"
        f"- Archived responses validated: "
        f"{archive_integrity['valid_archive_count']}/"
        f"{archive_integrity['archive_record_count']}\n"
        f"- Sources compared: {packet['source_count']}\n"
        f"- Ready for bounded human confirmation: "
        f"{packet['comparison_readiness_counts'].get(READY, 0)}\n"
        f"- Requiring targeted resolution: "
        f"{packet['comparison_readiness_counts'].get(RESOLUTION, 0)}\n"
        f"- Events covered: {event_readiness['event_count']}\n"
        f"- Event/source links: {event_readiness['event_source_link_count']}\n"
        "- No source is human-confirmed or verified.\n"
        "- No report is graded, authenticated, or origin-classified.\n"
        "- Evidence gate remains withheld.\n",
        encoding="utf-8",
        newline="\n",
    )

    archive_path = output_root.with_suffix(".zip")
    with zipfile.ZipFile(
        archive_path, "w", zipfile.ZIP_DEFLATED
    ) as bundle:
        for path in sorted(output_root.rglob("*")):
            if path.is_file():
                bundle.write(
                    path, path.relative_to(output_root).as_posix()
                )
    outputs["zip"] = archive_path
    return outputs
