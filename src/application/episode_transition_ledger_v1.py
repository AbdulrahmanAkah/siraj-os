"""Authoritative append-only episode transition ledger.

The ledger is the only writable authority for current/completed stages in the
remediated pipeline.  Legacy state files remain readable projections and are
never rewritten by inspection.  A legacy episode cannot execute until a human
approves a migration receipt; merely creating a migration proposal is not an
approval.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
import os
import uuid

from src.application.artifact_provenance_v1 import (
    append_jsonl,
    artifact_reference,
    canonical_json_bytes,
    canonical_sha256,
    _THREAD_LOCK,
    _process_lock,
    read_jsonl,
    sha256_file,
    utc_now,
)


SCHEMA_VERSION = "siraj-episode-transition-ledger-v1"
MIGRATION_APPROVAL_SCHEMA = "siraj-episode-transition-migration-approval-v1"
MIGRATION_APPROVAL_PHRASE = "أوافق على اعتماد سجل انتقال الحلقة بعد مراجعة المقترح"

BASE_STAGE_ORDER: tuple[str, ...] = (
    "TOPIC_SELECTION",
    "SOURCE_RESEARCH_FROM_ZERO",
    "SOURCE_CLAIM_MATRIX",
    "STORY_ARCHITECTURE",
    "ICONIC_CINEMATIC_REVIEW",
    "FINAL_SCRIPT",
    "PRONUNCIATION_AND_PERFORMANCE_GATE",
    "FINAL_TTS",
    "AUDIO_TIMESTAMPS_AND_BEATS",
    "AUDIO_BOUND_STORYBOARD",
    "LUNA_SEMANTIC_PROMPT_DIRECTION",
    "NARRATION_VISUAL_ALIGNMENT_GATE",
    "PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
    "MEDIA_COST_PREFLIGHT",
    "PROVIDER_EXECUTION",
    "LOCAL_ASSEMBLY_AND_MONTAGE",
    "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA",
    "READY_FOR_FINAL_HUMAN_REVIEW",
)
EVENT_REVIEW_STAGE = "EVENTS_REVIEW_AND_APPROVAL"


class EpisodeTransitionLedgerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TransitionProjection:
    episode_id: str
    current_stage: str
    completed_stages: tuple[str, ...]
    status: str
    failure_classification: str | None
    last_transition_id: str | None
    ledger_authoritative: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def stage_order(*, event_review_required: bool = False) -> tuple[str, ...]:
    if not event_review_required:
        return BASE_STAGE_ORDER
    insertion = BASE_STAGE_ORDER.index("STORY_ARCHITECTURE")
    return (
        BASE_STAGE_ORDER[:insertion]
        + (EVENT_REVIEW_STAGE,)
        + BASE_STAGE_ORDER[insertion:]
    )


def ledger_path(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / "episode-transition-ledger-v1.jsonl"
    )


def migration_approval_path(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / "episode-transition-migration-approval-v1.json"
    )


def _entry_without_hash(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in entry.items() if key != "entry_sha256"}


def validate_entry(entry: Mapping[str, Any], episode_id: str) -> None:
    if entry.get("schema_version") != SCHEMA_VERSION:
        raise EpisodeTransitionLedgerError("TRANSITION_SCHEMA_INVALID")
    if entry.get("episode_id") != episode_id:
        raise EpisodeTransitionLedgerError("TRANSITION_EPISODE_MISMATCH")
    expected = canonical_sha256(_entry_without_hash(entry))
    if entry.get("entry_sha256") != expected:
        raise EpisodeTransitionLedgerError("TRANSITION_ENTRY_HASH_INVALID")


def read_entries(repo_root: Path, episode_id: str) -> list[dict[str, Any]]:
    entries = read_jsonl(ledger_path(repo_root, episode_id))
    for entry in entries:
        validate_entry(entry, episode_id)
    return entries


def append_transition(
    repo_root: Path,
    episode_id: str,
    *,
    stage: str,
    previous_stage: str | None,
    status: str,
    input_artifacts: Sequence[Mapping[str, Any]] = (),
    output_artifacts: Sequence[Mapping[str, Any]] = (),
    schema_versions: Sequence[str] = (),
    authorization_references: Sequence[Mapping[str, Any]] = (),
    attempt_references: Sequence[Mapping[str, Any]] = (),
    failure_classification: str | None = None,
    invalidation_links: Sequence[Mapping[str, Any]] = (),
    transition_id: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    allowed = {
        "STARTED",
        "COMPLETED",
        "FAILED",
        "INVALIDATED",
        "MIGRATION_PROPOSED",
        "MIGRATION_APPROVED",
    }
    if status not in allowed:
        raise EpisodeTransitionLedgerError("TRANSITION_STATUS_INVALID:" + status)
    if stage not in BASE_STAGE_ORDER and stage != EVENT_REVIEW_STAGE:
        raise EpisodeTransitionLedgerError("TRANSITION_STAGE_INVALID:" + stage)
    now = utc_now()
    entry: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "transition_id": transition_id or str(uuid.uuid4()),
        "episode_id": episode_id,
        "stage": stage,
        "previous_stage": previous_stage,
        "status": status,
        "input_artifacts": list(input_artifacts),
        "output_artifacts": list(output_artifacts),
        "schema_versions": list(schema_versions),
        "authorization_references": list(authorization_references),
        "attempt_references": list(attempt_references),
        "started_at": started_at or now,
        "completed_at": completed_at if completed_at is not None else (
            now if status in {"COMPLETED", "FAILED", "INVALIDATED"} else None
        ),
        "failure_classification": failure_classification,
        "invalidation_links": list(invalidation_links),
        "metadata": dict(metadata or {}),
    }
    entry["entry_sha256"] = canonical_sha256(entry)
    append_jsonl(ledger_path(repo_root, episode_id), entry)
    return entry


def append_transition_if_head(
    repo_root: Path,
    episode_id: str,
    *,
    expected_ledger_sha256: str,
    stage: str,
    previous_stage: str | None,
    status: str,
    input_artifacts: Sequence[Mapping[str, Any]] = (),
    output_artifacts: Sequence[Mapping[str, Any]] = (),
    schema_versions: Sequence[str] = (),
    authorization_references: Sequence[Mapping[str, Any]] = (),
    attempt_references: Sequence[Mapping[str, Any]] = (),
    failure_classification: str | None = None,
    invalidation_links: Sequence[Mapping[str, Any]] = (),
    transition_id: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one receipt only if the ledger bytes still match the review.

    The ordinary append helper remains available for append-only migrations.
    Desktop resume transactions use this compare-and-set variant so a stale
    UI review cannot start or commit against a newer ledger head.
    """

    allowed = {
        "STARTED",
        "COMPLETED",
        "FAILED",
        "INVALIDATED",
        "MIGRATION_PROPOSED",
        "MIGRATION_APPROVED",
    }
    if status not in allowed:
        raise EpisodeTransitionLedgerError("TRANSITION_STATUS_INVALID:" + status)
    if stage not in BASE_STAGE_ORDER and stage != EVENT_REVIEW_STAGE:
        raise EpisodeTransitionLedgerError("TRANSITION_STAGE_INVALID:" + stage)
    path = ledger_path(repo_root, episode_id)
    with _THREAD_LOCK, _process_lock(path):
        actual = sha256_file(path) if path.is_file() else ""
        if actual != expected_ledger_sha256:
            raise EpisodeTransitionLedgerError(
                "AUTHORITATIVE_STATE_CHANGED_REVIEW_REQUIRED"
            )
        now = utc_now()
        entry: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "transition_id": transition_id or str(uuid.uuid4()),
            "episode_id": episode_id,
            "stage": stage,
            "previous_stage": previous_stage,
            "status": status,
            "input_artifacts": list(input_artifacts),
            "output_artifacts": list(output_artifacts),
            "schema_versions": list(schema_versions),
            "authorization_references": list(authorization_references),
            "attempt_references": list(attempt_references),
            "started_at": started_at or now,
            "completed_at": completed_at if completed_at is not None else (
                now if status in {"COMPLETED", "FAILED", "INVALIDATED"} else None
            ),
            "failure_classification": failure_classification,
            "invalidation_links": list(invalidation_links),
            "metadata": dict(metadata or {}),
        }
        entry["entry_sha256"] = canonical_sha256(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as handle:
            handle.write(canonical_json_bytes(entry) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        return entry


def _expected_stage(order: Sequence[str], completed: Sequence[str]) -> str:
    if len(completed) >= len(order):
        return order[-1]
    return order[len(completed)]


def project_state(
    repo_root: Path,
    episode_id: str,
    *,
    order: Sequence[str] = BASE_STAGE_ORDER,
) -> TransitionProjection:
    entries = read_entries(repo_root, episode_id)
    if not entries:
        raise EpisodeTransitionLedgerError("TRANSITION_LEDGER_EMPTY")
    completed: list[str] = []
    status = "READY"
    failure: str | None = None
    last_id: str | None = None
    current = order[0]

    for entry in entries:
        event_status = str(entry["status"])
        stage = str(entry["stage"])
        last_id = str(entry["transition_id"])
        if stage not in order:
            if event_status == "MIGRATION_PROPOSED":
                continue
            raise EpisodeTransitionLedgerError(
                "TRANSITION_STAGE_NOT_IN_EPISODE_ORDER:" + stage
            )

        if event_status == "MIGRATION_PROPOSED":
            continue
        if event_status == "MIGRATION_APPROVED":
            accepted = list(entry.get("metadata", {}).get("accepted_stages") or [])
            if accepted != list(order[: len(accepted)]):
                raise EpisodeTransitionLedgerError(
                    "MIGRATION_ACCEPTED_STAGES_NOT_CONTIGUOUS"
                )
            completed = accepted
            current = _expected_stage(order, completed)
            status = "READY"
            failure = None
            continue

        index = order.index(stage)
        expected_index = len(completed)
        if event_status == "INVALIDATED":
            completed = completed[:index]
            current = stage
            status = "INVALIDATED"
            failure = str(entry.get("failure_classification") or "INPUT_CHANGED")
            continue

        if event_status == "STARTED":
            if index != expected_index:
                raise EpisodeTransitionLedgerError(
                    "NON_CONTIGUOUS_STAGE_START:" + stage
                )
            current = stage
            status = "RUNNING"
            failure = None
            continue

        if event_status == "FAILED":
            if index != expected_index:
                raise EpisodeTransitionLedgerError(
                    "NON_CONTIGUOUS_STAGE_FAILURE:" + stage
                )
            current = stage
            status = "FAILED"
            failure = str(entry.get("failure_classification") or "UNCLASSIFIED")
            continue

        if event_status == "COMPLETED":
            if index < expected_index:
                prior = next(
                    (row for row in entries if row.get("stage") == stage and row.get("status") == "COMPLETED"),
                    None,
                )
                if prior and prior.get("output_artifacts") == entry.get("output_artifacts"):
                    continue
                raise EpisodeTransitionLedgerError(
                    "COMPLETED_STAGE_RERUN_FORBIDDEN:" + stage
                )
            if index != expected_index:
                raise EpisodeTransitionLedgerError(
                    "NON_CONTIGUOUS_COMPLETION:" + stage
                )
            completed.append(stage)
            current = _expected_stage(order, completed)
            status = "COMPLETE" if len(completed) == len(order) else "READY"
            failure = None

    return TransitionProjection(
        episode_id=episode_id,
        current_stage=current,
        completed_stages=tuple(completed),
        status=status,
        failure_classification=failure,
        last_transition_id=last_id,
        ledger_authoritative=True,
    )


def start_stage(
    repo_root: Path,
    episode_id: str,
    stage: str,
    *,
    input_paths: Sequence[Path] = (),
    authorization_references: Sequence[Mapping[str, Any]] = (),
    attempt_references: Sequence[Mapping[str, Any]] = (),
    order: Sequence[str] = BASE_STAGE_ORDER,
) -> dict[str, Any]:
    projection = project_state(repo_root, episode_id, order=order)
    if projection.current_stage != stage:
        raise EpisodeTransitionLedgerError(
            f"STAGE_NOT_CURRENT:{stage}:{projection.current_stage}"
        )
    previous = projection.completed_stages[-1] if projection.completed_stages else None
    refs = [artifact_reference(path, base=Path(repo_root)) for path in input_paths]
    return append_transition(
        repo_root,
        episode_id,
        stage=stage,
        previous_stage=previous,
        status="STARTED",
        input_artifacts=refs,
        authorization_references=authorization_references,
        attempt_references=attempt_references,
    )


def complete_stage(
    repo_root: Path,
    episode_id: str,
    stage: str,
    *,
    input_paths: Sequence[Path] = (),
    output_paths: Sequence[Path] = (),
    schema_versions: Sequence[str] = (),
    authorization_references: Sequence[Mapping[str, Any]] = (),
    attempt_references: Sequence[Mapping[str, Any]] = (),
    order: Sequence[str] = BASE_STAGE_ORDER,
) -> dict[str, Any]:
    projection = project_state(repo_root, episode_id, order=order)
    if projection.current_stage != stage:
        raise EpisodeTransitionLedgerError(
            f"STAGE_NOT_CURRENT_AT_COMMIT:{stage}:{projection.current_stage}"
        )
    previous = projection.completed_stages[-1] if projection.completed_stages else None
    return append_transition(
        repo_root,
        episode_id,
        stage=stage,
        previous_stage=previous,
        status="COMPLETED",
        input_artifacts=[artifact_reference(path, base=Path(repo_root)) for path in input_paths],
        output_artifacts=[artifact_reference(path, base=Path(repo_root)) for path in output_paths],
        schema_versions=schema_versions,
        authorization_references=authorization_references,
        attempt_references=attempt_references,
    )


def fail_stage(
    repo_root: Path,
    episode_id: str,
    stage: str,
    *,
    failure_classification: str,
    order: Sequence[str] = BASE_STAGE_ORDER,
) -> dict[str, Any]:
    projection = project_state(repo_root, episode_id, order=order)
    previous = projection.completed_stages[-1] if projection.completed_stages else None
    return append_transition(
        repo_root,
        episode_id,
        stage=stage,
        previous_stage=previous,
        status="FAILED",
        failure_classification=failure_classification,
    )


def migration_approval_active(repo_root: Path, episode_id: str) -> bool:
    path = migration_approval_path(repo_root, episode_id)
    if not path.is_file():
        return False
    try:
        import json

        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    if not isinstance(value, dict):
        return False
    signature = value.get("approval_sha256")
    unsigned = {key: val for key, val in value.items() if key != "approval_sha256"}
    return (
        value.get("schema_version") == MIGRATION_APPROVAL_SCHEMA
        and value.get("status") == "APPROVED"
        and value.get("episode_id") == episode_id
        and value.get("confirmation_phrase") == MIGRATION_APPROVAL_PHRASE
        and signature == canonical_sha256(unsigned)
    )


def require_ledger_or_migration_approval(
    repo_root: Path,
    episode_id: str,
) -> None:
    path = ledger_path(repo_root, episode_id)
    if path.is_file():
        project_state(repo_root, episode_id)
        return
    if migration_approval_active(repo_root, episode_id):
        return
    raise EpisodeTransitionLedgerError(
        "EPISODE_TRANSITION_LEDGER_MIGRATION_APPROVAL_REQUIRED:" + episode_id
    )
