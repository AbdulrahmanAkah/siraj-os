from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.application.production_resume_router_v1 import (
    resolve_resume_directive_from_state,
)

RELEASE = "SIRAJ_ACCEPTANCE_RESUME_BUTTON_RECOVERY_V1"
ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
BACKUP_DIR_REL = Path("projects/_orchestrator/runtime-state-backups")


class RuntimeStateRecoveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeStateDiagnosis:
    current_episode_id: str | None
    stored_status: str
    stored_stage: str
    stored_action: str
    inferred_status: str
    inferred_stage: str
    inferred_next_stage: str
    inferred_action: str
    needs_recovery: bool
    reason: str
    evidence_paths: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RuntimeStateRecoveryResult:
    changed: bool
    current_episode_id: str | None
    previous_status: str
    previous_stage: str
    recovered_status: str
    recovered_stage: str
    recovered_action: str
    reason: str
    backup_path: Path | None
    state_path: Path

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["backup_path"] = str(self.backup_path) if self.backup_path else None
        payload["state_path"] = str(self.state_path)
        return payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeStateRecoveryError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeStateRecoveryError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _episode_candidates(repo: Path) -> list[Path]:
    root = repo / "projects"
    if not root.is_dir():
        return []
    values = [
        path
        for path in root.iterdir()
        if path.is_dir() and path.name != "_orchestrator"
    ]
    return sorted(
        values,
        key=lambda path: (
            path.stat().st_mtime if path.exists() else 0.0,
            path.name,
        ),
        reverse=True,
    )


def _active_episode(repo: Path, state: Mapping[str, Any]) -> tuple[str | None, Path | None]:
    episode_id = state.get("current_episode_id")
    if isinstance(episode_id, str) and episode_id.strip():
        root = repo / "projects" / episode_id.strip()
        if root.is_dir():
            return episode_id.strip(), root
    candidates = _episode_candidates(repo)
    if not candidates:
        return None, None
    return candidates[0].name, candidates[0]


def _json_status(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        payload = _read(path)
    except RuntimeStateRecoveryError:
        return ""
    return str(payload.get("status") or payload.get("decision") or "").upper()


def _media_queue_complete(path: Path) -> tuple[bool, bool]:
    if not path.is_file():
        return False, False
    try:
        payload = _read(path)
    except RuntimeStateRecoveryError:
        return True, False
    queues = payload.get("queues")
    if not isinstance(queues, Mapping):
        return True, False
    items: list[Mapping[str, Any]] = []
    for key in (
        "runware_images",
        "runware_videos",
        "local_graphics",
        "elevenlabs_tts",
    ):
        for item in _sequence(queues.get(key)):
            if isinstance(item, Mapping):
                items.append(item)
    if not items:
        return True, False
    return True, all(str(item.get("status", "")).upper() == "COMPLETE" for item in items)


def _infer_from_artifacts(
    repo: Path,
    state: Mapping[str, Any],
) -> tuple[str, str, str, str, tuple[str, ...]]:
    episode_id, episode_root = _active_episode(repo, state)
    if episode_root is None:
        return (
            "IDLE_READY_FOR_NEXT_EPISODE",
            "TOPIC_AND_EVENT_PROPOSAL",
            "GENERATE_SCOPE_PROPOSAL_WITH_LUNA",
            "NO_EPISODE_ARTIFACTS",
            (),
        )

    evidence: list[str] = []

    upload_manifest = (
        episode_root
        / "publishing/publish-package-v1/youtube-upload-manifest-v1.json"
    )
    publish_manifest = (
        episode_root
        / "publishing/publish-package-v1/publish-manifest-v1.json"
    )
    final_review = episode_root / "publishing/human-final-review-v1.json"
    qa_report = episode_root / "qa/automatic-qa-report-v1.json"
    final_master = episode_root / "deliverables/episode-master-v1.mp4"
    final_receipt = (
        episode_root / "deliverables/episode-master-v1-receipt.json"
    )
    audio_master = episode_root / "audio/mix/episode-audio-master-v1.wav"
    media_queue = episode_root / "orchestration/media-production-queue-v1.json"
    storyboard = episode_root / "cinematic/storyboard-and-media-plan-v1.json"
    script = episode_root / "script/episode-script-v1.json"
    research = episode_root / "research/evidence-package-v1.json"
    approved_scope = episode_root / "contracts/approved-scope-v1.json"

    if _json_status(upload_manifest) == "READY_FOR_MANUAL_YOUTUBE_UPLOAD":
        evidence.append(str(upload_manifest.relative_to(repo)))
        return (
            "READY_TO_PUBLISH",
            "READY_TO_PUBLISH",
            "MANUAL_YOUTUBE_UPLOAD",
            "YOUTUBE_HANDOFF_MANIFEST_READY",
            tuple(evidence),
        )

    if publish_manifest.is_file() and _json_status(publish_manifest) == "READY_TO_PUBLISH":
        evidence.append(str(publish_manifest.relative_to(repo)))
        return (
            "READY_TO_PUBLISH",
            "READY_TO_PUBLISH",
            "MANUAL_YOUTUBE_UPLOAD",
            "PUBLISH_MANIFEST_READY",
            tuple(evidence),
        )

    if (
        final_review.is_file()
        and _json_status(final_review) in {"APPROVED", "READY_TO_PUBLISH"}
        and final_master.is_file()
    ):
        evidence.extend(
            str(path.relative_to(repo)) for path in (final_review, final_master)
        )
        return (
            "READY_TO_PUBLISH",
            "READY_TO_PUBLISH",
            "MANUAL_YOUTUBE_UPLOAD",
            "FINAL_REVIEW_APPROVED",
            tuple(evidence),
        )

    if (
        qa_report.is_file()
        and _json_status(qa_report) == "PASS"
        and final_master.is_file()
    ):
        evidence.extend(
            str(path.relative_to(repo)) for path in (qa_report, final_master)
        )
        return (
            "AWAITING_HUMAN_FINAL_REVIEW",
            "HUMAN_FINAL_REVIEW",
            "HUMAN_FINAL_REVIEW_AND_PUBLISHING_V1",
            "QA_PASS_AND_FINAL_MASTER_PRESENT",
            tuple(evidence),
        )

    if final_master.is_file():
        evidence.append(str(final_master.relative_to(repo)))
        if final_receipt.is_file():
            evidence.append(str(final_receipt.relative_to(repo)))
        return (
            "FINAL_RENDER_READY_FOR_QA",
            "AUTOMATIC_QA",
            "AUTOMATIC_QA_AND_PARTIAL_REPAIR_V1",
            "FINAL_MASTER_PRESENT_QA_NOT_PASSED",
            tuple(evidence),
        )

    if audio_master.is_file():
        evidence.append(str(audio_master.relative_to(repo)))
        return (
            "SFX_MIX_READY",
            "STRUCTURAL_MONTAGE",
            "STRUCTURAL_MONTAGE_AND_FINAL_RENDER_V1",
            "AUDIO_MASTER_PRESENT",
            tuple(evidence),
        )

    queue_present, queue_complete = _media_queue_complete(media_queue)
    if queue_present:
        evidence.append(str(media_queue.relative_to(repo)))
        if queue_complete:
            return (
                "MEDIA_ASSETS_COMPLETE",
                "SFX_DESIGN",
                "SFX_AND_AUDIO_MIX_V1",
                "MEDIA_QUEUE_ALL_COMPLETE",
                tuple(evidence),
            )
        return (
            "MEDIA_QUEUE_READY",
            "DESKTOP_MEDIA_EXECUTION",
            "DESKTOP_MEDIA_EXECUTION_V1",
            "MEDIA_QUEUE_HAS_PENDING_ITEMS",
            tuple(evidence),
        )

    if storyboard.is_file() and script.is_file() and research.is_file():
        evidence.extend(
            str(path.relative_to(repo)) for path in (research, script, storyboard)
        )
        return (
            "EDITORIAL_PIPELINE_COMPLETE_BUDGET_PREFLIGHT_QUEUED",
            "BUDGET_PREFLIGHT",
            "GRAPHICS_STORYBOARD_INTEGRATION_AND_MEDIA_QUEUE_V1",
            "EDITORIAL_ARTIFACTS_COMPLETE_MEDIA_QUEUE_MISSING",
            tuple(evidence),
        )

    if approved_scope.is_file():
        evidence.append(str(approved_scope.relative_to(repo)))
        return (
            "SCOPE_APPROVED_AUTOMATIC_PIPELINE_QUEUED",
            "EVIDENCE_RESEARCH",
            "AUTOMATIC_RESEARCH_SCRIPT_STORYBOARD_RUNNER_V1",
            "APPROVED_SCOPE_PRESENT",
            tuple(evidence),
        )

    proposal_relative = state.get("current_proposal_path_relative")
    if isinstance(proposal_relative, str) and proposal_relative.strip():
        proposal_path = repo / proposal_relative
        if proposal_path.is_file():
            evidence.append(str(proposal_path.relative_to(repo)))
            return (
                "AWAITING_HUMAN_SCOPE_REVIEW",
                "HUMAN_SCOPE_REVIEW",
                "HUMAN_SCOPE_REVIEW",
                "SCOPE_PROPOSAL_PRESENT",
                tuple(evidence),
            )

    return (
        "IDLE_READY_FOR_NEXT_EPISODE",
        "TOPIC_AND_EVENT_PROPOSAL",
        "GENERATE_SCOPE_PROPOSAL_WITH_LUNA",
        "NO_CANONICAL_RESUMABLE_ARTIFACT_FOUND",
        tuple(evidence),
    )


def diagnose_runtime_state(repo_root: Path) -> RuntimeStateDiagnosis:
    repo = repo_root.resolve()
    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path) if state_path.is_file() else {}
    episode_id, _ = _active_episode(repo, state)
    stored_status = str(state.get("status") or "UNKNOWN").upper()
    stored_stage = str(state.get("stage") or "UNKNOWN").upper()
    stored_directive = resolve_resume_directive_from_state(state)
    inferred_status, inferred_stage, inferred_next, reason, evidence = (
        _infer_from_artifacts(repo, state)
    )
    inferred_state = dict(state)
    inferred_state.update(
        {
            "status": inferred_status,
            "stage": inferred_stage,
            "next_stage": inferred_next,
            "current_episode_id": episode_id,
        }
    )
    inferred_directive = resolve_resume_directive_from_state(inferred_state)
    stale_actions = {"WAIT", "REFRESH", "INSPECT_BLOCKER"}
    active_like = (
        stored_status.endswith("_ACTIVE")
        or stored_status.startswith("RUNNING_")
        or stored_status.startswith("GENERATING_")
        or "EXECUTION_ACTIVE" in stored_status
    )
    state_differs = (
        inferred_status != stored_status
        or inferred_stage != stored_stage
    )
    protected_human_gate = bool(stored_directive.requires_human)
    needs_recovery = (
        not protected_human_gate
        and state_differs
        and (
            stored_directive.action in stale_actions
            or active_like
            or inferred_directive.action != stored_directive.action
        )
    )
    return RuntimeStateDiagnosis(
        current_episode_id=episode_id,
        stored_status=stored_status,
        stored_stage=stored_stage,
        stored_action=stored_directive.action,
        inferred_status=inferred_status,
        inferred_stage=inferred_stage,
        inferred_next_stage=inferred_next,
        inferred_action=inferred_directive.action,
        needs_recovery=needs_recovery,
        reason=reason,
        evidence_paths=evidence,
    )


def recover_runtime_state_from_artifacts(
    repo_root: Path,
    *,
    force: bool = False,
) -> RuntimeStateRecoveryResult:
    repo = repo_root.resolve()
    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path) if state_path.is_file() else {}
    diagnosis = diagnose_runtime_state(repo)
    if not diagnosis.needs_recovery and not force:
        return RuntimeStateRecoveryResult(
            changed=False,
            current_episode_id=diagnosis.current_episode_id,
            previous_status=diagnosis.stored_status,
            previous_stage=diagnosis.stored_stage,
            recovered_status=diagnosis.stored_status,
            recovered_stage=diagnosis.stored_stage,
            recovered_action=diagnosis.stored_action,
            reason="RECOVERY_NOT_REQUIRED",
            backup_path=None,
            state_path=state_path,
        )

    backup_path: Path | None = None
    if state_path.is_file():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = repo / BACKUP_DIR_REL / f"orchestrator-state-{stamp}.json"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(state_path.read_bytes())

    recovered = dict(state)
    recovered.update(
        {
            "schema_version": recovered.get(
                "schema_version",
                "siraj-autonomous-episode-orchestrator-state-v1",
            ),
            "status": diagnosis.inferred_status,
            "stage": diagnosis.inferred_stage,
            "next_stage": diagnosis.inferred_next_stage,
            "current_episode_id": diagnosis.current_episode_id,
            "last_error": None,
            "runtime_state_recovery": {
                "release": RELEASE,
                "reason": diagnosis.reason,
                "previous_status": diagnosis.stored_status,
                "previous_stage": diagnosis.stored_stage,
                "previous_action": diagnosis.stored_action,
                "evidence_paths": list(diagnosis.evidence_paths),
                "backup_path_relative": (
                    str(backup_path.relative_to(repo)).replace("\\", "/")
                    if backup_path is not None
                    else None
                ),
                "recovered_at_utc": _now(),
            },
            "updated_at_utc": _now(),
        }
    )
    if (
        diagnosis.inferred_status == "AWAITING_HUMAN_FINAL_REVIEW"
        and diagnosis.current_episode_id
    ):
        qa = (
            repo
            / "projects"
            / diagnosis.current_episode_id
            / "qa/automatic-qa-report-v1.json"
        )
        if qa.is_file():
            recovered["automatic_qa_report_sha256"] = _sha256(qa)
    if diagnosis.inferred_status == "READY_TO_PUBLISH":
        upload = (
            repo
            / "projects"
            / str(diagnosis.current_episode_id or "")
            / "publishing/publish-package-v1/youtube-upload-manifest-v1.json"
        )
        if upload.is_file() and _json_status(upload) == "READY_FOR_MANUAL_YOUTUBE_UPLOAD":
            recovered["youtube_handoff_status"] = "READY_FOR_MANUAL_YOUTUBE_UPLOAD"

    _write(state_path, recovered)
    directive = resolve_resume_directive_from_state(recovered)
    return RuntimeStateRecoveryResult(
        changed=True,
        current_episode_id=diagnosis.current_episode_id,
        previous_status=diagnosis.stored_status,
        previous_stage=diagnosis.stored_stage,
        recovered_status=diagnosis.inferred_status,
        recovered_stage=diagnosis.inferred_stage,
        recovered_action=directive.action,
        reason=diagnosis.reason,
        backup_path=backup_path,
        state_path=state_path,
    )
