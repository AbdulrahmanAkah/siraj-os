from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from src.application.autonomous_episode_orchestrator_v1 import (
    generate_next_episode_scope,
    load_orchestrator_state,
)
from src.application.automatic_qa_partial_repair_v1 import (
    run_automatic_qa_and_partial_repair,
)
from src.application.automatic_research_script_storyboard_runner_v1 import (
    run_editorial_pipeline,
)
from src.application.desktop_media_execution_v1 import (
    DesktopMediaExecutionError,
    MediaExecutionResult,
    MediaQueueRow,
    execute_elevenlabs_item,
    execute_runware_item,
    media_queue_rows,
    render_local_graphics_item,
)
from src.application.graphics_storyboard_media_queue_v1 import (
    integrate_graphics_and_build_media_queue,
)
from src.application.production_resume_router_v1 import (
    ProductionResumeDirective,
    resolve_resume_directive_from_state,
)
from src.application.sfx_audio_mix_v1 import run_sfx_audio_mix
from src.application.structural_montage_final_render_v1 import (
    run_structural_montage_final_render,
)
from src.application.youtube_publish_handoff_v1 import (
    complete_youtube_publish_handoff,
)

RELEASE = "SIRAJ_END_TO_END_PRODUCTION_AND_YOUTUBE_HANDOFF_V1"
ProgressCallback = Callable[[str, int | None], None]


class EndToEndProductionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EndToEndPlan:
    status: str
    stage: str
    action: str
    target_tab: str
    label_ar: str
    detail_ar: str
    current_episode_id: str | None
    pending_media_count: int
    pending_runware_count: int
    pending_elevenlabs_count: int
    pending_local_graphics_count: int
    pending_media_maximum_usd: float
    requires_openai_key: bool
    requires_runware_key: bool
    requires_elevenlabs_key: bool
    requires_human_gate: bool
    requires_paid_confirmation: bool
    ready_for_manual_youtube_upload: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EndToEndRunResult:
    status: str
    stop_reason: str
    final_status: str
    final_stage: str
    current_episode_id: str | None
    completed_actions: tuple[str, ...]
    completed_media_items: int
    recovered_runware_items: int
    maximum_authorized_media_usd: float
    ready_for_manual_youtube_upload: bool
    youtube_handoff_manifest_path: Path | None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["youtube_handoff_manifest_path"] = (
            str(self.youtube_handoff_manifest_path)
            if self.youtube_handoff_manifest_path is not None
            else None
        )
        return payload


def _pending_rows(repo_root: Path) -> tuple[MediaQueueRow, ...]:
    try:
        rows = media_queue_rows(repo_root)
    except Exception:
        return ()
    return tuple(row for row in rows if row.status != "COMPLETE")


def _pending_summary(rows: Sequence[MediaQueueRow]) -> dict[str, Any]:
    runware = [
        row
        for row in rows
        if row.media_kind in {"RUNWARE_IMAGE", "RUNWARE_VIDEO"}
    ]
    elevenlabs = [row for row in rows if row.media_kind == "ELEVENLABS_TTS"]
    local = [row for row in rows if row.media_kind == "LOCAL_GRAPHICS"]
    maximum = round(
        sum(
            float(row.maximum_authorized_usd)
            for row in (*runware, *elevenlabs)
        ),
        6,
    )
    return {
        "pending_media_count": len(rows),
        "pending_runware_count": len(runware),
        "pending_elevenlabs_count": len(elevenlabs),
        "pending_local_graphics_count": len(local),
        "pending_media_maximum_usd": maximum,
    }


def inspect_end_to_end_plan(repo_root: Path) -> EndToEndPlan:
    repo = repo_root.resolve()
    state = load_orchestrator_state(repo)
    directive = resolve_resume_directive_from_state(state)
    rows = _pending_rows(repo) if directive.action == "OPEN_MEDIA_EXECUTION" else ()
    summary = _pending_summary(rows)
    action = directive.action
    status = str(state.get("status") or directive.status)
    stage = str(state.get("stage") or directive.stage)
    episode_id = state.get("current_episode_id")
    if not isinstance(episode_id, str) or not episode_id.strip():
        episode_id = None

    ready = (
        status == "READY_TO_PUBLISH"
        and str(state.get("youtube_handoff_status", ""))
        == "READY_FOR_MANUAL_YOUTUBE_UPLOAD"
    )
    return EndToEndPlan(
        status=status,
        stage=stage,
        action=action,
        target_tab=directive.target_tab,
        label_ar=directive.label_ar,
        detail_ar=directive.detail_ar,
        current_episode_id=episode_id,
        requires_openai_key=action in {"GENERATE_SCOPE", "RUN_EDITORIAL"},
        requires_runware_key=summary["pending_runware_count"] > 0,
        requires_elevenlabs_key=summary["pending_elevenlabs_count"] > 0,
        requires_human_gate=directive.requires_human,
        requires_paid_confirmation=(
            directive.requires_paid_confirmation
            and summary["pending_media_maximum_usd"] > 0
        ),
        ready_for_manual_youtube_upload=ready,
        **summary,
    )


def _emit(
    progress: ProgressCallback | None,
    message: str,
    value: int | None,
) -> None:
    if progress is not None:
        progress(message, value)


def _execute_media_queue(
    repo_root: Path,
    *,
    runware_api_key: str,
    elevenlabs_api_key: str,
    confirmed_maximum_usd: float,
    progress: ProgressCallback | None,
) -> tuple[tuple[MediaExecutionResult, ...], int]:
    repo = repo_root.resolve()
    rows = sorted(_pending_rows(repo), key=lambda row: (row.queue_index, row.queue_id))
    expected = _pending_summary(rows)["pending_media_maximum_usd"]
    if abs(float(confirmed_maximum_usd) - expected) > 1e-6:
        raise EndToEndProductionError(
            "CONSOLIDATED_MEDIA_AUTHORIZATION_MISMATCH:"
            f"expected={expected:.6f}:confirmed={float(confirmed_maximum_usd):.6f}"
        )
    if any(
        row.media_kind in {"RUNWARE_IMAGE", "RUNWARE_VIDEO"}
        for row in rows
    ) and not runware_api_key.strip():
        raise EndToEndProductionError("RUNWARE_API_KEY_REQUIRED")
    if any(row.media_kind == "ELEVENLABS_TTS" for row in rows) and not elevenlabs_api_key.strip():
        raise EndToEndProductionError("ELEVENLABS_API_KEY_REQUIRED")

    results: list[MediaExecutionResult] = []
    recovered = 0
    total = max(1, len(rows))
    for index, row in enumerate(rows, start=1):
        base = int((index - 1) * 100 / total)
        _emit(
            progress,
            f"تنفيذ عنصر الوسائط {index}/{len(rows)} — {row.media_kind} — {row.source_id}",
            base,
        )
        try:
            if row.media_kind == "LOCAL_GRAPHICS":
                result = render_local_graphics_item(repo, row.queue_id)
            elif row.media_kind in {"RUNWARE_IMAGE", "RUNWARE_VIDEO"}:
                try:
                    result = execute_runware_item(
                        repo,
                        row.queue_id,
                        runware_api_key,
                        confirmed_maximum_usd=row.maximum_authorized_usd,
                    )
                except DesktopMediaExecutionError as exc:
                    if "ATTEMPT_ALREADY_LOCKED_USE_RECOVERY" not in str(exc):
                        raise
                    result = execute_runware_item(
                        repo,
                        row.queue_id,
                        runware_api_key,
                        confirmed_maximum_usd=row.maximum_authorized_usd,
                        recovery_only=True,
                    )
                    recovered += 1
            elif row.media_kind == "ELEVENLABS_TTS":
                result = execute_elevenlabs_item(
                    repo,
                    row.queue_id,
                    elevenlabs_api_key,
                    confirmed_maximum_usd=row.maximum_authorized_usd,
                )
            else:
                raise EndToEndProductionError(
                    "UNKNOWN_MEDIA_KIND:" + row.media_kind
                )
        except Exception as exc:
            raise EndToEndProductionError(
                f"MEDIA_QUEUE_ITEM_FAILED:{row.queue_id}:{exc}"
            ) from exc
        results.append(result)
        _emit(
            progress,
            f"اكتمل عنصر الوسائط {index}/{len(rows)}.",
            int(index * 100 / total),
        )

    remaining = _pending_rows(repo)
    if remaining:
        raise EndToEndProductionError(
            "MEDIA_QUEUE_NOT_COMPLETE_AFTER_AUTHORIZED_RUN:"
            + ",".join(row.queue_id for row in remaining)
        )
    return tuple(results), recovered


def run_to_next_human_gate(
    repo_root: Path,
    *,
    openai_api_key: str = "",
    runware_api_key: str = "",
    elevenlabs_api_key: str = "",
    confirmed_media_maximum_usd: float | None = None,
    progress: ProgressCallback | None = None,
    maximum_transitions: int = 12,
) -> EndToEndRunResult:
    repo = repo_root.resolve()
    completed: list[str] = []
    media_completed = 0
    recovered = 0
    authorized = float(confirmed_media_maximum_usd or 0.0)
    handoff_path: Path | None = None

    for transition in range(maximum_transitions):
        plan = inspect_end_to_end_plan(repo)
        _emit(
            progress,
            f"المرحلة {transition + 1}: {plan.label_ar}",
            None,
        )
        action = plan.action

        if action == "GENERATE_SCOPE":
            if not openai_api_key.strip():
                raise EndToEndProductionError("OPENAI_API_KEY_REQUIRED")
            generate_next_episode_scope(
                repo,
                openai_api_key,
                progress=progress,
            )
            completed.append("GENERATE_SCOPE")
            break

        if action == "REVIEW_SCOPE":
            break

        if action == "RUN_EDITORIAL":
            if not openai_api_key.strip():
                raise EndToEndProductionError("OPENAI_API_KEY_REQUIRED")
            run_editorial_pipeline(repo, openai_api_key, progress=progress)
            completed.append("EDITORIAL_PIPELINE")
            integrate_graphics_and_build_media_queue(repo)
            completed.append("MEDIA_QUEUE_BUILD")
            continue

        if action == "OPEN_MEDIA_EXECUTION":
            if plan.pending_media_count == 0:
                state = load_orchestrator_state(repo)
                if str(state.get("status", "")) != "MEDIA_ASSETS_COMPLETE":
                    raise EndToEndProductionError(
                        "MEDIA_DIRECTIVE_WITHOUT_PENDING_ITEMS_AND_WITHOUT_COMPLETE_STATE"
                    )
                continue
            if confirmed_media_maximum_usd is None:
                raise EndToEndProductionError(
                    "CONSOLIDATED_MEDIA_AUTHORIZATION_REQUIRED:"
                    f"maximum_usd={plan.pending_media_maximum_usd:.6f}"
                )
            results, recovered_count = _execute_media_queue(
                repo,
                runware_api_key=runware_api_key,
                elevenlabs_api_key=elevenlabs_api_key,
                confirmed_maximum_usd=authorized,
                progress=progress,
            )
            media_completed += len(results)
            recovered += recovered_count
            completed.append("AUTHORIZED_MEDIA_QUEUE")
            continue

        if action == "RUN_SFX":
            run_sfx_audio_mix(repo, progress=progress)
            completed.append("SFX_AUDIO_MIX")
            continue

        if action == "RUN_MONTAGE":
            run_structural_montage_final_render(repo, progress=progress)
            completed.append("STRUCTURAL_MONTAGE")
            continue

        if action == "RUN_QA":
            result = run_automatic_qa_and_partial_repair(repo, progress=progress)
            completed.append("AUTOMATIC_QA")
            if result.status != "AWAITING_HUMAN_FINAL_REVIEW":
                break
            continue

        if action == "OPEN_FINAL_REVIEW":
            break

        if action == "OPEN_PUBLISH_PACKAGE":
            handoff = complete_youtube_publish_handoff(repo)
            handoff_path = handoff.upload_manifest_path
            completed.append("YOUTUBE_PUBLISH_HANDOFF")
            break

        if action in {"WAIT", "INSPECT_BLOCKER", "REFRESH"}:
            break

        raise EndToEndProductionError("UNSUPPORTED_END_TO_END_ACTION:" + action)
    else:
        raise EndToEndProductionError(
            f"MAXIMUM_END_TO_END_TRANSITIONS_EXCEEDED:{maximum_transitions}"
        )

    final_state = load_orchestrator_state(repo)
    final_plan = inspect_end_to_end_plan(repo)
    final_status = str(final_state.get("status", "UNKNOWN"))
    final_stage = str(final_state.get("stage", "UNKNOWN"))
    if final_plan.ready_for_manual_youtube_upload:
        stop_reason = "READY_FOR_MANUAL_YOUTUBE_UPLOAD"
    elif final_plan.requires_human_gate:
        stop_reason = (
            "HUMAN_SCOPE_REVIEW_REQUIRED"
            if final_stage == "HUMAN_SCOPE_REVIEW"
            else "HUMAN_FINAL_REVIEW_REQUIRED"
        )
    elif final_plan.requires_paid_confirmation:
        stop_reason = "PAID_MEDIA_AUTHORIZATION_REQUIRED"
    elif final_plan.action == "WAIT":
        stop_reason = "STAGE_ALREADY_RUNNING"
    else:
        stop_reason = "ACTION_REQUIRED:" + final_plan.action

    return EndToEndRunResult(
        status="PASS",
        stop_reason=stop_reason,
        final_status=final_status,
        final_stage=final_stage,
        current_episode_id=final_plan.current_episode_id,
        completed_actions=tuple(completed),
        completed_media_items=media_completed,
        recovered_runware_items=recovered,
        maximum_authorized_media_usd=authorized,
        ready_for_manual_youtube_upload=(
            final_plan.ready_for_manual_youtube_upload
        ),
        youtube_handoff_manifest_path=handoff_path,
    )


def run_end_to_end_planner_smoke_test(output_root: Path) -> dict[str, Any]:
    root = output_root.resolve() / "end-to-end-planner-smoke"
    episode_id = "episode-999-smoke"
    state_path = (
        root
        / "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
    )
    queue_path = (
        root
        / "projects"
        / episode_id
        / "orchestration/media-production-queue-v1.json"
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        __import__("json").dumps(
            {
                "status": "MEDIA_QUEUE_READY",
                "stage": "RUNWARE_VIDEO_GENERATION",
                "current_episode_id": episode_id,
            }
        ),
        encoding="utf-8",
    )
    queue_path.write_text(
        __import__("json").dumps(
            {
                "queues": {
                    "runware_images": [
                        {
                            "queue_id": "IMG-001",
                            "queue_index": 1,
                            "shot_id": "SH-001",
                            "status": "PENDING",
                            "selected_model": "test",
                            "maximum_authorized_usd": 0.15,
                            "output_path_relative": "out/image.jpg",
                        }
                    ],
                    "runware_videos": [],
                    "local_graphics": [
                        {
                            "queue_id": "GFX-001",
                            "queue_index": 2,
                            "shot_id": "SH-002",
                            "status": "PENDING",
                            "graphic_type": "SOURCE_CARD",
                            "output_path_relative": "out/graphic.mp4",
                        }
                    ],
                    "elevenlabs_tts": [
                        {
                            "queue_id": "TTS-001",
                            "queue_index": 3,
                            "segment_id": "SEG-001",
                            "status": "PENDING",
                            "voice_slot": "PRIMARY",
                            "model_id": "test",
                            "text_ar": "هذا نص اختبار كاف لحساب الحصة.",
                            "output_path_relative": "out/tts.mp3",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    plan = inspect_end_to_end_plan(root)
    return {
        "status": "PASS" if plan.pending_media_count == 3 else "FAIL",
        "action": plan.action,
        "pending_media_count": plan.pending_media_count,
        "pending_runware_count": plan.pending_runware_count,
        "pending_elevenlabs_count": plan.pending_elevenlabs_count,
        "pending_local_graphics_count": plan.pending_local_graphics_count,
        "pending_media_maximum_usd": plan.pending_media_maximum_usd,
        "requires_paid_confirmation": plan.requires_paid_confirmation,
    }

# SIRAJ_PRODUCTION_STANDARD_V2_NATIVE_LOCAL_STAGES
from src.application.production_standard_v2_runtime import (
    run_v2_automatic_qa as run_automatic_qa_and_partial_repair,
    run_v2_sfx_audio_mix as run_sfx_audio_mix,
    run_v2_structural_montage as run_structural_montage_final_render,
)
