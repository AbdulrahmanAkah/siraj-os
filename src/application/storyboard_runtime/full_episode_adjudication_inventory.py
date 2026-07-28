"""Build a conservative full-episode adjudication inventory for Adam.

This module inventories event readiness and evidence traces. It never grades
sources, records human approval, opens the evidence gate, or enables providers.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping

SCHEMA = "siraj-full-episode-adjudication-inventory-v1"
STATUS = "INVENTORY_READY_REVIEW_AND_BINDING_PENDING"
GATE = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTO_APPROVAL = "FORBIDDEN"
LIVE_EXECUTION = "BLOCKED"
EVENT_RE = re.compile(r"\bEV-ADAM-\d{3}\b")
HUMAN_APPROVED_GAPS = ("EV-ADAM-031", "EV-ADAM-071", "EV-ADAM-091")


class FullEpisodeInventoryError(ValueError):
    pass


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FullEpisodeInventoryError(f"Invalid JSON: {path}") from exc


def _event_map(path: Path) -> list[Mapping[str, object]]:
    value = _read_json(path)
    if not isinstance(value, list) or any(not isinstance(x, Mapping) for x in value):
        raise FullEpisodeInventoryError("event-map.json must be a list of objects.")
    ids = [str(x.get("event_id", "")) for x in value]
    if len(ids) != len(set(ids)) or any(not EVENT_RE.fullmatch(x) for x in ids):
        raise FullEpisodeInventoryError("Event map ids are invalid or duplicated.")
    if len(ids) != 37:
        raise FullEpisodeInventoryError(f"Expected 37 Adam events, found {len(ids)}.")
    return list(value)


def _source_records(path: Path) -> tuple[dict[str, dict], dict[str, list[str]]]:
    if not path.is_file():
        return {}, {}
    data = _read_json(path)
    if not isinstance(data, Mapping):
        return {}, {}
    records = {}
    for item in data.get("source_records", []):
        if isinstance(item, Mapping) and isinstance(item.get("source_record_id"), str):
            records[item["source_record_id"]] = dict(item)
    by_event: dict[str, list[str]] = defaultdict(list)
    for event in data.get("events", []):
        if not isinstance(event, Mapping):
            continue
        event_id = event.get("event_id")
        if not isinstance(event_id, str):
            continue
        text = json.dumps(event, ensure_ascii=False)
        for source_id in records:
            if source_id in text:
                by_event[event_id].append(source_id)
    return records, {k: sorted(set(v)) for k, v in by_event.items()}


def _approved_events(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    data = _read_json(path)
    if not isinstance(data, Mapping) or data.get("human_approval") is not True:
        return {}
    if data.get("scope", {}).get("opens_evidence_gate") is not False:
        raise FullEpisodeInventoryError("Limited approval unexpectedly opens the gate.")
    result = {}
    for item in data.get("decisions", []):
        if isinstance(item, Mapping) and item.get("human_decision") is True:
            result[str(item["event_id"])] = dict(item)
    if tuple(result) != HUMAN_APPROVED_GAPS:
        raise FullEpisodeInventoryError("Human-approved gap event set changed.")
    return result


def scan_event_mentions(root: Path) -> tuple[dict[str, dict], dict]:
    """Scan project text metadata without retaining raw source text."""
    root = Path(root)
    per_event: dict[str, dict] = defaultdict(
        lambda: {"mention_count": 0, "file_count": 0, "paths": []}
    )
    scanned = 0
    skipped_large = 0
    extensions = {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml", ".csv"}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > 25_000_000:
            skipped_large += 1
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        scanned += 1
        counts = Counter(EVENT_RE.findall(text))
        relative = path.relative_to(root).as_posix()
        for event_id, count in counts.items():
            entry = per_event[event_id]
            entry["mention_count"] += count
            entry["file_count"] += 1
            if len(entry["paths"]) < 20:
                entry["paths"].append(relative)
    return dict(per_event), {
        "files_scanned": scanned,
        "large_files_skipped": skipped_large,
        "raw_text_retained": False,
    }


def _readiness(event: Mapping[str, object], approved: bool, source_ids: list[str],
               mention_count: int) -> tuple[str, list[str]]:
    status = str(event.get("verification_status", "pending"))
    reasons: list[str] = []
    if approved:
        reasons.append("limited human decision recorded")
        reasons.append("full evidence item checksums still missing")
        return "HUMAN_DECISION_RECORDED_BINDING_PENDING", reasons
    if status == "quran_explicit":
        reasons.append("event map marks claim Quran-explicit")
        reasons.append("exact verse locator and source/excerpt checksums still required")
        return "QURAN_SOURCE_BINDING_PENDING", reasons
    if source_ids:
        reasons.append("classified source records are linked")
        reasons.append("human decision and evidence item checksums still required")
        return "SOURCE_CLASSIFIED_HUMAN_REVIEW_PENDING", reasons
    if mention_count:
        reasons.append("local project artifacts mention the event")
        reasons.append("candidate traces require extraction and verification")
        return "CANDIDATE_EVIDENCE_REVIEW_PENDING", reasons
    if status in {"deferred", "pending", "pending_interpretation"}:
        reasons.append(f"event map verification status is {status}")
        return "RESEARCH_OR_EDITORIAL_DECISION_PENDING", reasons
    reasons.append("no binding-ready evidence trace found")
    return "SOURCE_DISCOVERY_PENDING", reasons


def _priority(event: Mapping[str, object], readiness: str) -> int:
    importance = {"core": 0, "supporting": 1, "context": 2}.get(
        str(event.get("importance")), 3
    )
    readiness_rank = {
        "QURAN_SOURCE_BINDING_PENDING": 0,
        "SOURCE_CLASSIFIED_HUMAN_REVIEW_PENDING": 1,
        "HUMAN_DECISION_RECORDED_BINDING_PENDING": 2,
        "CANDIDATE_EVIDENCE_REVIEW_PENDING": 3,
        "RESEARCH_OR_EDITORIAL_DECISION_PENDING": 4,
        "SOURCE_DISCOVERY_PENDING": 5,
    }.get(readiness, 9)
    return readiness_rank * 1000 + importance * 100 + int(event.get("order", 999))


def build_inventory(*, event_map_path: Path, project_root: Path,
                    source_classification_path: Path,
                    human_approval_path: Path,
                    include_local_scan: bool = True) -> dict:
    events = _event_map(event_map_path)
    records, source_by_event = _source_records(source_classification_path)
    approved = _approved_events(human_approval_path)
    mentions, scan = scan_event_mentions(project_root) if include_local_scan else ({}, {
        "files_scanned": 0, "large_files_skipped": 0, "raw_text_retained": False
    })

    rows = []
    for event in events:
        event_id = str(event["event_id"])
        trace = mentions.get(event_id, {})
        source_ids = source_by_event.get(event_id, [])
        readiness, reasons = _readiness(
            event, event_id in approved, source_ids, int(trace.get("mention_count", 0))
        )
        rows.append({
            "event_id": event_id,
            "order": int(event.get("order", 0)),
            "section": str(event.get("section", "")),
            "title": str(event.get("title", "")),
            "importance": str(event.get("importance", "")),
            "duration_weight": str(event.get("duration_weight", "")),
            "chronology_type": str(event.get("chronology_type", "")),
            "verification_status": str(event.get("verification_status", "")),
            "question_ids": list(event.get("question_ids", [])),
            "human_gap_decision_recorded": event_id in approved,
            "approved_gap_disposition": approved.get(event_id, {}).get("disposition"),
            "source_record_ids": source_ids,
            "source_record_count": len(source_ids),
            "artifact_mention_count": int(trace.get("mention_count", 0)),
            "artifact_file_count": int(trace.get("file_count", 0)),
            "artifact_paths_sample": list(trace.get("paths", [])),
            "readiness": readiness,
            "blocking_reasons": reasons,
        })

    rows.sort(key=lambda x: x["order"])
    counts = Counter(x["readiness"] for x in rows)
    priority = sorted(rows, key=lambda x: _priority(x, x["readiness"]))
    next_batch = [
        {
            "event_id": x["event_id"],
            "title": x["title"],
            "section": x["section"],
            "readiness": x["readiness"],
            "recommended_action": {
                "QURAN_SOURCE_BINDING_PENDING":
                    "bind exact Quran verse locator and compute source/excerpt checksums",
                "SOURCE_CLASSIFIED_HUMAN_REVIEW_PENDING":
                    "prepare audience wording and human disposition review",
                "HUMAN_DECISION_RECORDED_BINDING_PENDING":
                    "materialize approved evidence items with checksums",
                "CANDIDATE_EVIDENCE_REVIEW_PENDING":
                    "extract, deduplicate, and verify strongest local candidates",
                "RESEARCH_OR_EDITORIAL_DECISION_PENDING":
                    "research origin or choose qualified/omit/editorial treatment",
                "SOURCE_DISCOVERY_PENDING":
                    "discover primary source candidates",
            }[x["readiness"]],
        }
        for x in priority[:12]
    ]

    fingerprint_input = {
        "events": rows,
        "source_records": sorted(records),
        "approved_events": sorted(approved),
        "scan_summary": scan,
    }
    inventory = {
        "schema_version": SCHEMA,
        "status": STATUS,
        "episode_id": "episode-001-adam",
        "event_count": len(rows),
        "event_map_sha256": canonical_sha256(events),
        "source_classification_sha256": (
            canonical_sha256(_read_json(source_classification_path))
            if source_classification_path.is_file() else None
        ),
        "human_gap_approval_sha256": (
            canonical_sha256(_read_json(human_approval_path))
            if human_approval_path.is_file() else None
        ),
        "inventory_id": "adam_full_episode_inventory_" +
                        canonical_sha256(fingerprint_input)[:16],
        "coverage": {
            "human_decision_recorded_events": len(approved),
            "events_with_classified_source_records": sum(bool(x["source_record_ids"]) for x in rows),
            "events_with_local_artifact_mentions": sum(x["artifact_mention_count"] > 0 for x in rows),
            "readiness_counts": dict(sorted(counts.items())),
        },
        "scan_summary": scan,
        "events": rows,
        "recommended_next_batch": next_batch,
        "binding_readiness": {
            "ready": False,
            "full_episode_adjudication_complete": False,
            "approved_evidence_package_complete": False,
            "source_and_excerpt_checksums_complete": False,
        },
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "human_approval_effect": "NONE_BEYOND_ALREADY_RECORDED_THREE_GAP_DECISIONS",
        "live_provider_execution": LIVE_EXECUTION,
    }
    validate_inventory(inventory)
    return inventory


def validate_inventory(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != SCHEMA or data.get("status") != STATUS:
        raise FullEpisodeInventoryError("Inventory schema or status changed.")
    if data.get("event_count") != 37:
        raise FullEpisodeInventoryError("Inventory must contain all 37 events.")
    events = data.get("events")
    if not isinstance(events, list) or len(events) != 37:
        raise FullEpisodeInventoryError("Inventory event list is incomplete.")
    ids = [x.get("event_id") for x in events if isinstance(x, Mapping)]
    if len(ids) != 37 or len(set(ids)) != 37:
        raise FullEpisodeInventoryError("Inventory event ids are incomplete or duplicated.")
    if data.get("evidence_gate_status") != GATE:
        raise FullEpisodeInventoryError("Inventory cannot open the evidence gate.")
    if data.get("automatic_evidence_approval") != AUTO_APPROVAL:
        raise FullEpisodeInventoryError("Inventory cannot approve evidence.")
    if data.get("live_provider_execution") != LIVE_EXECUTION:
        raise FullEpisodeInventoryError("Inventory cannot enable providers.")
    readiness = data.get("binding_readiness")
    if not isinstance(readiness, Mapping) or any(readiness.get(k) is not False for k in (
        "ready", "full_episode_adjudication_complete",
        "approved_evidence_package_complete", "source_and_excerpt_checksums_complete"
    )):
        raise FullEpisodeInventoryError("Inventory cannot claim binding readiness.")


def write_outputs(root: Path, inventory: Mapping[str, object]) -> dict[str, Path]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "full-episode-event-inventory.json"
    json_path.write_text(json.dumps(
        inventory, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n", encoding="utf-8", newline="\n")

    csv_path = root / "event-evidence-coverage.csv"
    fields = [
        "event_id", "order", "section", "title", "importance",
        "verification_status", "human_gap_decision_recorded",
        "source_record_count", "artifact_mention_count", "artifact_file_count",
        "readiness",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in inventory["events"]:
            writer.writerow({k: item.get(k) for k in fields})

    batch_path = root / "human-review-next-batch.json"
    batch_path.write_text(json.dumps({
        "schema_version": "siraj-adjudication-next-batch-v1",
        "inventory_id": inventory["inventory_id"],
        "items": inventory["recommended_next_batch"],
        "human_approval": False,
        "evidence_gate_status": GATE,
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    backlog_path = root / "source-binding-backlog.json"
    backlog = [{
        "event_id": x["event_id"],
        "title": x["title"],
        "readiness": x["readiness"],
        "blocking_reasons": x["blocking_reasons"],
        "source_record_ids": x["source_record_ids"],
    } for x in inventory["events"] if x["readiness"] !=
         "HUMAN_DECISION_RECORDED_BINDING_PENDING"]
    backlog_path.write_text(json.dumps({
        "schema_version": "siraj-source-binding-backlog-v1",
        "inventory_id": inventory["inventory_id"],
        "item_count": len(backlog),
        "items": backlog,
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    readme = root / "README.md"
    cov = inventory["coverage"]
    readme.write_text(
        "# Adam Full-Episode Adjudication Inventory v1\n\n"
        f"- Events inventoried: {inventory['event_count']}\n"
        f"- Human-approved gap decisions: {cov['human_decision_recorded_events']}\n"
        f"- Events with classified source records: {cov['events_with_classified_source_records']}\n"
        f"- Events mentioned in scanned local artifacts: {cov['events_with_local_artifact_mentions']}\n"
        f"- Files scanned: {inventory['scan_summary']['files_scanned']}\n"
        "- Evidence gate: withheld.\n"
        "- Automatic approval: forbidden.\n"
        "- Raw source text was not retained in this report.\n",
        encoding="utf-8", newline="\n"
    )
    return {
        "inventory": json_path, "coverage_csv": csv_path,
        "next_batch": batch_path, "backlog": backlog_path, "readme": readme
    }
