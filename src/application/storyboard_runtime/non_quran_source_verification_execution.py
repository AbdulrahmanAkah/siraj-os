"""Build an execution-ready source-verification queue for Adam candidates.

This stage consolidates structurally selected local candidates into canonical
verification representatives, creates per-candidate verification records, and
routes every unresolved factual event to locator verification, source-mention
expansion, or focused source discovery. It never authenticates sources, grades
reports, records human approval, opens evidence gates, or enables providers.
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

EXECUTION_SCHEMA = "siraj-non-quran-source-verification-execution-v1"
POLICY_SCHEMA = "siraj-source-verification-acceptance-policy-v1"
REVIEW_SCHEMA = "siraj-source-verification-human-review-template-v1"
RECORD_SCHEMA = "siraj-source-verification-record-template-v1"
STATUS = "SOURCE_VERIFICATION_EXECUTION_READY"
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

ROUTE_LOCATOR = "LOCATOR_VERIFICATION"
ROUTE_MENTION = "SOURCE_MENTION_EXPANSION"
ROUTE_DISCOVERY = "FOCUSED_SOURCE_DISCOVERY"
ROUTE_EDITORIAL = "EDITORIAL_HUMAN_DECISION"

BUCKET_LOCATOR = "SOURCE_LOCATOR_CANDIDATE"
BUCKET_MENTION = "SOURCE_MENTION_CANDIDATE"
BUCKET_NOTE = "RESEARCH_NOTE_CANDIDATE"
BUCKET_MANUAL = "MANUAL_REVIEW"
BUCKET_EDITORIAL = "EDITORIAL_CONTEXT"

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
EVENT_RE = re.compile(r"^EV-ADAM-\d{3}$")


class VerificationExecutionError(ValueError):
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
        raise VerificationExecutionError(f"Invalid JSON: {path}") from exc


def load_triage(path: Path) -> dict:
    triage = read_json(path)
    if not isinstance(triage, Mapping):
        raise VerificationExecutionError("Triage must be an object.")
    if triage.get("schema_version") != "siraj-non-quran-candidate-triage-v1":
        raise VerificationExecutionError("Unexpected triage schema.")
    if triage.get("status") != (
        "STRUCTURAL_TRIAGE_READY_SOURCE_VERIFICATION_PENDING"
    ):
        raise VerificationExecutionError("Unexpected triage status.")
    events = triage.get("events")
    if not isinstance(events, list):
        raise VerificationExecutionError("Triage events missing.")
    ids = tuple(
        item.get("event_id") for item in events if isinstance(item, Mapping)
    )
    if ids != TARGET_EVENTS:
        raise VerificationExecutionError("Triage event coverage changed.")
    if triage.get("input_candidate_count", 0) <= 0:
        raise VerificationExecutionError("Triage has no candidates.")
    if triage.get("selected_candidate_count", 0) <= 0:
        raise VerificationExecutionError("Triage selected no candidates.")
    if triage.get("human_approval") is not False:
        raise VerificationExecutionError("Triage unexpectedly claims approval.")
    return dict(triage)


def load_backlog(path: Path) -> dict:
    backlog = read_json(path)
    if not isinstance(backlog, Mapping):
        raise VerificationExecutionError("Backlog must be an object.")
    if backlog.get("schema_version") != "siraj-non-quran-research-backlog-v1":
        raise VerificationExecutionError("Unexpected backlog schema.")
    if tuple(backlog.get("event_ids", ())) != TARGET_EVENTS:
        raise VerificationExecutionError("Backlog event coverage changed.")
    return dict(backlog)


def load_verification_plan(path: Path) -> dict:
    plan = read_json(path)
    if not isinstance(plan, Mapping):
        raise VerificationExecutionError("Verification plan must be an object.")
    if plan.get("schema_version") != (
        "siraj-non-quran-source-verification-plan-v1"
    ):
        raise VerificationExecutionError("Unexpected verification-plan schema.")
    if plan.get("batch_count") != 3:
        raise VerificationExecutionError("Expected three verification batches.")
    covered = tuple(
        event_id
        for batch in plan.get("batches", [])
        for event_id in batch.get("event_ids", [])
    )
    if covered != FACTUAL_EVENTS:
        raise VerificationExecutionError("Verification-plan coverage changed.")
    return dict(plan)


def _clean_values(values: object) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(sorted({
        " ".join(str(value).split())
        for value in values
        if str(value).strip()
    }))


def verification_key(candidate: Mapping[str, object]) -> str:
    signals = candidate.get("locator_signals")
    if not isinstance(signals, Mapping):
        raise VerificationExecutionError("Candidate locator signals missing.")
    record_ids = _clean_values(signals.get("source_record_ids"))
    urls = _clean_values(signals.get("urls"))
    pages = _clean_values(signals.get("page_or_volume_markers"))
    names = _clean_values(signals.get("source_names"))
    numbers = _clean_values(signals.get("numbers"))
    if record_ids:
        return "source-record:" + "|".join(record_ids)
    if urls:
        return "url:" + "|".join(urls)
    if pages and names:
        return "source-page:" + "|".join(names) + ":" + "|".join(pages)
    if names and numbers:
        return "source-number:" + "|".join(names) + ":" + "|".join(numbers[:6])
    if names:
        return "source-name:" + "|".join(names)
    normalised = str(candidate.get("normalised_excerpt_sha256", ""))
    if SHA_RE.fullmatch(normalised):
        return "excerpt:" + normalised
    excerpt = str(candidate.get("excerpt", ""))
    if not excerpt:
        raise VerificationExecutionError("Candidate excerpt missing.")
    return "excerpt:" + text_sha256(" ".join(excerpt.split()))


def _candidate_sort_key(candidate: Mapping[str, object]) -> tuple:
    bucket_rank = {
        BUCKET_LOCATOR: 0,
        BUCKET_MENTION: 1,
        BUCKET_NOTE: 2,
        BUCKET_MANUAL: 3,
        BUCKET_EDITORIAL: 9,
    }.get(str(candidate.get("triage_bucket")), 8)
    return (
        bucket_rank,
        -int(candidate.get("structural_score", 0)),
        str(candidate.get("path", "")),
        int(candidate.get("line_start", 0)),
        str(candidate.get("candidate_id", "")),
    )


def consolidate_selected_candidates(
    triage: Mapping[str, object],
) -> tuple[list[dict], list[dict]]:
    representatives: list[dict] = []
    duplicate_ledger: list[dict] = []
    for event in triage["events"]:
        event_id = str(event["event_id"])
        selected = event.get("selected_candidates")
        if not isinstance(selected, list):
            raise VerificationExecutionError(
                f"Selected candidates missing for {event_id}."
            )
        if event_id in EDITORIAL_EVENTS:
            if selected:
                raise VerificationExecutionError(
                    "Editorial event cannot contain selected factual candidates."
                )
            continue
        groups: dict[str, list[dict]] = defaultdict(list)
        for candidate in selected:
            if not isinstance(candidate, Mapping):
                raise VerificationExecutionError("Candidate must be an object.")
            if candidate.get("event_id") != event_id:
                raise VerificationExecutionError("Candidate/event mismatch.")
            excerpt = str(candidate.get("excerpt", ""))
            if text_sha256(excerpt) != candidate.get("excerpt_sha256"):
                raise VerificationExecutionError("Candidate excerpt checksum mismatch.")
            if candidate.get("automatic_source_authentication") is not False:
                raise VerificationExecutionError(
                    "Candidate unexpectedly claims source authentication."
                )
            groups[verification_key(candidate)].append(dict(candidate))

        for key, members in sorted(groups.items()):
            members.sort(key=_candidate_sort_key)
            representative = dict(members[0])
            representative_id = str(representative["candidate_id"])
            representative.update({
                "verification_key": key,
                "representative_candidate_id": representative_id,
                "duplicate_candidate_ids": [
                    str(item["candidate_id"]) for item in members[1:]
                ],
                "duplicate_count": len(members) - 1,
                "source_verified": False,
                "authentication_verified": False,
                "origin_classification_verified": False,
                "human_decision": False,
            })
            representatives.append(representative)
            for duplicate in members[1:]:
                duplicate_ledger.append({
                    "event_id": event_id,
                    "verification_key": key,
                    "representative_candidate_id": representative_id,
                    "duplicate_candidate_id": duplicate["candidate_id"],
                    "duplicate_path": duplicate["path"],
                    "duplicate_excerpt_sha256": duplicate["excerpt_sha256"],
                    "deduplication_basis": "same_event_and_verification_key",
                })
    representatives.sort(key=lambda item: (
        int(str(item["event_id"]).rsplit("-", 1)[1]),
        _candidate_sort_key(item),
    ))
    duplicate_ledger.sort(key=lambda item: (
        item["event_id"], item["verification_key"],
        item["duplicate_candidate_id"],
    ))
    return representatives, duplicate_ledger


def determine_route(event_id: str, candidates: Iterable[Mapping[str, object]]) -> str:
    if event_id in EDITORIAL_EVENTS:
        return ROUTE_EDITORIAL
    buckets = {str(item.get("triage_bucket")) for item in candidates}
    if BUCKET_LOCATOR in buckets:
        return ROUTE_LOCATOR
    if BUCKET_MENTION in buckets:
        return ROUTE_MENTION
    return ROUTE_DISCOVERY


def build_policy() -> dict:
    policy = {
        "schema_version": POLICY_SCHEMA,
        "status": "SOURCE_VERIFICATION_POLICY_ACTIVE",
        "episode_id": "episode-001-adam",
        "accepted_record_schema": RECORD_SCHEMA,
        "required_fields_for_source_verified": [
            "source_title",
            "author",
            "edition_or_database",
            "volume_page_or_record_number",
            "exact_excerpt",
            "context_before_after",
            "source_file_or_url",
            "source_material_sha256",
            "exact_excerpt_sha256",
            "verification_method",
            "verified_by",
            "verified_at",
        ],
        "additional_fields_for_authenticated_reports": [
            "authentication_authority",
            "authentication_result",
            "authentication_locator",
        ],
        "origin_classification_allowed_values": [
            "authentic_sunnah",
            "accepted_athar",
            "scholarly_interpretation",
            "disputed_view",
            "historical_report",
            "israiliyyat",
            "weak_report",
            "unresolved",
        ],
        "verification_methods": [
            "authorized_local_source_file",
            "authorized_database_record",
            "human_compared_print_edition",
        ],
        "prohibitions": [
            "accepting internal project summaries as original evidence",
            "automatic hadith grading",
            "automatic source authentication",
            "automatic source-origin classification",
            "automatic narration disposition",
            "automatic evidence approval",
            "opening the evidence gate",
            "provider execution",
        ],
        "human_approval": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    policy["policy_id"] = (
        "adam_source_verification_policy_" + canonical_sha256(policy)[:16]
    )
    validate_policy(policy)
    return policy


def build_record_template(
    *, event_id: str, event_title: str, candidate: Mapping[str, object],
    route: str, policy: Mapping[str, object],
) -> dict:
    signals = candidate["locator_signals"]
    record = {
        "schema_version": RECORD_SCHEMA,
        "status": "TEMPLATE_UNVERIFIED",
        "episode_id": "episode-001-adam",
        "event_id": event_id,
        "event_title": event_title,
        "route": route,
        "candidate_id": candidate["candidate_id"],
        "representative_candidate_id": candidate["representative_candidate_id"],
        "verification_key": candidate["verification_key"],
        "candidate_path": candidate["path"],
        "candidate_line_start": candidate["line_start"],
        "candidate_line_end": candidate["line_end"],
        "candidate_file_sha256": candidate["file_sha256"],
        "candidate_excerpt": candidate["excerpt"],
        "candidate_excerpt_sha256": candidate["excerpt_sha256"],
        "candidate_structural_bucket": candidate["triage_bucket"],
        "candidate_structural_score": candidate["structural_score"],
        "detected_source_names": list(signals.get("source_names", [])),
        "detected_numbers": list(signals.get("numbers", [])),
        "detected_source_record_ids": list(
            signals.get("source_record_ids", [])
        ),
        "detected_urls": list(signals.get("urls", [])),
        "detected_page_or_volume_markers": list(
            signals.get("page_or_volume_markers", [])
        ),
        "source_title": "",
        "author": "",
        "edition_or_database": "",
        "volume_page_or_record_number": "",
        "exact_excerpt": "",
        "context_before_after": "",
        "source_file_or_url": "",
        "source_material_sha256": "",
        "exact_excerpt_sha256": "",
        "verification_method": "",
        "authentication_authority": "",
        "authentication_result": "",
        "authentication_locator": "",
        "origin_classification": "unresolved",
        "classification_notes": "",
        "uncertainties": [],
        "source_verified": False,
        "authentication_verified": False,
        "origin_classification_verified": False,
        "verified_by": "",
        "verified_at": "",
        "human_decision": False,
        "approved_for_event_binding": False,
        "policy_id": policy["policy_id"],
        "policy_sha256": canonical_sha256(policy),
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    validate_record_template(record)
    return record


def build_review_template(
    *, execution_id: str, execution_sha256: str,
    backlog: Mapping[str, object], policy: Mapping[str, object],
) -> dict:
    decisions = []
    for item in backlog["items"]:
        editorial = item["event_id"] in EDITORIAL_EVENTS
        decisions.append({
            "event_id": item["event_id"],
            "title": item["title"],
            "route": ROUTE_EDITORIAL if editorial else "",
            "verified_record_ids": [],
            "proposed_disposition": "editorial_only" if editorial else "",
            "source_verification_complete": False,
            "approved": False,
            "human_decision": False,
            "reviewer_notes": "",
        })
    review = {
        "schema_version": REVIEW_SCHEMA,
        "status": "TEMPLATE_NOT_APPROVED",
        "episode_id": "episode-001-adam",
        "execution_id": execution_id,
        "execution_sha256": execution_sha256,
        "policy_id": policy["policy_id"],
        "policy_sha256": canonical_sha256(policy),
        "event_count": len(decisions),
        "decisions": decisions,
        "approved_by": "",
        "approved_at": "",
        "human_approval": False,
        "full_episode_adjudication_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    validate_review_template(review)
    return review


def build_execution(
    *, triage_path: Path, backlog_path: Path, plan_path: Path,
) -> tuple[dict, dict, dict, list[dict], dict[str, dict]]:
    triage = load_triage(triage_path)
    backlog = load_backlog(backlog_path)
    plan = load_verification_plan(plan_path)
    policy = build_policy()
    representatives, duplicates = consolidate_selected_candidates(triage)
    reps_by_event: dict[str, list[dict]] = defaultdict(list)
    for candidate in representatives:
        reps_by_event[candidate["event_id"]].append(candidate)

    backlog_by_id = {item["event_id"]: item for item in backlog["items"]}
    events = []
    record_templates: dict[str, dict] = {}
    for event_id in TARGET_EVENTS:
        backlog_item = backlog_by_id[event_id]
        event_candidates = reps_by_event.get(event_id, [])
        route = determine_route(event_id, event_candidates)
        if event_id in FACTUAL_EVENTS and not event_candidates:
            route = ROUTE_DISCOVERY
        records = []
        for candidate in event_candidates:
            record = build_record_template(
                event_id=event_id,
                event_title=backlog_item["title"],
                candidate=candidate,
                route=route,
                policy=policy,
            )
            record_id = (
                event_id.lower().replace("-", "_")
                + "_verify_"
                + canonical_sha256(record)[:16]
            )
            record["record_template_id"] = record_id
            record_templates[record_id] = record
            records.append({
                "record_template_id": record_id,
                "candidate_id": candidate["candidate_id"],
                "verification_key": candidate["verification_key"],
                "triage_bucket": candidate["triage_bucket"],
                "structural_score": candidate["structural_score"],
            })
        events.append({
            "event_id": event_id,
            "title": backlog_item["title"],
            "section": backlog_item["section"],
            "event_kind": backlog_item["event_kind"],
            "route": route,
            "representative_candidate_count": len(event_candidates),
            "record_template_count": len(records),
            "record_templates": records,
            "source_verification_complete": False,
            "human_decision_required": True,
        })

    batches = []
    event_index = {item["event_id"]: item for item in events}
    for plan_batch in plan["batches"]:
        event_ids = list(plan_batch["event_ids"])
        batch_record_ids = [
            record["record_template_id"]
            for event_id in event_ids
            for record in event_index[event_id]["record_templates"]
        ]
        batches.append({
            "batch_id": plan_batch["batch_id"],
            "objective": plan_batch["objective"],
            "event_ids": event_ids,
            "record_template_ids": batch_record_ids,
            "record_template_count": len(batch_record_ids),
            "execution_status": "READY",
            "automatic_adjudication": False,
        })

    route_counts = Counter(item["route"] for item in events)
    execution = {
        "schema_version": EXECUTION_SCHEMA,
        "status": STATUS,
        "episode_id": "episode-001-adam",
        "triage_id": triage["triage_id"],
        "triage_sha256": canonical_sha256(triage),
        "backlog_id": backlog["backlog_id"],
        "backlog_sha256": canonical_sha256(backlog),
        "verification_plan_id": plan.get("plan_id"),
        "verification_plan_sha256": canonical_sha256(plan),
        "policy_id": policy["policy_id"],
        "policy_sha256": canonical_sha256(policy),
        "input_selected_candidate_count": triage["selected_candidate_count"],
        "representative_candidate_count": len(representatives),
        "duplicate_candidate_count": len(duplicates),
        "event_count": len(events),
        "factual_event_count": 14,
        "editorial_event_count": 1,
        "route_counts": dict(sorted(route_counts.items())),
        "events": events,
        "batch_count": len(batches),
        "batches": batches,
        "record_template_count": len(record_templates),
        "source_verification_complete": False,
        "human_approval": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    execution["execution_id"] = (
        "adam_source_verification_execution_"
        + canonical_sha256(execution)[:16]
    )
    validate_execution(execution)
    review = build_review_template(
        execution_id=execution["execution_id"],
        execution_sha256=canonical_sha256(execution),
        backlog=backlog,
        policy=policy,
    )
    duplicate_package = {
        "schema_version": "siraj-source-verification-duplicate-ledger-v1",
        "execution_id": execution["execution_id"],
        "duplicate_count": len(duplicates),
        "duplicates": duplicates,
    }
    return execution, policy, review, duplicates, record_templates


def validate_policy(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != POLICY_SCHEMA:
        raise VerificationExecutionError("Unexpected policy schema.")
    required = data.get("required_fields_for_source_verified")
    if not isinstance(required, list) or len(required) < 10:
        raise VerificationExecutionError("Verification requirements incomplete.")
    if "automatic hadith grading" not in data.get("prohibitions", []):
        raise VerificationExecutionError("Hadith-grading prohibition missing.")
    _validate_guards(data)


def validate_record_template(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != RECORD_SCHEMA:
        raise VerificationExecutionError("Unexpected record schema.")
    if data.get("status") != "TEMPLATE_UNVERIFIED":
        raise VerificationExecutionError("Record template cannot be verified.")
    if not EVENT_RE.fullmatch(str(data.get("event_id", ""))):
        raise VerificationExecutionError("Invalid record event id.")
    if not SHA_RE.fullmatch(str(data.get("candidate_file_sha256", ""))):
        raise VerificationExecutionError("Invalid candidate file checksum.")
    excerpt = str(data.get("candidate_excerpt", ""))
    if text_sha256(excerpt) != data.get("candidate_excerpt_sha256"):
        raise VerificationExecutionError("Candidate excerpt checksum mismatch.")
    blank_fields = (
        "source_title", "author", "edition_or_database",
        "volume_page_or_record_number", "exact_excerpt",
        "context_before_after", "source_file_or_url",
        "source_material_sha256", "exact_excerpt_sha256",
        "verification_method", "authentication_authority",
        "authentication_result", "authentication_locator",
        "verified_by", "verified_at",
    )
    if any(data.get(field) for field in blank_fields):
        raise VerificationExecutionError("Record verification fields must be blank.")
    false_fields = (
        "source_verified", "authentication_verified",
        "origin_classification_verified", "human_decision",
        "approved_for_event_binding", "opens_evidence_gate",
    )
    if any(data.get(field) is not False for field in false_fields):
        raise VerificationExecutionError("Record cannot claim verification/approval.")
    if data.get("origin_classification") != "unresolved":
        raise VerificationExecutionError("Origin classification must remain unresolved.")
    _validate_guards(data)


def validate_review_template(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != REVIEW_SCHEMA:
        raise VerificationExecutionError("Unexpected review schema.")
    if data.get("status") != "TEMPLATE_NOT_APPROVED":
        raise VerificationExecutionError("Review template cannot be approved.")
    decisions = data.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != 15:
        raise VerificationExecutionError("Review template must cover 15 events.")
    for decision in decisions:
        if decision.get("verified_record_ids"):
            raise VerificationExecutionError("Verified record ids must be blank.")
        if decision.get("source_verification_complete") is not False:
            raise VerificationExecutionError("Verification cannot be pre-complete.")
        if decision.get("approved") is not False:
            raise VerificationExecutionError("Decision cannot be preapproved.")
        if decision.get("human_decision") is not False:
            raise VerificationExecutionError("Human decision cannot be prefilled.")
    if data.get("approved_by") or data.get("approved_at"):
        raise VerificationExecutionError("Reviewer metadata must be blank.")
    _validate_guards(data)


def validate_execution(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != EXECUTION_SCHEMA or data.get("status") != STATUS:
        raise VerificationExecutionError("Unexpected execution schema/status.")
    events = data.get("events")
    if not isinstance(events, list) or len(events) != 15:
        raise VerificationExecutionError("Execution must cover 15 events.")
    if tuple(item["event_id"] for item in events) != TARGET_EVENTS:
        raise VerificationExecutionError("Execution event coverage changed.")
    if data.get("factual_event_count") != 14:
        raise VerificationExecutionError("Factual event count changed.")
    if data.get("editorial_event_count") != 1:
        raise VerificationExecutionError("Editorial event count changed.")
    editorial = next(
        item for item in events if item["event_id"] == "EV-ADAM-099"
    )
    if editorial["route"] != ROUTE_EDITORIAL:
        raise VerificationExecutionError("Editorial route changed.")
    if editorial["record_template_count"] != 0:
        raise VerificationExecutionError("Editorial event cannot have source records.")
    if data.get("batch_count") != 3:
        raise VerificationExecutionError("Execution must contain three batches.")
    covered = tuple(
        event_id
        for batch in data["batches"]
        for event_id in batch["event_ids"]
    )
    if covered != FACTUAL_EVENTS:
        raise VerificationExecutionError("Execution batch coverage changed.")
    if any(batch.get("automatic_adjudication") is not False for batch in data["batches"]):
        raise VerificationExecutionError("Execution cannot authorize adjudication.")
    false_fields = (
        "source_verification_complete",
        "human_approval",
        "full_episode_adjudication_complete",
        "approved_evidence_package_complete",
        "opens_evidence_gate",
    )
    if any(data.get(field) is not False for field in false_fields):
        raise VerificationExecutionError("Execution cannot claim completion/approval.")
    _validate_guards(data)


def _validate_guards(data: Mapping[str, object]) -> None:
    if data.get("human_approval") not in (None, False):
        raise VerificationExecutionError("Artifact cannot claim human approval.")
    if data.get("evidence_gate_status") != GATE:
        raise VerificationExecutionError("Evidence gate must remain withheld.")
    if data.get("automatic_evidence_approval") != AUTO_APPROVAL:
        raise VerificationExecutionError("Automatic approval must remain forbidden.")
    if data.get("live_provider_execution") != LIVE_EXECUTION:
        raise VerificationExecutionError("Provider execution must remain blocked.")


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_local_outputs(
    *, output_root: Path, execution: Mapping[str, object],
    policy: Mapping[str, object], review: Mapping[str, object],
    duplicates: list[Mapping[str, object]],
    record_templates: Mapping[str, Mapping[str, object]],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "execution": output_root / "source-verification-execution-v1.json",
        "policy": output_root / "source-verification-acceptance-policy-v1.json",
        "review": output_root / "source-verification-human-review-v1.template.json",
        "duplicates": output_root / "source-verification-duplicate-ledger-v1.json",
        "queue_csv": output_root / "source-verification-queue.csv",
        "duplicates_csv": output_root / "source-verification-duplicates.csv",
        "summary": output_root / "README.md",
    }
    write_json(outputs["execution"], execution)
    write_json(outputs["policy"], policy)
    write_json(outputs["review"], review)
    write_json(outputs["duplicates"], {
        "schema_version": "siraj-source-verification-duplicate-ledger-v1",
        "execution_id": execution["execution_id"],
        "duplicate_count": len(duplicates),
        "duplicates": list(duplicates),
    })

    record_root = output_root / "verification-records"
    record_root.mkdir(parents=True, exist_ok=True)
    for record_id, record in sorted(record_templates.items()):
        event_dir = record_root / record["event_id"]
        write_json(event_dir / f"{record_id}.json", record)

    queue_fields = (
        "event_id", "event_title", "route", "record_template_id",
        "candidate_id", "verification_key", "candidate_structural_bucket",
        "candidate_structural_score", "candidate_path",
    )
    with outputs["queue_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=queue_fields)
        writer.writeheader()
        for record_id, record in sorted(record_templates.items()):
            writer.writerow({
                "event_id": record["event_id"],
                "event_title": record["event_title"],
                "route": record["route"],
                "record_template_id": record_id,
                "candidate_id": record["candidate_id"],
                "verification_key": record["verification_key"],
                "candidate_structural_bucket": record[
                    "candidate_structural_bucket"
                ],
                "candidate_structural_score": record[
                    "candidate_structural_score"
                ],
                "candidate_path": record["candidate_path"],
            })

    duplicate_fields = (
        "event_id", "verification_key", "representative_candidate_id",
        "duplicate_candidate_id", "duplicate_path",
        "duplicate_excerpt_sha256", "deduplication_basis",
    )
    with outputs["duplicates_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=duplicate_fields)
        writer.writeheader()
        for item in duplicates:
            writer.writerow({key: item[key] for key in duplicate_fields})

    event_root = output_root / "event-execution-dossiers"
    event_root.mkdir(parents=True, exist_ok=True)
    records_by_event: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for record in record_templates.values():
        records_by_event[record["event_id"]].append(record)
    for event in execution["events"]:
        event_id = event["event_id"]
        lines = [
            f"# {event_id} — {event['title']}",
            "",
            f"- Route: `{event['route']}`",
            f"- Representative candidates: {event['representative_candidate_count']}",
            f"- Record templates: {event['record_template_count']}",
            "- Source verification complete: no",
            "",
        ]
        if event["route"] == ROUTE_EDITORIAL:
            lines.extend([
                "This event is editorial-only. It requires a human decision, "
                "not factual source verification.",
                "",
            ])
        elif event["route"] == ROUTE_DISCOVERY:
            lines.extend([
                "No precise locator survived structural triage.",
                "Search original authorized sources using the event title and "
                "research questions before creating a verified record.",
                "",
            ])
        for record in sorted(
            records_by_event.get(event_id, []),
            key=lambda item: (
                -int(item["candidate_structural_score"]),
                item["record_template_id"],
            ),
        ):
            lines.extend([
                f"## {record['record_template_id']}",
                "",
                f"- Candidate: `{record['candidate_id']}`",
                f"- Bucket: `{record['candidate_structural_bucket']}`",
                f"- Verification key: `{record['verification_key']}`",
                f"- Path: `{record['candidate_path']}`",
                f"- Lines: {record['candidate_line_start']}-{record['candidate_line_end']}",
                f"- Detected sources: {', '.join(record['detected_source_names']) or 'none'}",
                f"- Detected numbers: {', '.join(record['detected_numbers']) or 'none'}",
                f"- Template: `verification-records/{event_id}/{record['record_template_id']}.json`",
                "",
                "```text",
                record["candidate_excerpt"],
                "```",
                "",
            ])
        (event_root / f"{event_id}.md").write_text(
            "\n".join(lines), encoding="utf-8", newline="\n"
        )

    batch_root = output_root / "execution-batches"
    batch_root.mkdir(parents=True, exist_ok=True)
    for index, batch in enumerate(execution["batches"], 1):
        payload = {
            **batch,
            "record_templates": [
                record_templates[record_id]
                for record_id in batch["record_template_ids"]
            ],
            "execution_instruction": (
                "For each template, open the original authorized source, "
                "verify the exact locator and excerpt, compute source and "
                "excerpt checksums, record uncertainty, and leave authentication "
                "and origin unresolved unless a qualified human authority "
                "explicitly records them. Internal SIRAJ summaries are not "
                "original evidence."
            ),
        }
        write_json(
            batch_root / f"{index:02d}-{batch['batch_id'].lower()}.json",
            payload,
        )

    route_counts = execution["route_counts"]
    outputs["summary"].write_text(
        "# Adam Non-Quran Source Verification Execution v1\n\n"
        f"- Selected candidate input: {execution['input_selected_candidate_count']}\n"
        f"- Canonical representatives: {execution['representative_candidate_count']}\n"
        f"- Consolidated duplicates: {execution['duplicate_candidate_count']}\n"
        f"- Verification record templates: {execution['record_template_count']}\n"
        f"- Locator verification events: {route_counts.get(ROUTE_LOCATOR, 0)}\n"
        f"- Source-mention expansion events: {route_counts.get(ROUTE_MENTION, 0)}\n"
        f"- Focused discovery events: {route_counts.get(ROUTE_DISCOVERY, 0)}\n"
        "- No source was authenticated and no report was graded.\n"
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
