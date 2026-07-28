"""Deterministic structural triage for Adam non-Quran research candidates.

This layer ranks candidate usefulness for manual source verification. It does
not grade hadith, determine source origin, approve evidence, decide narration,
open evidence gates, or enable providers.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping

TRIAGE_SCHEMA = "siraj-non-quran-candidate-triage-v1"
POLICY_SCHEMA = "siraj-non-quran-candidate-triage-policy-v1"
REVIEW_SCHEMA = "siraj-non-quran-candidate-human-review-template-v1"
PLAN_SCHEMA = "siraj-non-quran-source-verification-plan-v1"
STATUS = "STRUCTURAL_TRIAGE_READY_SOURCE_VERIFICATION_PENDING"
GATE = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTO_APPROVAL = "FORBIDDEN"
LIVE_EXECUTION = "BLOCKED"

FACTUAL_EVENTS = (
    "EV-ADAM-001", "EV-ADAM-002", "EV-ADAM-003", "EV-ADAM-005",
    "EV-ADAM-007", "EV-ADAM-021", "EV-ADAM-023", "EV-ADAM-024",
    "EV-ADAM-032", "EV-ADAM-033", "EV-ADAM-042", "EV-ADAM-060",
    "EV-ADAM-061", "EV-ADAM-070",
)
EDITORIAL_EVENTS = ("EV-ADAM-099",)
TARGET_EVENTS = FACTUAL_EVENTS + EDITORIAL_EVENTS

BUCKET_LOCATOR = "SOURCE_LOCATOR_CANDIDATE"
BUCKET_MENTION = "SOURCE_MENTION_CANDIDATE"
BUCKET_NOTE = "RESEARCH_NOTE_CANDIDATE"
BUCKET_INTERNAL = "INTERNAL_ECHO"
BUCKET_EDITORIAL = "EDITORIAL_CONTEXT"
BUCKET_MANUAL = "MANUAL_REVIEW"

SOURCE_NAME_PATTERN = re.compile(
    r"(?:"
    r"صحيح\s+البخاري|البخاري|صحيح\s+مسلم|مسلم|جامع\s+الترمذي|الترمذي|"
    r"سنن\s+أبي\s+داود|أبو\s+داود|النسائي|ابن\s+ماجه|مسند\s+أحمد|"
    r"تفسير\s+الطبري|الطبري|تفسير\s+ابن\s+كثير|ابن\s+كثير|"
    r"ابن\s+أبي\s+حاتم|البيهقي|الأسماء\s+والصفات|"
    r"Sahih\s+Bukhari|Sahih\s+Muslim|Tirmidhi|Tabari|Ibn\s+Kathir"
    r")",
    re.IGNORECASE,
)
NUMBER_PATTERN = re.compile(r"\b\d{1,6}\b")
SOURCE_RECORD_PATTERN = re.compile(r"\b(?:SRCREC|QSR)-[A-Z0-9-]+\b")
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
PAGE_PATTERN = re.compile(
    r"(?:ص(?:فحة)?\.?\s*\d+|ج(?:زء)?\.?\s*\d+|"
    r"vol\.?\s*\d+|p(?:age)?\.?\s*\d+)",
    re.IGNORECASE,
)
INTERNAL_MARKERS = (
    "schema_version", "automatic_evidence_approval", "evidence_gate_status",
    "human_decision", "reviewer_notes", "binding_status", "prompt_pack_id",
    "candidate_id", "research_priority_score", "event_kind",
    "proposed_disposition", "source_record_ids", "verification_status",
)
INTERNAL_PATH_PARTS = (
    "docs/architecture/",
    "/contracts/",
    "/config/",
    "event-map.json",
    "full-episode-adjudication-inventory",
    "human-review",
    "prompt-pack",
    "review-packet",
    "blueprint",
    "storyboard",
)


class CandidateTriageError(ValueError):
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
        raise CandidateTriageError(f"Invalid JSON: {path}") from exc


def extract_locator_signals(text: str) -> dict:
    source_names = sorted(set(
        " ".join(match.group(0).split())
        for match in SOURCE_NAME_PATTERN.finditer(text)
    ))
    numbers = sorted(set(NUMBER_PATTERN.findall(text)), key=lambda x: (len(x), x))
    source_record_ids = sorted(set(SOURCE_RECORD_PATTERN.findall(text)))
    urls = sorted(set(URL_PATTERN.findall(text)))
    pages = sorted(set(
        " ".join(match.group(0).split())
        for match in PAGE_PATTERN.finditer(text)
    ))
    has_name_number_pair = bool(source_names and numbers)
    return {
        "source_names": source_names,
        "numbers": numbers[:30],
        "source_record_ids": source_record_ids,
        "urls": urls,
        "page_or_volume_markers": pages,
        "has_explicit_locator_signal": bool(
            source_record_ids or urls or pages or has_name_number_pair
        ),
    }


def _internal_echo_score(candidate: Mapping[str, object]) -> tuple[int, list[str]]:
    path = str(candidate.get("path", "")).replace("\\", "/").lower()
    excerpt = str(candidate.get("excerpt", ""))
    lowered = excerpt.lower()
    reasons = []
    score = 0
    for part in INTERNAL_PATH_PARTS:
        if part in path:
            score += 20
            reasons.append(f"internal_path:{part}")
    marker_count = sum(marker in lowered for marker in INTERNAL_MARKERS)
    if marker_count:
        score += min(marker_count * 8, 48)
        reasons.append(f"internal_markers:{marker_count}")
    matched = candidate.get("matched_tokens", [])
    if isinstance(matched, list) and matched:
        event_token_density = sum(excerpt.count(str(token)) for token in matched)
        if event_token_density >= 4:
            score += 12
            reasons.append("high_internal_token_density")
    if excerpt.lstrip().startswith(("{", "[", '"event_id"', "- event_id:")):
        score += 12
        reasons.append("structured_internal_content")
    return score, reasons


def classify_candidate(
    candidate: Mapping[str, object], *, event_kind: str
) -> dict:
    excerpt = str(candidate.get("excerpt", ""))
    if not excerpt:
        raise CandidateTriageError("Candidate excerpt is empty.")
    if text_sha256(excerpt) != candidate.get("excerpt_sha256"):
        raise CandidateTriageError("Candidate excerpt checksum mismatch.")

    signals = extract_locator_signals(excerpt)
    internal_score, internal_reasons = _internal_echo_score(candidate)
    role = str(candidate.get("artifact_role", "PROJECT_ARTIFACT"))
    source_hints = list(candidate.get("source_hints", []))
    original_priority = int(candidate.get("research_priority_score", 0))

    if event_kind == "EDITORIAL_TRANSITION":
        bucket = BUCKET_EDITORIAL
        reasons = ["event_is_editorial_transition"]
        structural_score = 0
        selectable = False
    elif internal_score >= 36 and not signals["has_explicit_locator_signal"]:
        bucket = BUCKET_INTERNAL
        reasons = internal_reasons
        structural_score = max(original_priority - internal_score, -100)
        selectable = False
    elif signals["has_explicit_locator_signal"]:
        bucket = BUCKET_LOCATOR
        reasons = ["explicit_source_locator_signal"]
        structural_score = original_priority + 55 - min(internal_score, 20)
        selectable = True
    elif source_hints and source_hints != ["INTERNAL_REFERENCE"]:
        bucket = BUCKET_MENTION
        reasons = ["source_name_or_type_mentioned_without_precise_locator"]
        structural_score = original_priority + 28 - min(internal_score, 28)
        selectable = True
    elif role in {"EVIDENCE_ARTIFACT", "RESEARCH_ARTIFACT"}:
        bucket = BUCKET_NOTE
        reasons = ["research_or_evidence_artifact_without_locator"]
        structural_score = original_priority + 10 - min(internal_score, 35)
        selectable = True
    elif internal_score >= 20:
        bucket = BUCKET_INTERNAL
        reasons = internal_reasons
        structural_score = original_priority - internal_score
        selectable = False
    else:
        bucket = BUCKET_MANUAL
        reasons = ["insufficient_structural_signal"]
        structural_score = original_priority
        selectable = True

    return {
        **dict(candidate),
        "triage_bucket": bucket,
        "triage_reasons": reasons,
        "internal_echo_score": internal_score,
        "locator_signals": signals,
        "structural_score": structural_score,
        "selected_for_source_verification_pool": selectable,
        "automatic_source_authentication": False,
        "automatic_hadith_grading": False,
        "automatic_origin_classification": False,
        "human_review_required": True,
    }


def _cluster_key(candidate: Mapping[str, object]) -> str:
    signals = candidate["locator_signals"]
    if signals["source_record_ids"]:
        return "record:" + "|".join(signals["source_record_ids"])
    if signals["urls"]:
        return "url:" + "|".join(signals["urls"])
    if signals["source_names"] and signals["numbers"]:
        return (
            "name-number:"
            + "|".join(signals["source_names"])
            + ":"
            + "|".join(signals["numbers"][:4])
        )
    return "file:" + str(candidate.get("file_sha256", ""))


def build_policy() -> dict:
    policy = {
        "schema_version": POLICY_SCHEMA,
        "status": "TRIAGE_POLICY_ACTIVE",
        "episode_id": "episode-001-adam",
        "target_event_ids": list(TARGET_EVENTS),
        "buckets": [
            BUCKET_LOCATOR, BUCKET_MENTION, BUCKET_NOTE,
            BUCKET_INTERNAL, BUCKET_EDITORIAL, BUCKET_MANUAL,
        ],
        "selection_limit_per_factual_event": 8,
        "rules": {
            "locator_candidate": (
                "source record id, URL, page/volume marker, or recognised "
                "source name combined with a number"
            ),
            "mention_candidate": (
                "source hint or source name without a precise locator"
            ),
            "research_note_candidate": (
                "evidence/research artifact lacking a precise source locator"
            ),
            "internal_echo": (
                "schema/policy/generated/editorial content without a precise "
                "source locator"
            ),
            "editorial_context": (
                "EV-ADAM-099 remains editorial_only and is excluded from "
                "factual source verification"
            ),
        },
        "prohibitions": [
            "automatic hadith grading",
            "automatic source-origin classification",
            "automatic evidence approval",
            "automatic narration disposition",
            "opening the evidence gate",
            "provider execution",
        ],
        "human_approval": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    policy["policy_id"] = (
        "adam_non_quran_triage_policy_" + canonical_sha256(policy)[:16]
    )
    validate_policy(policy)
    return policy


def build_review_template(backlog: Mapping[str, object], policy: Mapping[str, object]) -> dict:
    items = []
    for event in backlog["items"]:
        event_id = event["event_id"]
        editorial = event_id in EDITORIAL_EVENTS
        items.append({
            "event_id": event_id,
            "title": event["title"],
            "event_kind": event["event_kind"],
            "proposed_disposition": "editorial_only" if editorial else "",
            "selected_candidate_ids": [],
            "source_verification_complete": False,
            "approved": False,
            "human_decision": False,
            "reviewer_notes": "",
        })
    template = {
        "schema_version": REVIEW_SCHEMA,
        "status": "TEMPLATE_NOT_APPROVED",
        "episode_id": "episode-001-adam",
        "backlog_id": backlog["backlog_id"],
        "backlog_sha256": canonical_sha256(backlog),
        "triage_policy_id": policy["policy_id"],
        "triage_policy_sha256": canonical_sha256(policy),
        "event_count": len(items),
        "decisions": items,
        "approved_by": "",
        "approved_at": "",
        "human_approval": False,
        "full_episode_adjudication_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    validate_review_template(template)
    return template


def build_verification_plan(
    backlog: Mapping[str, object], policy: Mapping[str, object]
) -> dict:
    batches = (
        (
            "VERIFY-01-PRE-CREATION",
            FACTUAL_EVENTS[:5],
            "الأحداث السابقة لخلق آدم",
        ),
        (
            "VERIFY-02-CREATION-LIFE-KNOWLEDGE",
            FACTUAL_EVENTS[5:11],
            "خلق آدم وبداية حياته وفضل العلم",
        ),
        (
            "VERIFY-03-COVENANT-AND-SPOUSE",
            FACTUAL_EVENTS[11:],
            "الميثاق وخلق الزوج",
        ),
    )
    by_id = {item["event_id"]: item for item in backlog["items"]}
    plan_batches = []
    for batch_id, event_ids, objective in batches:
        plan_batches.append({
            "batch_id": batch_id,
            "objective": objective,
            "event_ids": list(event_ids),
            "events": [
                {
                    "event_id": event_id,
                    "title": by_id[event_id]["title"],
                    "question_ids": by_id[event_id]["question_ids"],
                }
                for event_id in event_ids
            ],
            "required_output_fields": [
                "candidate_id",
                "source_title",
                "author",
                "edition_or_database",
                "volume_page_or_record_number",
                "exact_excerpt",
                "context_before_after",
                "source_file_or_url",
                "source_file_sha256",
                "excerpt_sha256",
                "origin_candidate",
                "authentication_authority",
                "uncertainties",
            ],
            "automatic_adjudication": False,
        })
    plan = {
        "schema_version": PLAN_SCHEMA,
        "status": "SOURCE_VERIFICATION_PLAN_READY",
        "episode_id": "episode-001-adam",
        "triage_policy_id": policy["policy_id"],
        "factual_event_count": 14,
        "editorial_event_count": 1,
        "batch_count": 3,
        "batches": plan_batches,
        "editorial_event": {
            "event_id": "EV-ADAM-099",
            "research_required": False,
            "proposed_disposition": "editorial_only",
            "human_decision_required": True,
        },
        "human_approval": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    validate_verification_plan(plan)
    return plan


def load_backlog(path: Path) -> dict:
    backlog = read_json(path)
    if not isinstance(backlog, Mapping):
        raise CandidateTriageError("Backlog must be an object.")
    if backlog.get("schema_version") != "siraj-non-quran-research-backlog-v1":
        raise CandidateTriageError("Unexpected backlog schema.")
    if tuple(backlog.get("event_ids", ())) != TARGET_EVENTS:
        raise CandidateTriageError("Backlog event set changed.")
    return dict(backlog)


def load_harvest(path: Path) -> dict:
    harvest = read_json(path)
    if not isinstance(harvest, Mapping):
        raise CandidateTriageError("Harvest must be an object.")
    if harvest.get("schema_version") != "siraj-non-quran-research-harvest-v1":
        raise CandidateTriageError("Unexpected harvest schema.")
    events = harvest.get("events")
    if not isinstance(events, list):
        raise CandidateTriageError("Harvest events missing.")
    ids = tuple(item.get("event_id") for item in events if isinstance(item, Mapping))
    if ids != TARGET_EVENTS:
        raise CandidateTriageError("Harvest event set changed.")
    if harvest.get("candidate_count", 0) <= 0:
        raise CandidateTriageError("Harvest contains no candidates.")
    return dict(harvest)


def build_triage(
    *, harvest_path: Path, backlog_path: Path, top_n: int = 8
) -> tuple[dict, dict, dict, dict]:
    harvest = load_harvest(harvest_path)
    backlog = load_backlog(backlog_path)
    policy = build_policy()
    review = build_review_template(backlog, policy)
    plan = build_verification_plan(backlog, policy)

    triaged_events = []
    all_candidates = []
    cluster_members: dict[str, list[str]] = defaultdict(list)
    locator_index: dict[str, list[str]] = defaultdict(list)

    for event in harvest["events"]:
        event_id = event["event_id"]
        event_kind = event["event_kind"]
        triaged = [
            classify_candidate(candidate, event_kind=event_kind)
            for candidate in event["candidates"]
        ]
        for candidate in triaged:
            all_candidates.append(candidate)
            cluster_members[
                event_id + "::" + _cluster_key(candidate)
            ].append(candidate["candidate_id"])
            signals = candidate["locator_signals"]
            locator_values = (
                signals["source_record_ids"]
                + signals["urls"]
                + signals["page_or_volume_markers"]
            )
            if signals["source_names"] and signals["numbers"]:
                locator_values = locator_values + [
                    "source-name-number:"
                    + source_name
                    + ":"
                    + number
                    for source_name in signals["source_names"]
                    for number in signals["numbers"][:4]
                ]
            for value in locator_values:
                locator_index[value].append(candidate["candidate_id"])

        selectable = [
            candidate for candidate in triaged
            if candidate["selected_for_source_verification_pool"]
        ]
        selectable.sort(key=lambda item: (
            -item["structural_score"],
            item["path"],
            item["line_start"],
            item["candidate_id"],
        ))
        selected = selectable[:top_n]
        buckets = Counter(candidate["triage_bucket"] for candidate in triaged)
        triaged_events.append({
            "event_id": event_id,
            "title": event["title"],
            "section": event["section"],
            "event_kind": event_kind,
            "candidate_count": len(triaged),
            "bucket_counts": dict(sorted(buckets.items())),
            "selected_candidate_count": len(selected),
            "selected_candidate_ids": [
                candidate["candidate_id"] for candidate in selected
            ],
            "selected_candidates": selected,
            "all_candidates": triaged,
            "verification_readiness": (
                "EDITORIAL_HUMAN_DECISION_PENDING"
                if event_kind == "EDITORIAL_TRANSITION"
                else (
                    "LOCATOR_VERIFICATION_READY"
                    if any(
                        candidate["triage_bucket"] == BUCKET_LOCATOR
                        for candidate in selected
                    )
                    else (
                        "SOURCE_MENTION_EXTRACTION_READY"
                        if selected
                        else "MANUAL_SOURCE_DISCOVERY_REQUIRED"
                    )
                )
            ),
        })

    triage = {
        "schema_version": TRIAGE_SCHEMA,
        "status": STATUS,
        "episode_id": "episode-001-adam",
        "harvest_id": harvest["harvest_id"],
        "harvest_sha256": canonical_sha256(harvest),
        "backlog_id": backlog["backlog_id"],
        "backlog_sha256": canonical_sha256(backlog),
        "triage_policy_id": policy["policy_id"],
        "triage_policy_sha256": canonical_sha256(policy),
        "input_candidate_count": len(all_candidates),
        "event_count": len(triaged_events),
        "events": triaged_events,
        "bucket_counts": dict(sorted(Counter(
            candidate["triage_bucket"] for candidate in all_candidates
        ).items())),
        "selected_candidate_count": sum(
            event["selected_candidate_count"] for event in triaged_events
        ),
        "events_with_locator_candidates": sum(
            event["bucket_counts"].get(BUCKET_LOCATOR, 0) > 0
            for event in triaged_events
            if event["event_kind"] != "EDITORIAL_TRANSITION"
        ),
        "events_requiring_manual_source_discovery": [
            event["event_id"]
            for event in triaged_events
            if event["verification_readiness"] == "MANUAL_SOURCE_DISCOVERY_REQUIRED"
        ],
        "cluster_count": len(cluster_members),
        "human_approval": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    triage["triage_id"] = (
        "adam_non_quran_candidate_triage_" + canonical_sha256(triage)[:16]
    )
    validate_triage(triage)

    clusters = {
        "schema_version": "siraj-non-quran-candidate-cluster-index-v1",
        "triage_id": triage["triage_id"],
        "cluster_count": len(cluster_members),
        "clusters": [
            {
                "cluster_key": key,
                "candidate_ids": sorted(ids),
                "candidate_count": len(ids),
            }
            for key, ids in sorted(cluster_members.items())
        ],
    }
    locator_map = {
        "schema_version": "siraj-non-quran-locator-index-v1",
        "triage_id": triage["triage_id"],
        "locator_count": len(locator_index),
        "locators": [
            {
                "locator": locator,
                "candidate_ids": sorted(set(ids)),
            }
            for locator, ids in sorted(locator_index.items())
        ],
    }
    return triage, policy, review, plan, clusters, locator_map


def validate_policy(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != POLICY_SCHEMA:
        raise CandidateTriageError("Unexpected policy schema.")
    if tuple(data.get("target_event_ids", ())) != TARGET_EVENTS:
        raise CandidateTriageError("Policy target events changed.")
    if data.get("selection_limit_per_factual_event") != 8:
        raise CandidateTriageError("Selection limit changed.")
    _validate_guards(data)


def validate_review_template(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != REVIEW_SCHEMA:
        raise CandidateTriageError("Unexpected review schema.")
    if data.get("status") != "TEMPLATE_NOT_APPROVED":
        raise CandidateTriageError("Review template cannot be preapproved.")
    decisions = data.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != 15:
        raise CandidateTriageError("Review template must contain 15 decisions.")
    for decision in decisions:
        if decision.get("approved") is not False:
            raise CandidateTriageError("Review decision cannot be preapproved.")
        if decision.get("human_decision") is not False:
            raise CandidateTriageError("Human decision cannot be prefilled.")
        if decision.get("selected_candidate_ids"):
            raise CandidateTriageError("Candidate selections must be blank.")
        if decision.get("source_verification_complete") is not False:
            raise CandidateTriageError("Source verification cannot be prefilled.")
    if data.get("approved_by") or data.get("approved_at"):
        raise CandidateTriageError("Reviewer metadata must be blank.")
    if data.get("opens_evidence_gate") is not False:
        raise CandidateTriageError("Review template cannot open gate.")
    _validate_guards(data)


def validate_verification_plan(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != PLAN_SCHEMA:
        raise CandidateTriageError("Unexpected verification plan schema.")
    if data.get("batch_count") != 3:
        raise CandidateTriageError("Verification plan must contain three batches.")
    covered = tuple(
        event_id
        for batch in data["batches"]
        for event_id in batch["event_ids"]
    )
    if covered != FACTUAL_EVENTS:
        raise CandidateTriageError("Verification plan factual coverage changed.")
    if any(batch.get("automatic_adjudication") is not False for batch in data["batches"]):
        raise CandidateTriageError("Plan cannot authorize adjudication.")
    editorial = data.get("editorial_event", {})
    if editorial.get("event_id") != "EV-ADAM-099":
        raise CandidateTriageError("Unexpected editorial event.")
    if editorial.get("research_required") is not False:
        raise CandidateTriageError("Editorial event cannot require factual research.")
    _validate_guards(data)


def validate_triage(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != TRIAGE_SCHEMA or data.get("status") != STATUS:
        raise CandidateTriageError("Unexpected triage schema/status.")
    events = data.get("events")
    if not isinstance(events, list) or len(events) != 15:
        raise CandidateTriageError("Triage must contain 15 events.")
    ids = tuple(event["event_id"] for event in events)
    if ids != TARGET_EVENTS:
        raise CandidateTriageError("Triage event coverage changed.")
    if data.get("input_candidate_count", 0) <= 0:
        raise CandidateTriageError("Triage has no input candidates.")
    for event in events:
        if event["event_kind"] == "EDITORIAL_TRANSITION":
            if event["selected_candidate_count"] != 0:
                raise CandidateTriageError("Editorial event cannot select factual sources.")
        elif event["selected_candidate_count"] > 8:
            raise CandidateTriageError("Event selected more than eight candidates.")
        for candidate in event["all_candidates"]:
            if candidate.get("automatic_source_authentication") is not False:
                raise CandidateTriageError("Triage cannot authenticate sources.")
            if candidate.get("automatic_hadith_grading") is not False:
                raise CandidateTriageError("Triage cannot grade hadith.")
            if candidate.get("automatic_origin_classification") is not False:
                raise CandidateTriageError("Triage cannot classify origin.")
            if text_sha256(candidate["excerpt"]) != candidate["excerpt_sha256"]:
                raise CandidateTriageError("Excerpt checksum changed.")
    if data.get("full_episode_adjudication_complete") is not False:
        raise CandidateTriageError("Triage cannot complete adjudication.")
    if data.get("approved_evidence_package_complete") is not False:
        raise CandidateTriageError("Triage cannot complete evidence package.")
    _validate_guards(data)


def _validate_guards(data: Mapping[str, object]) -> None:
    if data.get("human_approval") not in (None, False):
        raise CandidateTriageError("Triage artifacts cannot claim human approval.")
    if data.get("evidence_gate_status") != GATE:
        raise CandidateTriageError("Evidence gate must remain withheld.")
    if data.get("automatic_evidence_approval") != AUTO_APPROVAL:
        raise CandidateTriageError("Automatic approval must remain forbidden.")
    if data.get("live_provider_execution") != LIVE_EXECUTION:
        raise CandidateTriageError("Provider execution must remain blocked.")


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_local_outputs(
    *, output_root: Path, triage: Mapping[str, object],
    policy: Mapping[str, object], review: Mapping[str, object],
    plan: Mapping[str, object], clusters: Mapping[str, object],
    locator_index: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "triage": output_root / "non-quran-candidate-triage-v1.json",
        "policy": output_root / "non-quran-candidate-triage-policy-v1.json",
        "review_template": output_root / "non-quran-candidate-human-review-v1.template.json",
        "verification_plan": output_root / "non-quran-source-verification-plan-v1.json",
        "cluster_index": output_root / "candidate-cluster-index-v1.json",
        "locator_index": output_root / "source-locator-index-v1.json",
        "ranking_csv": output_root / "candidate-ranking.csv",
        "exclusion_csv": output_root / "candidate-exclusion-ledger.csv",
        "summary": output_root / "README.md",
    }
    write_json(outputs["triage"], triage)
    write_json(outputs["policy"], policy)
    write_json(outputs["review_template"], review)
    write_json(outputs["verification_plan"], plan)
    write_json(outputs["cluster_index"], clusters)
    write_json(outputs["locator_index"], locator_index)

    fields = (
        "event_id", "candidate_id", "triage_bucket", "structural_score",
        "artifact_role", "path", "line_start", "line_end",
        "selected_for_source_verification_pool",
    )
    with outputs["ranking_csv"].open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for event in triage["events"]:
            for candidate in sorted(
                event["all_candidates"],
                key=lambda item: (
                    -item["structural_score"],
                    item["candidate_id"],
                ),
            ):
                writer.writerow({
                    key: (
                        event["event_id"] if key == "event_id"
                        else candidate.get(key)
                    )
                    for key in fields
                })

    exclusion_fields = (
        "event_id", "candidate_id", "triage_bucket", "path",
        "internal_echo_score", "triage_reasons",
    )
    with outputs["exclusion_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=exclusion_fields)
        writer.writeheader()
        for event in triage["events"]:
            for candidate in event["all_candidates"]:
                if candidate["triage_bucket"] not in {
                    BUCKET_INTERNAL, BUCKET_EDITORIAL
                }:
                    continue
                writer.writerow({
                    "event_id": event["event_id"],
                    "candidate_id": candidate["candidate_id"],
                    "triage_bucket": candidate["triage_bucket"],
                    "path": candidate["path"],
                    "internal_echo_score": candidate["internal_echo_score"],
                    "triage_reasons": ";".join(candidate["triage_reasons"]),
                })

    dossier_dir = output_root / "event-dossiers"
    dossier_dir.mkdir(parents=True, exist_ok=True)
    for event in triage["events"]:
        lines = [
            f"# {event['event_id']} — {event['title']}",
            "",
            f"- Section: {event['section']}",
            f"- Kind: {event['event_kind']}",
            f"- Input candidates: {event['candidate_count']}",
            f"- Selected candidates: {event['selected_candidate_count']}",
            f"- Readiness: {event['verification_readiness']}",
            f"- Buckets: {json.dumps(event['bucket_counts'], ensure_ascii=False)}",
            "",
        ]
        for index, candidate in enumerate(event["selected_candidates"], 1):
            signals = candidate["locator_signals"]
            lines.extend([
                f"## Selected candidate {index}",
                "",
                f"- Candidate ID: `{candidate['candidate_id']}`",
                f"- Bucket: `{candidate['triage_bucket']}`",
                f"- Structural score: {candidate['structural_score']}",
                f"- Path: `{candidate['path']}`",
                f"- Lines: {candidate['line_start']}-{candidate['line_end']}",
                f"- Source names: {', '.join(signals['source_names']) or 'none'}",
                f"- Numbers: {', '.join(signals['numbers']) or 'none'}",
                f"- Source record IDs: {', '.join(signals['source_record_ids']) or 'none'}",
                f"- URLs: {', '.join(signals['urls']) or 'none'}",
                f"- Excerpt SHA-256: `{candidate['excerpt_sha256']}`",
                "",
                "```text",
                candidate["excerpt"],
                "```",
                "",
            ])
        (dossier_dir / f"{event['event_id']}.md").write_text(
            "\n".join(lines), encoding="utf-8", newline="\n"
        )

    batch_dir = output_root / "verification-batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    selected_by_event = {
        event["event_id"]: event["selected_candidates"]
        for event in triage["events"]
    }
    for index, batch in enumerate(plan["batches"], 1):
        payload = {
            **batch,
            "selected_candidates": {
                event_id: [
                    {
                        "candidate_id": candidate["candidate_id"],
                        "triage_bucket": candidate["triage_bucket"],
                        "path": candidate["path"],
                        "line_start": candidate["line_start"],
                        "line_end": candidate["line_end"],
                        "locator_signals": candidate["locator_signals"],
                        "excerpt": candidate["excerpt"],
                        "excerpt_sha256": candidate["excerpt_sha256"],
                    }
                    for candidate in selected_by_event[event_id]
                ]
                for event_id in batch["event_ids"]
            },
            "instruction": (
                "تحقق من المصادر الأصلية لكل مرشح. لا تعتمد ملخص المشروع نفسه "
                "دليلًا. لا تحكم بصحة حديث دون سلطة تخريج معتمدة، وسجّل النص "
                "والسياق والموضع والبصمات وعدم اليقين لكل حدث مستقلًا."
            ),
        }
        write_json(
            batch_dir / f"{index:02d}-{batch['batch_id'].lower()}.json",
            payload,
        )

    outputs["summary"].write_text(
        "# Adam Non-Quran Candidate Triage v1\n\n"
        f"- Input candidates: {triage['input_candidate_count']}\n"
        f"- Selected for source verification: {triage['selected_candidate_count']}\n"
        f"- Events with locator candidates: {triage['events_with_locator_candidates']}\n"
        f"- Manual source discovery events: "
        f"{len(triage['events_requiring_manual_source_discovery'])}\n"
        f"- Structural clusters: {triage['cluster_count']}\n"
        "- Triage buckets do not authenticate sources or grade reports.\n"
        "- Evidence gate remains withheld.\n",
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
