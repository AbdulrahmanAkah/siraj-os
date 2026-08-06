"""Consolidated production controller for SIRAJ Series Production Standard V2.

Installation and inspection are offline. Paid provider calls occur only after
one explicit desktop authorization. The controller then:
- executes seven Luna prompt batches and certifies 70 visual prompts;
- materializes the certified storyboard into the existing media queue;
- installs the approved 43-block narration queue;
- reuses the existing locked Runware, ElevenLabs, local graphics, SFX,
  montage, QA, recovery, and final-review pipeline;
- stops at the mandatory final human watch gate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from src.application.end_to_end_production_v1 import (
    EndToEndRunResult,
    inspect_end_to_end_plan,
    run_to_next_human_gate,
)
from src.application.episode_001_pipeline_adoption_v1 import (
    adopt_episode_001_for_pipeline,
)
import src.application.graphics_storyboard_media_queue_v1 as queue_builder
from src.application.luna_cinematic_prompt_director_v2 import (
    MAXIMUM_BATCH_RESERVE_USD,
    _apply_to_media_queue,
    execute_authorized_batch,
    finalize_certified_storyboard,
)

RELEASE = "SIRAJ_CONSOLIDATED_EPISODE_PRODUCTION_CONTROLLER_V2"
SCHEMA_VERSION = "siraj-consolidated-episode-production-controller-v2"
EPISODE_ID = "episode-001-adam"

TOTAL_EPISODE_HARD_CAP_USD = 40.0
GENERATED_VIDEO_PLANNED_USD = 29.514375
TTS_RESERVE_USD = 3.0
PROMPT_DIRECTION_RESERVE_USD = 0.35
OTHER_MEDIA_RESERVE_USD = 2.0
CONSOLIDATED_MAXIMUM_USD = round(
    GENERATED_VIDEO_PLANNED_USD
    + TTS_RESERVE_USD
    + PROMPT_DIRECTION_RESERVE_USD
    + OTHER_MEDIA_RESERVE_USD,
    6,
)

STANDARD_READINESS_REL = Path(
    "projects/episode-001-adam/orchestration/"
    "series-production-standard-v2-readiness.json"
)
PROMPT_PLAN_REL = Path(
    "projects/episode-001-adam/orchestration/"
    "luna-cinematic-prompt-direction-plan-v2.json"
)
TTS_PLAN_REL = Path(
    "projects/episode-001-adam/orchestration/"
    "full-episode-tts-execution-plan-production-standard-v2.json"
)
CERTIFIED_STORYBOARD_REL = Path(
    "projects/episode-001-adam/cinematic/"
    "storyboard-and-media-plan-luna-certified-v2.json"
)
MEDIA_QUEUE_REL = Path(
    "projects/episode-001-adam/orchestration/media-production-queue-v1.json"
)
AUTHORIZATION_REL = Path(
    "projects/episode-001-adam/evidence/"
    "consolidated-full-episode-production-authorization-v2.json"
)
CONTROLLER_PLAN_REL = Path(
    "projects/episode-001-adam/orchestration/"
    "consolidated-episode-production-plan-v2.json"
)
CONTROLLER_STATE_REL = Path(
    "projects/episode-001-adam/orchestration/"
    "consolidated-episode-production-state-v2.json"
)
DESKTOP_SNAPSHOT_REL = Path(
    "projects/episode-001-adam/orchestration/"
    "desktop-series-production-standard-v2-snapshot.json"
)
ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)

ProgressCallback = Callable[[str, int | None], None]


class ConsolidatedProductionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ConsolidatedProductionPlan:
    status: str
    episode_id: str
    standard_status: str
    director_review_status: str
    blocking_issue_count: int
    prompt_status: str
    prompt_item_count: int
    certified_prompt_count: int
    prompt_batch_count: int
    pending_prompt_batch_count: int
    tts_status: str
    tts_block_count: int
    generated_video_planned_usd: float
    prompt_direction_reserve_usd: float
    tts_reserve_usd: float
    other_media_reserve_usd: float
    maximum_authorized_usd: float
    episode_hard_cap_usd: float
    full_episode_production_authorized: bool
    next_stage: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ConsolidatedProductionResult:
    status: str
    stop_reason: str
    episode_id: str
    completed_prompt_batches: int
    reused_prompt_batches: int
    certified_prompt_count: int
    media_queue_pending_maximum_usd: float
    downstream_result: EndToEndRunResult | None
    authorization_path: Path
    controller_state_path: Path

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["downstream_result"] = (
            self.downstream_result.as_dict()
            if self.downstream_result is not None
            else None
        )
        payload["authorization_path"] = str(self.authorization_path)
        payload["controller_state_path"] = str(self.controller_state_path)
        return payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConsolidatedProductionError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ConsolidatedProductionError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return value
    return ()


def _emit(
    progress: ProgressCallback | None,
    message: str,
    value: int | None,
) -> None:
    if progress is not None:
        progress(message, value)


def _required_file(repo: Path, relative: Path) -> Path:
    path = repo / relative
    if not path.is_file():
        raise ConsolidatedProductionError(
            f"REQUIRED_PRODUCTION_ARTIFACT_MISSING:{relative.as_posix()}"
        )
    return path


def _prompt_counts(plan: Mapping[str, Any]) -> tuple[int, int, int]:
    batches = [
        item
        for item in _sequence(plan.get("batches"))
        if isinstance(item, Mapping)
    ]
    pending = sum(str(item.get("status")) != "COMPLETE" for item in batches)
    certified = int(plan.get("certified_prompt_count", 0) or 0)
    return len(batches), pending, certified


def inspect_consolidated_production_plan(
    repo_root: Path,
) -> ConsolidatedProductionPlan:
    repo = repo_root.resolve()
    readiness = _read(_required_file(repo, STANDARD_READINESS_REL))
    prompt_plan = _read(_required_file(repo, PROMPT_PLAN_REL))
    tts_plan = _read(_required_file(repo, TTS_PLAN_REL))

    standard_status = str(readiness.get("status") or "")
    packages = readiness.get("packages")
    packages = packages if isinstance(packages, Mapping) else {}
    director_review = str(
        packages.get("global_director_and_technical_review")
        or readiness.get("director_review_status")
        or "PASS"
    )
    blocking = int(readiness.get("blocking_issue_count", 0) or 0)
    if standard_status != "READY_FOR_FULL_EPISODE_REBUILD_AUTHORIZATION":
        raise ConsolidatedProductionError(
            f"STANDARD_V2_NOT_READY:{standard_status}"
        )
    if blocking != 0 or director_review != "PASS":
        raise ConsolidatedProductionError(
            "STANDARD_V2_BLOCKING_GATE_NOT_CLEAR"
        )

    batch_count, pending_batches, certified_count = _prompt_counts(prompt_plan)
    prompt_count = int(prompt_plan.get("prompt_item_count", 0) or 0)
    if prompt_count != 70 or batch_count != 7:
        raise ConsolidatedProductionError(
            "LUNA_PROMPT_PLAN_MUST_CONTAIN_70_ITEMS_IN_7_BATCHES"
        )

    tts_count = int(tts_plan.get("performance_block_count", 0) or 0)
    if tts_count != 43:
        raise ConsolidatedProductionError(
            f"TTS_PLAN_MUST_CONTAIN_43_BLOCKS:{tts_count}"
        )
    if tts_plan.get("full_episode_tts_authorized") is not False:
        raise ConsolidatedProductionError(
            "TTS_PLAN_MUST_START_UNAUTHORIZED"
        )

    metrics = readiness.get("metrics")
    metrics = metrics if isinstance(metrics, Mapping) else {}
    generated = float(
        metrics.get("planned_generated_video_spend_usd")
        or readiness.get("planned_generated_video_spend_usd")
        or GENERATED_VIDEO_PLANNED_USD
    )
    if abs(generated - GENERATED_VIDEO_PLANNED_USD) > 1e-6:
        raise ConsolidatedProductionError(
            f"GENERATED_VIDEO_PLAN_CHANGED:{generated}"
        )

    if certified_count == 70:
        status = "READY_FOR_CONSOLIDATED_FULL_EPISODE_AUTHORIZATION"
        next_stage = "CONSOLIDATED_FULL_EPISODE_AUTHORIZATION"
    else:
        status = (
            "READY_FOR_CONSOLIDATED_LUNA_PROMPT_AND_"
            "FULL_EPISODE_AUTHORIZATION"
        )
        next_stage = (
            "CONSOLIDATED_LUNA_PROMPT_AND_FULL_EPISODE_AUTHORIZATION"
        )

    plan = ConsolidatedProductionPlan(
        status=status,
        episode_id=EPISODE_ID,
        standard_status=standard_status,
        director_review_status=director_review,
        blocking_issue_count=blocking,
        prompt_status=str(prompt_plan.get("status") or ""),
        prompt_item_count=prompt_count,
        certified_prompt_count=certified_count,
        prompt_batch_count=batch_count,
        pending_prompt_batch_count=pending_batches,
        tts_status=str(tts_plan.get("status") or ""),
        tts_block_count=tts_count,
        generated_video_planned_usd=generated,
        prompt_direction_reserve_usd=PROMPT_DIRECTION_RESERVE_USD,
        tts_reserve_usd=TTS_RESERVE_USD,
        other_media_reserve_usd=OTHER_MEDIA_RESERVE_USD,
        maximum_authorized_usd=CONSOLIDATED_MAXIMUM_USD,
        episode_hard_cap_usd=TOTAL_EPISODE_HARD_CAP_USD,
        full_episode_production_authorized=False,
        next_stage=next_stage,
    )
    _write(
        repo / CONTROLLER_PLAN_REL,
        {
            "schema_version": SCHEMA_VERSION,
            "release": RELEASE,
            **plan.as_dict(),
            "authorization_policy": {
                "one_consolidated_human_confirmation": True,
                "one_lock_and_receipt_per_provider_item": True,
                "automatic_paid_retry": "FORBIDDEN",
                "hidden_paid_retry": "FORBIDDEN",
                "runware_recovery_reuses_task_uuid": True,
                "final_human_watch_gate": "REQUIRED",
                "youtube_upload": "MANUAL",
            },
            "created_at_utc": _now(),
        },
    )
    _update_desktop_snapshot(repo, plan)
    return plan


def _update_desktop_snapshot(
    repo: Path,
    plan: ConsolidatedProductionPlan,
) -> None:
    path = repo / DESKTOP_SNAPSHOT_REL
    if not path.is_file():
        return
    snapshot = _read(path)
    snapshot["consolidated_production_v2"] = {
        "release": RELEASE,
        "status": plan.status,
        "prompt_batches_pending": plan.pending_prompt_batch_count,
        "prompt_items": plan.prompt_item_count,
        "certified_prompts": plan.certified_prompt_count,
        "tts_blocks": plan.tts_block_count,
        "maximum_authorized_usd": plan.maximum_authorized_usd,
        "episode_hard_cap_usd": plan.episode_hard_cap_usd,
        "full_episode_production_authorized": False,
        "next_stage": plan.next_stage,
    }
    snapshot["next_action_ar"] = "تفويض موحد وبدء إنتاج الحلقة كاملة"
    snapshot["full_episode_production_authorized"] = False
    snapshot["updated_at_utc"] = _now()
    _write(path, snapshot)


def _record_authorization(
    repo: Path,
    plan: ConsolidatedProductionPlan,
    confirmed_maximum_usd: float,
) -> Path:
    if abs(confirmed_maximum_usd - plan.maximum_authorized_usd) > 1e-6:
        raise ConsolidatedProductionError(
            "CONSOLIDATED_AUTHORIZATION_MAXIMUM_MISMATCH:"
            f"expected={plan.maximum_authorized_usd:.6f}:"
            f"confirmed={confirmed_maximum_usd:.6f}"
        )
    if confirmed_maximum_usd > TOTAL_EPISODE_HARD_CAP_USD + 1e-9:
        raise ConsolidatedProductionError(
            "CONSOLIDATED_AUTHORIZATION_EXCEEDS_HARD_CAP"
        )
    path = repo / AUTHORIZATION_REL
    if path.is_file():
        previous = _read(path)
        if (
            str(previous.get("status")) == "ACTIVE"
            and abs(
                float(previous.get("maximum_authorized_usd", -1))
                - confirmed_maximum_usd
            )
            <= 1e-6
        ):
            return path
        raise ConsolidatedProductionError(
            "CONSOLIDATED_AUTHORIZATION_ALREADY_EXISTS_WITH_DIFFERENT_TERMS"
        )
    _write(
        path,
        {
            "schema_version": (
                "siraj-consolidated-full-episode-production-authorization-v2"
            ),
            "release": RELEASE,
            "episode_id": EPISODE_ID,
            "status": "ACTIVE",
            "decision": (
                "AUTHORIZED_ONE_CONSOLIDATED_PRODUCTION_RUN_"
                "TO_FINAL_HUMAN_GATE"
            ),
            "authorization_source": "EXPLICIT_DESKTOP_CONFIRMATION",
            "maximum_authorized_usd": confirmed_maximum_usd,
            "budget_components_usd": {
                "luna_prompt_direction": PROMPT_DIRECTION_RESERVE_USD,
                "generated_video": GENERATED_VIDEO_PLANNED_USD,
                "tts": TTS_RESERVE_USD,
                "other_media": OTHER_MEDIA_RESERVE_USD,
            },
            "episode_hard_cap_usd": TOTAL_EPISODE_HARD_CAP_USD,
            "automatic_paid_retry": "FORBIDDEN",
            "hidden_paid_retry": "FORBIDDEN",
            "final_human_watch_gate": "REQUIRED",
            "youtube_upload": "MANUAL",
            "authorized_at_utc": _now(),
        },
    )
    return path


def _controller_state(repo: Path, **values: Any) -> Path:
    path = repo / CONTROLLER_STATE_REL
    current = (
        _read(path)
        if path.is_file()
        else {
            "schema_version": (
                "siraj-consolidated-episode-production-state-v2"
            ),
            "release": RELEASE,
            "episode_id": EPISODE_ID,
            "created_at_utc": _now(),
        }
    )
    current.update(values)
    current["updated_at_utc"] = _now()
    _write(path, current)
    return path


def _ensure_active_episode(repo: Path) -> None:
    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path) if state_path.is_file() else {}
    if str(state.get("current_episode_id") or "") == EPISODE_ID:
        return
    adopt_episode_001_for_pipeline(repo)


def _certifications_by_shot(
    certified_storyboard: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    shots = certified_storyboard.get("shots")
    if not isinstance(shots, list):
        raise ConsolidatedProductionError(
            "CERTIFIED_STORYBOARD_SHOTS_REQUIRED"
        )
    result: dict[str, dict[str, Any]] = {}
    for shot in shots:
        if not isinstance(shot, Mapping):
            continue
        shot_id = str(shot.get("shot_id") or "")
        certification = shot.get("luna_prompt_certification_v2")
        if shot_id and isinstance(certification, Mapping):
            result[shot_id] = dict(certification)
    if len(result) != 70:
        raise ConsolidatedProductionError(
            f"EXPECTED_70_LUNA_CERTIFICATIONS:{len(result)}"
        )
    return result


V2_MEDIA_QUEUE_BUILDER_ALLOWED_STATES = {
    "EDITORIAL_PIPELINE_COMPLETE_BUDGET_PREFLIGHT_QUEUED",
    "GRAPHICS_MEDIA_QUEUE_FAILED",
    "MEDIA_QUEUE_READY",
    "RUNWARE_IMAGE_GENERATION_QUEUED",
}
V2_REBUILD_STALE_DOWNSTREAM_STATES = {
    "AUTOMATIC_QA_BLOCKED",
    "AUTOMATIC_QA_FAILED",
    "FINAL_RENDER_READY_FOR_QA",
    "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED",
    "AWAITING_HUMAN_FINAL_REVIEW",
    "READY_TO_PUBLISH",
}
V2_STATE_REBASE_BACKUP_REL = Path(
    "projects/episode-001-adam/orchestration/"
    "state-rebase-backups/"
    "orchestrator-before-v2-media-queue-materialization.json"
)


def _prepare_orchestrator_for_v2_media_queue_materialization(
    repo: Path,
) -> dict[str, Any]:
    """Rebase only stale V1 downstream state for the authorized V2 rebuild."""
    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path)
    episode_id = str(state.get("current_episode_id") or "")
    if episode_id != EPISODE_ID:
        raise ConsolidatedProductionError(
            "V2_MEDIA_QUEUE_STATE_REBASE_EPISODE_MISMATCH:"
            f"{episode_id}"
        )

    status = str(state.get("status") or "")
    if status in V2_MEDIA_QUEUE_BUILDER_ALLOWED_STATES:
        return {
            "status": "ALREADY_COMPATIBLE",
            "source_status": status,
            "state_changed": False,
            "backup_path": None,
        }
    if status not in V2_REBUILD_STALE_DOWNSTREAM_STATES:
        raise ConsolidatedProductionError(
            "V2_MEDIA_QUEUE_STATE_REBASE_NOT_ALLOWED:"
            + status
        )

    authorization_path = repo / AUTHORIZATION_REL
    if not authorization_path.is_file():
        raise ConsolidatedProductionError(
            "V2_MEDIA_QUEUE_STATE_REBASE_AUTHORIZATION_REQUIRED"
        )
    authorization = _read(authorization_path)
    if str(authorization.get("status") or "") != "ACTIVE":
        raise ConsolidatedProductionError(
            "V2_MEDIA_QUEUE_STATE_REBASE_AUTHORIZATION_NOT_ACTIVE"
        )

    certified = _read(
        _required_file(repo, CERTIFIED_STORYBOARD_REL)
    )
    certifications = _certifications_by_shot(certified)
    if len(certifications) != 70:
        raise ConsolidatedProductionError(
            "V2_MEDIA_QUEUE_STATE_REBASE_REQUIRES_70_CERTIFICATIONS"
        )

    backup_path = repo / V2_STATE_REBASE_BACKUP_REL
    if backup_path.is_file():
        backup = _read(backup_path)
        if (
            str(backup.get("current_episode_id") or "")
            != EPISODE_ID
        ):
            raise ConsolidatedProductionError(
                "V2_MEDIA_QUEUE_STATE_REBASE_BACKUP_CONFLICT"
            )
    else:
        _write(backup_path, state)

    revised = dict(state)
    revised["status"] = (
        "EDITORIAL_PIPELINE_COMPLETE_BUDGET_PREFLIGHT_QUEUED"
    )
    revised["stage"] = "BUDGET_PREFLIGHT"
    revised["next_stage"] = (
        "SIRAJ_V2_CERTIFIED_MEDIA_QUEUE_MATERIALIZATION"
    )
    revised["last_error"] = None
    revised["production_standard_v2_rebuild_state_rebase"] = {
        "release": (
            "SIRAJ_V2_STALE_QA_STATE_MEDIA_QUEUE_RESUME"
        ),
        "reason": (
            "OLD_V1_DOWNSTREAM_QA_STATE_INVALIDATED_BY_"
            "EXPLICIT_FULL_V2_REBUILD"
        ),
        "source_status": status,
        "source_stage": str(state.get("stage") or ""),
        "certified_prompt_count": 70,
        "paid_provider_requests": 0,
        "automatic_paid_retry": "FORBIDDEN",
        "rebase_at_utc": _now(),
    }
    revised["updated_at_utc"] = _now()
    _write(state_path, revised)
    return {
        "status": "PASS_STALE_STATE_REBASED_FOR_V2_QUEUE",
        "source_status": status,
        "state_changed": True,
        "backup_path": str(backup_path),
    }

def _materialize_certified_media_queue(repo: Path) -> None:
    episode_root = repo / "projects" / EPISODE_ID
    certified_storyboard = _read(
        _required_file(repo, CERTIFIED_STORYBOARD_REL)
    )
    certifications = _certifications_by_shot(certified_storyboard)

    _prepare_orchestrator_for_v2_media_queue_materialization(
        repo
    )

    old_storyboard = queue_builder.STORYBOARD_REL
    old_script = queue_builder.SCRIPT_REL
    old_backup = queue_builder.STORYBOARD_BACKUP_REL
    try:
        queue_builder.STORYBOARD_REL = Path(
            "cinematic/storyboard-and-media-plan-luna-certified-v2.json"
        )
        queue_builder.SCRIPT_REL = Path(
            "script/episode-script-production-standard-v2.json"
        )
        queue_builder.STORYBOARD_BACKUP_REL = Path(
            "cinematic/storyboard-and-media-plan-luna-certified-v2."
            "pre-graphics-integration.json"
        )
        queue_builder.integrate_graphics_and_build_media_queue(repo)
    finally:
        queue_builder.STORYBOARD_REL = old_storyboard
        queue_builder.SCRIPT_REL = old_script
        queue_builder.STORYBOARD_BACKUP_REL = old_backup

    queue_path = repo / MEDIA_QUEUE_REL
    queue = _read(queue_path)
    tts_plan = _read(repo / TTS_PLAN_REL)
    tts_queue: list[dict[str, Any]] = []
    for offset, item in enumerate(_sequence(tts_plan.get("queue"))):
        if not isinstance(item, Mapping):
            raise ConsolidatedProductionError("TTS_PLAN_QUEUE_ITEM_INVALID")
        tts_queue.append(
            {
                "queue_id": str(item.get("queue_id") or ""),
                "queue_index": 71 + offset,
                "block_id": str(item.get("block_id") or ""),
                "segment_id": str(item.get("segment_id") or ""),
                "voice_slot": str(item.get("speaker_key") or "NARRATOR"),
                "voice_id": str(item.get("voice_id") or ""),
                "model_id": str(item.get("model_id") or ""),
                "voice_settings": dict(item.get("voice_settings") or {}),
                "text_ar": str(item.get("text_ar") or ""),
                "pause_before_ms": int(
                    item.get("pause_before_ms", 0) or 0
                ),
                "pause_after_ms": int(item.get("pause_after_ms", 0) or 0),
                "status": "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED",
                "maximum_authorized_usd": float(
                    item.get("internal_reserve_share_usd", 0) or 0
                ),
                "output_path_relative": str(
                    item.get("output_path_relative") or ""
                ),
                "hidden_paid_retry": "FORBIDDEN",
                "automatic_resubmission": "FORBIDDEN",
            }
        )

    queues = queue.get("queues")
    if not isinstance(queues, dict):
        raise ConsolidatedProductionError("MEDIA_QUEUE_COLLECTIONS_REQUIRED")
    queues["elevenlabs_tts"] = tts_queue
    counts = queue.get("counts")
    if not isinstance(counts, dict):
        counts = {}
        queue["counts"] = counts
    counts["elevenlabs_tts_segments"] = len(tts_queue)
    counts["elevenlabs_voice_performers_used"] = 1
    counts["elevenlabs_multi_performer_required"] = False
    queue["release"] = "SIRAJ_MEDIA_QUEUE_PRODUCTION_STANDARD_V2"
    queue["schema_version"] = (
        "siraj-media-production-queue-production-standard-v2"
    )
    queue["production_standard_v2"] = {
        "certified_storyboard": str(CERTIFIED_STORYBOARD_REL).replace(
            "\\", "/"
        ),
        "luna_certified_prompt_count": 70,
        "tts_block_count": 43,
        "generated_video_planned_usd": GENERATED_VIDEO_PLANNED_USD,
        "automatic_paid_retry": "FORBIDDEN",
        "hidden_paid_retry": "FORBIDDEN",
    }
    _write(queue_path, queue)
    _apply_to_media_queue(episode_root, certifications)

    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path)
    state["current_episode_id"] = EPISODE_ID
    state["status"] = "MEDIA_QUEUE_READY"
    state["stage"] = "RUNWARE_VIDEO_GENERATION"
    state["updated_at_utc"] = _now()
    _write(state_path, state)


def run_consolidated_production_to_human_gate(
    repo_root: Path,
    *,
    openai_api_key: str,
    runware_api_key: str,
    elevenlabs_api_key: str,
    confirmed_maximum_usd: float,
    progress: ProgressCallback | None = None,
) -> ConsolidatedProductionResult:
    repo = repo_root.resolve()
    plan = inspect_consolidated_production_plan(repo)
    if not openai_api_key.strip():
        raise ConsolidatedProductionError(
            "OPENAI_API_KEY_REQUIRED_FOR_LUNA_PROMPT_DIRECTION"
        )
    if not runware_api_key.strip():
        raise ConsolidatedProductionError("RUNWARE_API_KEY_REQUIRED")
    if not elevenlabs_api_key.strip():
        raise ConsolidatedProductionError("ELEVENLABS_API_KEY_REQUIRED")
    authorization_path = _record_authorization(
        repo, plan, confirmed_maximum_usd
    )

    state_path = _controller_state(
        repo,
        status="RUNNING",
        stage="LUNA_PROMPT_DIRECTION",
        maximum_authorized_usd=confirmed_maximum_usd,
        automatic_paid_retry="FORBIDDEN",
        hidden_paid_retry="FORBIDDEN",
    )
    _ensure_active_episode(repo)

    prompt_plan = _read(repo / PROMPT_PLAN_REL)
    completed = 0
    reused = 0
    batches = [
        item
        for item in _sequence(prompt_plan.get("batches"))
        if isinstance(item, Mapping)
    ]
    for index, batch in enumerate(batches, start=1):
        batch_id = str(batch.get("batch_id") or "")
        _emit(
            progress,
            f"لونا يراجع برومبتات الدفعة {index}/{len(batches)} — {batch_id}",
            int((index - 1) * 18 / max(1, len(batches))),
        )
        result = execute_authorized_batch(
            repo,
            episode_id=EPISODE_ID,
            batch_id=batch_id,
            api_key=openai_api_key,
            confirmed_maximum_usd=MAXIMUM_BATCH_RESERVE_USD,
        )
        if int(result.get("provider_requests_this_run", 0)) == 0:
            reused += 1
        else:
            completed += 1

    _emit(progress, "اعتماد الستوريبورد ببرومبتات لونا النهائية.", 20)
    certification = finalize_certified_storyboard(
        repo, episode_id=EPISODE_ID
    )
    certified_count = int(certification.get("certified_prompt_count", 0))
    if certified_count != 70:
        raise ConsolidatedProductionError(
            f"LUNA_CERTIFICATION_INCOMPLETE:{certified_count}"
        )

    _controller_state(
        repo,
        status="RUNNING",
        stage="CERTIFIED_MEDIA_QUEUE_MATERIALIZATION",
        completed_prompt_batches=completed,
        reused_prompt_batches=reused,
        certified_prompt_count=certified_count,
    )
    _emit(
        progress,
        "بناء طابور الوسائط المعتمد وإدخال 43 كتلة صوتية.",
        24,
    )
    _materialize_certified_media_queue(repo)

    downstream_plan = inspect_end_to_end_plan(repo)
    media_maximum = float(downstream_plan.pending_media_maximum_usd)
    component_cap = (
        GENERATED_VIDEO_PLANNED_USD
        + TTS_RESERVE_USD
        + OTHER_MEDIA_RESERVE_USD
    )
    if media_maximum > component_cap + 1e-6:
        raise ConsolidatedProductionError(
            "MATERIALIZED_MEDIA_QUEUE_EXCEEDS_AUTHORIZED_COMPONENTS:"
            f"{media_maximum:.6f}"
        )

    _controller_state(
        repo,
        status="RUNNING",
        stage="MEDIA_SFX_MONTAGE_QA",
        media_queue_pending_maximum_usd=media_maximum,
    )
    _emit(
        progress,
        "بدء الصوت والصور والفيديو والجرافيك ثم المكساج والمونتاج وQA.",
        28,
    )
    downstream = run_to_next_human_gate(
        repo,
        openai_api_key=openai_api_key,
        runware_api_key=runware_api_key,
        elevenlabs_api_key=elevenlabs_api_key,
        confirmed_media_maximum_usd=media_maximum,
        progress=progress,
        maximum_transitions=16,
    )

    acceptable = {
        "HUMAN_FINAL_REVIEW_REQUIRED",
        "READY_FOR_MANUAL_YOUTUBE_UPLOAD",
    }
    status = (
        "PASS_AWAITING_FINAL_HUMAN_WATCH"
        if downstream.stop_reason in acceptable
        else "STOPPED_AT_FAIL_CLOSED_GATE"
    )
    state_path = _controller_state(
        repo,
        status=status,
        stage=downstream.final_stage,
        stop_reason=downstream.stop_reason,
        downstream_result=downstream.as_dict(),
        full_episode_production_authorized=True,
        youtube_upload="MANUAL",
    )
    return ConsolidatedProductionResult(
        status=status,
        stop_reason=downstream.stop_reason,
        episode_id=EPISODE_ID,
        completed_prompt_batches=completed,
        reused_prompt_batches=reused,
        certified_prompt_count=certified_count,
        media_queue_pending_maximum_usd=media_maximum,
        downstream_result=downstream,
        authorization_path=authorization_path,
        controller_state_path=state_path,
    )

# SIRAJ_EXPLICIT_LUNA_INVALID_OUTPUT_RETRY_V2
from dataclasses import replace as _siraj_retry_replace
from src.application.luna_invalid_output_recovery_v2 import (
    SUPPLEMENTAL_MAXIMUM_USD as _SIRAJ_LUNA_RETRY_MAXIMUM_USD,
    create_explicit_retry_authorization as _siraj_create_retry_authorization,
    execute_authorized_batch_with_explicit_retry as execute_authorized_batch,
    inspect_invalid_luna_retry as _siraj_inspect_invalid_luna_retry,
)


_siraj_base_inspect_consolidated_plan = (
    inspect_consolidated_production_plan
)
_siraj_base_record_consolidated_authorization = (
    _record_authorization
)


def inspect_consolidated_production_plan(
    repo_root: Path,
) -> ConsolidatedProductionPlan:
    plan = _siraj_base_inspect_consolidated_plan(
        repo_root
    )
    inspection = _siraj_inspect_invalid_luna_retry(
        repo_root,
        EPISODE_ID,
    )
    if inspection.get("manual_review_required") is True:
        raise ConsolidatedProductionError(
            "LUNA_EXPLICIT_RETRY_ALREADY_CONSUMED_"
            "MANUAL_REVIEW_REQUIRED"
        )
    if inspection.get("retry_required") is not True:
        return plan

    revised_maximum = round(
        plan.maximum_authorized_usd
        + _SIRAJ_LUNA_RETRY_MAXIMUM_USD,
        6,
    )
    if revised_maximum > plan.episode_hard_cap_usd:
        raise ConsolidatedProductionError(
            "LUNA_EXPLICIT_RETRY_WOULD_EXCEED_HARD_CAP"
        )

    revised = _siraj_retry_replace(
        plan,
        status=(
            "READY_FOR_EXPLICIT_LUNA_RETRY_AND_"
            "FULL_EPISODE_AUTHORIZATION"
        ),
        prompt_status=(
            "EXPLICIT_LUNA_RETRY_REQUIRED:"
            + str(inspection.get("batch_id") or "")
        ),
        maximum_authorized_usd=revised_maximum,
        next_stage=(
            "EXPLICIT_LUNA_RETRY_AND_FULL_EPISODE_AUTHORIZATION"
        ),
    )
    _write(
        Path(repo_root).resolve() / CONTROLLER_PLAN_REL,
        {
            "schema_version": SCHEMA_VERSION,
            "release": RELEASE,
            **revised.as_dict(),
            "supplemental_luna_retry": inspection,
            "automatic_paid_retry": "FORBIDDEN",
            "hidden_paid_retry": "FORBIDDEN",
            "updated_at_utc": _now(),
        },
    )
    _update_desktop_snapshot(
        Path(repo_root).resolve(),
        revised,
    )
    return revised


def _record_authorization(
    repo: Path,
    plan: ConsolidatedProductionPlan,
    confirmed_maximum_usd: float,
) -> Path:
    inspection = _siraj_inspect_invalid_luna_retry(
        repo,
        EPISODE_ID,
    )
    if inspection.get("retry_required") is not True:
        return _siraj_base_record_consolidated_authorization(
            repo,
            plan,
            confirmed_maximum_usd,
        )

    expected = round(
        CONSOLIDATED_MAXIMUM_USD
        + _SIRAJ_LUNA_RETRY_MAXIMUM_USD,
        6,
    )
    if abs(
        float(confirmed_maximum_usd) - expected
    ) > 1e-6:
        raise ConsolidatedProductionError(
            "LUNA_RETRY_TOTAL_AUTHORIZATION_MISMATCH:"
            f"expected={expected:.6f}:"
            f"confirmed={float(confirmed_maximum_usd):.6f}"
        )

    main_path = repo / AUTHORIZATION_REL
    if main_path.is_file():
        main = _read(main_path)
        if (
            str(main.get("status") or "") != "ACTIVE"
            or abs(
                float(
                    main.get(
                        "maximum_authorized_usd",
                        -1.0,
                    )
                )
                - CONSOLIDATED_MAXIMUM_USD
            )
            > 1e-6
        ):
            raise ConsolidatedProductionError(
                "ORIGINAL_CONSOLIDATED_AUTHORIZATION_INVALID"
            )
    else:
        base_plan = _siraj_retry_replace(
            plan,
            maximum_authorized_usd=(
                CONSOLIDATED_MAXIMUM_USD
            ),
        )
        main_path = (
            _siraj_base_record_consolidated_authorization(
                repo,
                base_plan,
                CONSOLIDATED_MAXIMUM_USD,
            )
        )

    _siraj_create_retry_authorization(
        repo,
        episode_id=EPISODE_ID,
        batch_id=str(
            inspection.get("batch_id") or ""
        ),
        confirmed_supplemental_usd=(
            _SIRAJ_LUNA_RETRY_MAXIMUM_USD
        ),
        effective_consolidated_maximum_usd=expected,
        episode_hard_cap_usd=(
            TOTAL_EPISODE_HARD_CAP_USD
        ),
    )
    return main_path

# SIRAJ_LUNA_SAFE_TECHNICAL_REPAIR_BUDGET_V1
from dataclasses import replace as _siraj_safe_repair_replace
from src.application.luna_safe_technical_repair_v1 import (
    SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD as _SIRAJ_SAFE_REPAIR_RESERVE_USD,
    create_safe_repair_authorization as _siraj_create_safe_repair_authorization,
)


_siraj_pre_safe_repair_inspect_plan = (
    inspect_consolidated_production_plan
)
_siraj_pre_safe_repair_record_authorization = (
    _record_authorization
)


def inspect_consolidated_production_plan(
    repo_root: Path,
) -> ConsolidatedProductionPlan:
    plan = _siraj_pre_safe_repair_inspect_plan(
        repo_root
    )
    revised_maximum = round(
        plan.maximum_authorized_usd
        + _SIRAJ_SAFE_REPAIR_RESERVE_USD,
        6,
    )
    if revised_maximum > plan.episode_hard_cap_usd:
        raise ConsolidatedProductionError(
            "SAFE_TECHNICAL_REPAIR_RESERVE_EXCEEDS_HARD_CAP"
        )
    revised = _siraj_safe_repair_replace(
        plan,
        maximum_authorized_usd=revised_maximum,
    )
    _write(
        Path(repo_root).resolve() / CONTROLLER_PLAN_REL,
        {
            "schema_version": SCHEMA_VERSION,
            "release": RELEASE,
            **revised.as_dict(),
            "safe_technical_repair": {
                "mode": "AUTOMATIC_BOUNDED",
                "reserve_usd": (
                    _SIRAJ_SAFE_REPAIR_RESERVE_USD
                ),
                "maximum_calls": 3,
                "maximum_files_per_repair": 5,
                "maximum_changed_lines_per_repair": 200,
                "automatic_media_retry": "FORBIDDEN",
                "stop_policy": (
                    "STOP_ONLY_WHEN_USER_ACTION_REQUIRED"
                ),
            },
            "updated_at_utc": _now(),
        },
    )
    _update_desktop_snapshot(
        Path(repo_root).resolve(),
        revised,
    )
    return revised


def _record_authorization(
    repo: Path,
    plan: ConsolidatedProductionPlan,
    confirmed_maximum_usd: float,
) -> Path:
    base_maximum = round(
        float(confirmed_maximum_usd)
        - _SIRAJ_SAFE_REPAIR_RESERVE_USD,
        6,
    )
    if base_maximum <= 0:
        raise ConsolidatedProductionError(
            "SAFE_REPAIR_BASE_AUTHORIZATION_INVALID"
        )
    base_plan = _siraj_safe_repair_replace(
        plan,
        maximum_authorized_usd=base_maximum,
    )
    main_path = _siraj_pre_safe_repair_record_authorization(
        repo,
        base_plan,
        base_maximum,
    )
    _siraj_create_safe_repair_authorization(
        repo,
        confirmed_reserve_usd=(
            _SIRAJ_SAFE_REPAIR_RESERVE_USD
        ),
        effective_consolidated_maximum_usd=(
            confirmed_maximum_usd
        ),
        episode_hard_cap_usd=(
            TOTAL_EPISODE_HARD_CAP_USD
        ),
    )
    return main_path

# SIRAJ_WINDOWS_SNAPSHOT_PERMISSION_RECOVERY_ANCHORLESS_V2
DESKTOP_SNAPSHOT_PENDING_REL = Path(
    "projects/episode-001-adam/orchestration/"
    "desktop-series-production-standard-v2-snapshot.pending.json"
)


def _siraj_desktop_snapshot_patch(
    plan: ConsolidatedProductionPlan,
) -> dict[str, Any]:
    return {
        "consolidated_production_v2": {
            "release": RELEASE,
            "status": plan.status,
            "prompt_batches_pending": (
                plan.pending_prompt_batch_count
            ),
            "prompt_items": plan.prompt_item_count,
            "certified_prompts": plan.certified_prompt_count,
            "tts_blocks": plan.tts_block_count,
            "maximum_authorized_usd": (
                plan.maximum_authorized_usd
            ),
            "episode_hard_cap_usd": (
                plan.episode_hard_cap_usd
            ),
            "full_episode_production_authorized": False,
            "next_stage": plan.next_stage,
        },
        "next_action_ar": (
            "تفويض موحد وبدء إنتاج الحلقة كاملة"
        ),
        "full_episode_production_authorized": False,
        "updated_at_utc": _now(),
    }


def _siraj_read_snapshot_with_windows_retry(
    path: Path,
    *,
    attempts: int = 8,
    initial_delay_seconds: float = 0.05,
) -> dict[str, Any]:
    from time import sleep

    last_error: Exception | None = None
    delay = initial_delay_seconds
    for attempt in range(attempts):
        try:
            value = json.loads(
                path.read_text(encoding="utf-8-sig")
            )
            if not isinstance(value, dict):
                raise ConsolidatedProductionError(
                    f"JSON_OBJECT_REQUIRED:{path}"
                )
            return value
        except PermissionError as exc:
            last_error = exc
        except OSError as exc:
            if getattr(exc, "winerror", None) not in {
                5,
                13,
                32,
                33,
            }:
                raise
            last_error = exc

        if attempt + 1 < attempts:
            sleep(delay)
            delay = min(delay * 1.8, 0.45)

    assert last_error is not None
    raise last_error


def _siraj_write_pending_snapshot_patch(
    repo: Path,
    *,
    patch: Mapping[str, Any],
    error: Exception,
) -> None:
    pending_path = repo / DESKTOP_SNAPSHOT_PENDING_REL
    try:
        _write(
            pending_path,
            {
                "schema_version": (
                    "siraj-desktop-snapshot-pending-update-v2"
                ),
                "release": RELEASE,
                "status": (
                    "PENDING_TRANSIENT_WINDOWS_FILE_ACCESS"
                ),
                "target_path_relative": str(
                    DESKTOP_SNAPSHOT_REL
                ).replace("\\", "/"),
                "patch": dict(patch),
                "last_error": str(error),
                "provider_requests": 0,
                "paid_provider_requests": 0,
                "created_at_utc": _now(),
            },
        )
    except OSError:
        # This sidecar is also a derived UI artifact. It must never stop
        # production when the authoritative state remains valid.
        return


def _update_desktop_snapshot(
    repo: Path,
    plan: ConsolidatedProductionPlan,
) -> dict[str, Any]:
    """Update a derived UI cache without blocking production on Windows.

    Authoritative plans, provider locks, receipts, budgets and controller state
    remain fail-closed. Only this desktop snapshot can be deferred.
    """
    path = repo / DESKTOP_SNAPSHOT_REL
    pending_path = repo / DESKTOP_SNAPSHOT_PENDING_REL
    patch = _siraj_desktop_snapshot_patch(plan)

    if not path.exists():
        snapshot: dict[str, Any] = {}
    elif not path.is_file():
        error = PermissionError(
            f"DESKTOP_SNAPSHOT_NOT_A_REGULAR_FILE:{path}"
        )
        _siraj_write_pending_snapshot_patch(
            repo,
            patch=patch,
            error=error,
        )
        return {
            "status": "DEFERRED_DESKTOP_SNAPSHOT_UPDATE",
            "reason": str(error),
        }
    else:
        try:
            snapshot = _siraj_read_snapshot_with_windows_retry(
                path
            )
        except (PermissionError, OSError) as exc:
            _siraj_write_pending_snapshot_patch(
                repo,
                patch=patch,
                error=exc,
            )
            return {
                "status": "DEFERRED_DESKTOP_SNAPSHOT_UPDATE",
                "reason": str(exc),
            }
        except (
            json.JSONDecodeError,
            ConsolidatedProductionError,
        ):
            # This is a derived cache. Rebuild from authoritative fields.
            snapshot = {}

    snapshot.update(patch)
    try:
        _write(path, snapshot)
    except (PermissionError, OSError) as exc:
        _siraj_write_pending_snapshot_patch(
            repo,
            patch=patch,
            error=exc,
        )
        return {
            "status": "DEFERRED_DESKTOP_SNAPSHOT_UPDATE",
            "reason": str(exc),
        }

    try:
        if pending_path.is_file():
            pending_path.unlink()
    except OSError:
        pass

    return {
        "status": "PASS_DESKTOP_SNAPSHOT_UPDATED",
        "path": str(path),
    }

# SIRAJ_NATIVE_PRODUCTION_STANDARD_V2_CONTROLLER_V1
from src.application.production_standard_v2_native_assets import (
    EPISODE_HARD_CAP_USD as _SIRAJ_NATIVE_HARD_CAP,
    GENERATION_ID as _SIRAJ_NATIVE_GENERATION_ID,
    inspect_native_execution_plan as _siraj_native_inspect,
    materialize_native_media_queue as _siraj_native_materialize,
)
from src.application.production_pipeline_certification_gate_v1 import (
    ProductionPipelineCertificationError as _SirajNativeGateError,
    ensure_full_pipeline_certified as _siraj_native_gate,
)

_SIRAJ_NATIVE_REPO_ROOT = Path(__file__).resolve().parents[2]
try:
    CONSOLIDATED_MAXIMUM_USD = float(
        _siraj_native_inspect(_SIRAJ_NATIVE_REPO_ROOT)[
            "pending_media_maximum_usd"
        ]
    )
except Exception:
    # The installer materializes the native queue before production/tests.
    # Keep importability for isolated tooling that has no episode artifacts.
    pass


def inspect_consolidated_production_plan(
    repo_root: Path,
) -> ConsolidatedProductionPlan:
    repo = repo_root.resolve()
    native = _siraj_native_inspect(repo)
    plan = ConsolidatedProductionPlan(
        status=native["status"],
        episode_id=EPISODE_ID,
        standard_status=(
            "READY_FOR_FULL_EPISODE_REBUILD_AUTHORIZATION"
        ),
        director_review_status="PASS",
        blocking_issue_count=0,
        prompt_status=(
            "ALL_LUNA_BATCHES_COMPLETE_AND_CERTIFIED"
        ),
        prompt_item_count=70,
        certified_prompt_count=70,
        prompt_batch_count=7,
        pending_prompt_batch_count=0,
        tts_status=(
            "READY_AWAITING_CONSOLIDATED_AUTHORIZATION"
        ),
        tts_block_count=43,
        generated_video_planned_usd=float(
            native["generated_video_maximum_usd"]
        ),
        prompt_direction_reserve_usd=0.0,
        tts_reserve_usd=float(
            native["tts_maximum_usd"]
        ),
        other_media_reserve_usd=float(
            native["image_maximum_usd"]
        ),
        maximum_authorized_usd=float(
            native["consolidated_maximum_usd"]
        ),
        episode_hard_cap_usd=float(
            native["episode_hard_cap_usd"]
        ),
        full_episode_production_authorized=False,
        next_stage=(
            "CONSOLIDATED_PRODUCTION_STANDARD_V2_EXECUTION"
        ),
    )
    _write(
        repo / CONTROLLER_PLAN_REL,
        {
            "schema_version": (
                "siraj-consolidated-production-controller-v2-native"
            ),
            "release": RELEASE,
            **plan.as_dict(),
            "production_generation_id": (
                _SIRAJ_NATIVE_GENERATION_ID
            ),
            "native_asset_counts": dict(
                native.get("counts") or {}
            ),
            "pending_media_maximum_usd": native[
                "pending_media_maximum_usd"
            ],
            "safe_technical_repair_reserve_usd": native[
                "safe_repair_reserve_usd"
            ],
            "authorization_policy": {
                "one_consolidated_human_confirmation": True,
                "one_lock_and_receipt_per_asset": True,
                "automatic_paid_retry": "FORBIDDEN",
                "hidden_paid_retry": "FORBIDDEN",
                "final_human_watch_gate": "REQUIRED",
                "youtube_upload": "MANUAL",
            },
            "created_at_utc": _now(),
        },
    )
    _update_desktop_snapshot(repo, plan)
    return plan


def _siraj_native_authorization(
    repo: Path,
    plan: ConsolidatedProductionPlan,
    confirmed_maximum_usd: float,
) -> Path:
    confirmed = float(confirmed_maximum_usd)
    if abs(
        confirmed - plan.maximum_authorized_usd
    ) > 1e-6:
        raise ConsolidatedProductionError(
            "EXPLICIT_AUTHORIZATION_MAXIMUM_MISMATCH:"
            f"expected={plan.maximum_authorized_usd:.6f}:"
            f"confirmed={confirmed:.6f}"
        )
    if confirmed > _SIRAJ_NATIVE_HARD_CAP + 1e-9:
        raise ConsolidatedProductionError(
            "CONSOLIDATED_MAXIMUM_EXCEEDS_HARD_CAP"
        )
    path = repo / AUTHORIZATION_REL
    native = _siraj_native_inspect(repo)
    _write(
        path,
        {
            "schema_version": (
                "siraj-consolidated-full-episode-"
                "production-authorization-v2-native"
            ),
            "release": RELEASE,
            "status": "ACTIVE",
            "episode_id": EPISODE_ID,
            "production_generation_id": (
                _SIRAJ_NATIVE_GENERATION_ID
            ),
            "decision": (
                "AUTHORIZED_PRODUCTION_STANDARD_V2_"
                "NATIVE_FULL_EPISODE_EXECUTION"
            ),
            "maximum_authorized_usd": confirmed,
            "pending_media_maximum_usd": native[
                "pending_media_maximum_usd"
            ],
            "safe_technical_repair_reserve_usd": native[
                "safe_repair_reserve_usd"
            ],
            "episode_hard_cap_usd": (
                _SIRAJ_NATIVE_HARD_CAP
            ),
            "runware_video_maximum_usd": native[
                "generated_video_maximum_usd"
            ],
            "runware_image_maximum_usd": native[
                "image_maximum_usd"
            ],
            "tts_maximum_usd": native[
                "tts_maximum_usd"
            ],
            "luna_prompt_requests_remaining": 0,
            "automatic_paid_retry": "FORBIDDEN",
            "hidden_paid_retry": "FORBIDDEN",
            "historical_legacy_spend": (
                "REPORTED_SEPARATELY_NOT_CHARGED_TO_"
                "CURRENT_GENERATION_CAP"
            ),
            "authorization_source": (
                "ONE_CONSOLIDATED_DESKTOP_CONFIRMATION"
            ),
            "authorized_at_utc": _now(),
        },
    )
    return path


def run_consolidated_production_to_human_gate(
    repo_root: Path,
    *,
    openai_api_key: str,
    runware_api_key: str,
    elevenlabs_api_key: str,
    confirmed_maximum_usd: float,
    progress: ProgressCallback | None = None,
) -> ConsolidatedProductionResult:
    repo = repo_root.resolve()
    try:
        _siraj_native_gate(repo)
    except _SirajNativeGateError as exc:
        raise ConsolidatedProductionError(
            str(exc)
        ) from exc

    plan = inspect_consolidated_production_plan(repo)
    if not runware_api_key.strip():
        raise ConsolidatedProductionError(
            "RUNWARE_API_KEY_REQUIRED"
        )
    if not elevenlabs_api_key.strip():
        raise ConsolidatedProductionError(
            "ELEVENLABS_API_KEY_REQUIRED"
        )
    if not openai_api_key.strip():
        raise ConsolidatedProductionError(
            "OPENAI_API_KEY_REQUIRED_FOR_SAFE_TECHNICAL_REPAIR"
        )

    authorization_path = _siraj_native_authorization(
        repo,
        plan,
        confirmed_maximum_usd,
    )
    _emit(
        progress,
        "تحميل طابور V2 الأصلي: 137 فيديو، 61 صورة، "
        "6 جرافيك، و43 كتلة صوتية.",
        2,
    )
    queue = _siraj_native_materialize(
        repo,
        live=True,
    )
    native = _siraj_native_inspect(repo)
    media_maximum = float(
        native["pending_media_maximum_usd"]
    )

    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path)
    state.update(
        {
            "status": "MEDIA_QUEUE_READY",
            "stage": "BUDGET_PREFLIGHT",
            "next_stage": (
                "PRODUCTION_STANDARD_V2_NATIVE_MEDIA_EXECUTION"
            ),
            "production_generation_id": (
                _SIRAJ_NATIVE_GENERATION_ID
            ),
            "full_episode_production_authorized": True,
            "consolidated_authorization_path_relative": str(
                authorization_path.relative_to(repo)
            ).replace("\\", "/"),
            "media_queue_sha256": str(
                queue.get("queue_sha256") or ""
            ),
            "last_error": None,
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)

    _emit(
        progress,
        "بدء التنفيذ المتسلسل المقفل لكل أصل ثم الصوت "
        "والمونتاج وQA.",
        4,
    )
    downstream = run_to_next_human_gate(
        repo,
        openai_api_key=openai_api_key,
        runware_api_key=runware_api_key,
        elevenlabs_api_key=elevenlabs_api_key,
        confirmed_media_maximum_usd=media_maximum,
        progress=progress,
        maximum_transitions=16,
    )
    acceptable = {
        "HUMAN_FINAL_REVIEW_REQUIRED",
        "READY_FOR_MANUAL_YOUTUBE_UPLOAD",
    }
    status = (
        "PASS_AWAITING_FINAL_HUMAN_WATCH"
        if downstream.stop_reason in acceptable
        else "STOPPED_AT_FAIL_CLOSED_GATE"
    )
    state = _read(state_path)
    state.update(
        {
            "status": status,
            "stage": downstream.final_stage,
            "stop_reason": downstream.stop_reason,
            "downstream_result": downstream.as_dict(),
            "production_generation_id": (
                _SIRAJ_NATIVE_GENERATION_ID
            ),
            "full_episode_production_authorized": True,
            "youtube_upload": "MANUAL",
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)
    return ConsolidatedProductionResult(
        status=status,
        stop_reason=downstream.stop_reason,
        episode_id=EPISODE_ID,
        completed_prompt_batches=0,
        reused_prompt_batches=7,
        certified_prompt_count=70,
        media_queue_pending_maximum_usd=(
            media_maximum
        ),
        downstream_result=downstream,
        authorization_path=authorization_path,
        controller_state_path=state_path,
    )

# SIRAJ_NATIVE_BUDGET_FLOAT_NORMALIZATION_V1
from src.application.luna_safe_technical_repair_v1 import (
    SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD
    as _SIRAJ_NATIVE_SAFE_REPAIR_RESERVE_USD,
)

try:
    _siraj_native_budget_snapshot = _siraj_native_inspect(
        Path(__file__).resolve().parents[2]
    )
    _siraj_native_rounded_total_maximum = round(
        float(
            _siraj_native_budget_snapshot[
                "pending_media_maximum_usd"
            ]
        )
        + float(_SIRAJ_NATIVE_SAFE_REPAIR_RESERVE_USD),
        6,
    )
    CONSOLIDATED_MAXIMUM_USD = (
        _siraj_native_rounded_total_maximum
        - float(_SIRAJ_NATIVE_SAFE_REPAIR_RESERVE_USD)
    )
except Exception:
    pass
