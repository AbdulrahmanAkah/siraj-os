"""V6 state overlay for the ORIGINAL SIRAJ desktop dashboard.

This module does not create a replacement desktop application. It overlays the
existing v1.3 dashboard snapshot with the canonical V6 Autopilot runtime and
artifact state so the original interface displays the actual current pipeline.
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any, Mapping

from .models import ActivityRecord, DashboardSnapshot, EpisodeRecord, EpisodeStage

EP2_ID = "episode-002-adam-temptation-fall-repentance"

V6_STAGE_AR = {
    "TOPIC_SELECTION": "اختيار موضوع الحلقة",
    "SOURCE_RESEARCH_FROM_ZERO": "البحث من الصفر",
    "SOURCE_CLAIM_MATRIX": "مصفوفة المصادر والادعاءات",
    "STORY_ARCHITECTURE": "هندسة القصة",
    "ICONIC_CINEMATIC_REVIEW": "المراجعة السينمائية القصوى",
    "FINAL_SCRIPT": "النص النهائي",
    "PRONUNCIATION_AND_PERFORMANCE_GATE": "ضبط النطق والأداء",
    "FINAL_TTS": "الصوت النهائي",
    "AUDIO_TIMESTAMPS_AND_BEATS": "التوقيت والإيقاع",
    "AUDIO_BOUND_STORYBOARD": "الستوريبورد المرتبط بالصوت",
    "LUNA_SEMANTIC_PROMPT_DIRECTION": "التوجيه الدلالي للبرومبت",
    "NARRATION_VISUAL_ALIGNMENT_GATE": "بوابة تطابق السرد والصورة",
    "PROMPT_SIMILARITY_AND_DUPLICATE_GATE": "منع التكرار البصري",
    "MEDIA_COST_PREFLIGHT": "فحص خطة الوسائط والكلفة",
    "PROVIDER_EXECUTION": "توليد الوسائط",
    "LOCAL_ASSEMBLY_AND_MONTAGE": "المونتاج المحلي",
    "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA": "الجودة والمراجعة النهائية",
    "READY_FOR_FINAL_HUMAN_REVIEW": "جاهزة للمراجعة البشرية النهائية",
    "COMPLETED_PRIVATE": "مكتملة — خاصة",
    "EVENTS_REVIEW_AND_APPROVAL": "مراجعة أحداث الحلقة",
}

LUNA_STAGES = {
    "TOPIC_SELECTION",
    "SOURCE_RESEARCH_FROM_ZERO",
    "SOURCE_CLAIM_MATRIX",
    "STORY_ARCHITECTURE",
    "ICONIC_CINEMATIC_REVIEW",
    "FINAL_SCRIPT",
    "PRONUNCIATION_AND_PERFORMANCE_GATE",
    "AUDIO_BOUND_STORYBOARD",
    "LUNA_SEMANTIC_PROMPT_DIRECTION",
    "NARRATION_VISUAL_ALIGNMENT_GATE",
    "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _v6_marker(blockers: tuple[str, ...], prefix: str) -> str | None:
    for item in blockers:
        if item.startswith(prefix):
            return item[len(prefix):]
    return None


def install_v6_stage_label_bridge() -> None:
    """Teach the existing EpisodeRecord property to display exact V6 stages."""
    current = EpisodeRecord.stage_label_ar
    if getattr(current.fget, "_siraj_v6_bridge", False):
        return

    original_getter = current.fget

    def getter(self: EpisodeRecord) -> str:
        stage = _v6_marker(self.blockers, "V6_STAGE=")
        if stage:
            return V6_STAGE_AR.get(stage, stage)
        return original_getter(self)

    getter._siraj_v6_bridge = True  # type: ignore[attr-defined]
    EpisodeRecord.stage_label_ar = property(getter)


def _title_from_v6(ep: Path, fallback: str) -> str:
    if ep.name == EP2_ID:
        return "من الوسوسة إلى التوبة"

    candidates = (
        ep / "contracts/episode-definition-v6-3.json",
        ep / "preproduction/topic-selection-v6-3.json",
        ep / "preproduction/luna-final-script-v5-1.json",
        ep / "preproduction/final-script-v6-3.json",
    )
    for path in candidates:
        payload = _read_json(path)
        if not payload:
            continue
        for key in (
            "working_title_ar",
            "topic_title_ar",
            "title_ar",
            "title",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return fallback


def _episode_duration(ep: Path, fallback: int) -> int:
    for path, key in (
        (
            ep / "preproduction/audio-timestamps-and-beats-v6-1.json",
            "total_duration_seconds",
        ),
        (
            ep
            / "deliverables/autopilot-v6-2-1/"
            "episode-master-autopilot-v6-2-1-receipt.json",
            "duration_seconds",
        ),
    ):
        payload = _read_json(path)
        if payload:
            value = payload.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return int(round(float(value)))
    return fallback


def _media_stats(ep: Path) -> tuple[int, int, str, str, str, str]:
    queue = _read_json(
        ep / "orchestration/media-production-queue-v6-2-1.json"
    )
    if queue and isinstance(queue.get("items"), list):
        items = [item for item in queue["items"] if isinstance(item, dict)]
        total = len(items)
        generated = sum(
            1
            for item in items
            if item.get("status") == "COMPLETE"
        )
        pending = next(
            (
                item
                for item in items
                if item.get("status") != "COMPLETE"
            ),
            None,
        )
        if pending:
            shot = str(pending.get("shot_id") or "—")
            beat = str(pending.get("beat_id") or "—")
            model = str(pending.get("selected_model") or "Runware routing")
            provider = str(pending.get("provider") or "RUNWARE")
        else:
            shot = beat = "—"
            model = "Runware routing"
            provider = "RUNWARE"
        return total, generated, provider, model, shot, beat

    prompts = _read_json(
        ep
        / "preproduction/luna-semantic-prompt-direction-v6-2-1.json"
    )
    if prompts and isinstance(prompts.get("items"), list):
        items = [item for item in prompts["items"] if isinstance(item, dict)]
        return len(items), 0, "RUNWARE", "Model Router", "—", "—"

    return 0, 0, "—", "—", "—", "—"


def _provider_model_for_stage(
    repo: Path,
    ep: Path,
    stage: str,
    media_provider: str,
    media_model: str,
) -> tuple[str, str]:
    if stage == "EVENTS_REVIEW_AND_APPROVAL":
        return "HUMAN + LUNA", "Events Review V6.6"
    if stage == "FINAL_TTS":
        return "ELEVENLABS", "eleven_multilingual_v2"
    if stage == "PROVIDER_EXECUTION":
        return media_provider or "RUNWARE", media_model or "Runware routing"
    if stage in {
        "AUDIO_TIMESTAMPS_AND_BEATS",
        "PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
        "MEDIA_COST_PREFLIGHT",
        "LOCAL_ASSEMBLY_AND_MONTAGE",
    }:
        return "LOCAL", "Deterministic V6"
    if stage in LUNA_STAGES:
        try:
            from src.application.siraj_luna_upstream_transport_v6_3 import (
                resolve_luna_model,
            )
            return "OPENAI", resolve_luna_model()
        except Exception:
            return "OPENAI", "Luna"
    if stage == "READY_FOR_FINAL_HUMAN_REVIEW":
        return "HUMAN", "Final Review"
    return "—", "—"


def _next_action_ar(stage: str, paid: bool, authorized: bool, terminal: bool) -> str:
    if terminal:
        return "فتح الفيديو للمراجعة النهائية"
    if stage == "EVENTS_REVIEW_AND_APPROVAL":
        return "مراجعة الأحداث مع Luna"
    label = V6_STAGE_AR.get(stage, stage)
    if paid and not authorized:
        return "تفويض " + label
    return "متابعة Autopilot"


def _v6_final_video(ep: Path, fallback: Path | None) -> Path | None:
    candidate = (
        ep
        / "deliverables/autopilot-v6-2-1/"
        "episode-master-autopilot-v6-2-1.mp4"
    )
    if candidate.is_file():
        return candidate
    return fallback


def _v6_manifest(ep: Path, fallback: Path | None) -> Path | None:
    candidates = (
        ep / "orchestration/media-production-queue-v6-2-1.json",
        ep / "preproduction/luna-semantic-prompt-direction-v6-2-1.json",
        ep / "preproduction/audio-bound-storyboard-v6-1.json",
        ep / "orchestration/final-tts-queue-v5-4-3.json",
        ep / "orchestration/final-tts-queue-v6-3-2.json",
    )
    for path in candidates:
        if path.is_file():
            return path
    return fallback


def _augment_outputs(
    snapshot: DashboardSnapshot,
    active_path: Path,
) -> tuple[Path, ...]:
    found = set(snapshot.output_files)
    patterns = (
        "research/**/*.json",
        "preproduction/**/*.json",
        "orchestration/**/*.json",
        "deliverables/**/*",
    )
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(
            path
            for path in active_path.glob(pattern)
            if path.is_file()
        )
    candidates.sort(
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    for path in candidates[:16]:
        found.add(path)
    return tuple(
        sorted(
            found,
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
        )[-18:]
    )


def build_v6_dashboard_snapshot(repo_root: Path) -> DashboardSnapshot:
    """Return the original dashboard snapshot with V6 runtime truth overlaid."""
    from .repository import build_dashboard_snapshot as legacy_snapshot
    from src.application.siraj_autopilot_v6_6 import inspect_autopilot

    install_v6_stage_label_bridge()
    snapshot = legacy_snapshot(repo_root)

    try:
        inspection = inspect_autopilot(repo_root)
    except Exception:
        return snapshot

    if inspection.episode_id == "NEXT_NEW_EPISODE":
        activities = (
            ActivityRecord(
                time_label="الآن",
                message_ar=(
                    "Autopilot V6: لا توجد حلقة غير مكتملة — "
                    "الحلقة الجديدة ستبدأ من اختيار الموضوع."
                ),
                status="PASS",
            ),
            *snapshot.activities,
        )
        return replace(
            snapshot,
            activities=activities[:8],
            warnings=tuple(
                warning
                for warning in snapshot.warnings
                if warning != "NO_EPISODE_READY_FOR_VIDEO_CONVERSION"
            ),
        )

    episode_id = inspection.episode_id
    updated: list[EpisodeRecord] = []
    active_record: EpisodeRecord | None = None

    for record in snapshot.episodes:
        if record.episode_id != episode_id:
            if record.episode_id == "episode-001-adam":
                completed = replace(
                    record,
                    title_ar=(
                        "آدم عليه السلام — بداية حكاية الإنسان وعداوة إبليس"
                    ),
                    stage=EpisodeStage.PUBLISH_READY,
                    next_action_ar="فتح الحلقة المكتملة",
                    blockers=tuple(
                        dict.fromkeys(
                            (
                                "V6_STAGE=COMPLETED_PRIVATE",
                                "V6_COMPLETED_EPISODE",
                                *record.blockers,
                            )
                        )
                    ),
                )
                updated.append(completed)
            else:
                updated.append(record)
            continue

        ep = record.project_path
        total, generated, media_provider, media_model, shot, beat = (
            _media_stats(ep)
        )
        provider, model = _provider_model_for_stage(
            repo_root,
            ep,
            inspection.stage,
            media_provider,
            media_model,
        )
        blockers = tuple(
            dict.fromkeys(
                (
                    f"V6_STAGE={inspection.stage}",
                    f"V6_ACTION={inspection.action}",
                    f"V6_COMPLETED={len(inspection.completed_stages)}",
                    "V6_AUTOPILOT_ACTIVE",
                    *record.blockers,
                )
            )
        )
        stage = (
            EpisodeStage.VIDEO_REVIEW
            if inspection.terminal
            else EpisodeStage.IN_PRODUCTION
        )
        active_record = replace(
            record,
            title_ar=_title_from_v6(ep, record.title_ar),
            stage=stage,
            duration_seconds=_episode_duration(
                ep,
                record.duration_seconds,
            ),
            shot_count=total,
            approved_shot_count=(
                total
                if (
                    ep
                    / "orchestration/prompt-duplicate-gate-v6-4.json"
                ).is_file()
                else 0
            ),
            generated_shot_count=generated,
            provider=provider,
            model=model,
            current_shot_id=shot,
            current_beat_id=beat,
            next_action_ar=_next_action_ar(
                inspection.stage,
                inspection.paid_stage,
                inspection.authorized,
                inspection.terminal,
            ),
            final_video_path=_v6_final_video(
                ep,
                record.final_video_path,
            ),
            manifest_path=_v6_manifest(
                ep,
                record.manifest_path,
            ),
            blockers=blockers,
        )
        updated.append(active_record)

    if active_record is None:
        return snapshot

    activities = (
        ActivityRecord(
            time_label="الآن",
            message_ar=(
                "Autopilot V6 — "
                + active_record.title_ar
                + ": "
                + V6_STAGE_AR.get(inspection.stage, inspection.stage)
                + " — "
                + (
                    "بانتظار تفويض مدفوع صريح"
                    if inspection.paid_stage and not inspection.authorized
                    else "جاهز للمتابعة"
                )
            ),
            status=(
                "INFO"
                if inspection.paid_stage and not inspection.authorized
                else "PASS"
            ),
        ),
        *snapshot.activities,
    )

    warnings = [
        warning
        for warning in snapshot.warnings
        if warning != "NO_EPISODE_READY_FOR_VIDEO_CONVERSION"
    ]
    if inspection.paid_stage and not inspection.authorized:
        warnings.insert(
            0,
            "V6_EXPLICIT_PAID_AUTHORIZATION_REQUIRED_"
            + inspection.stage,
        )

    from src.application.siraj_series_autopilot_v6_0_1 import STAGES

    readiness = round(
        100 * len(inspection.completed_stages) / max(1, len(STAGES))
    )
    ordered = [
        active_record,
        *[
            item
            for item in updated
            if item.episode_id != active_record.episode_id
        ],
    ]

    return replace(
        snapshot,
        episodes=tuple(ordered),
        activities=activities[:8],
        output_files=_augment_outputs(
            snapshot,
            active_record.project_path,
        ),
        generated_clip_count=active_record.generated_shot_count,
        approved_shot_count=active_record.approved_shot_count,
        total_shot_count=active_record.shot_count,
        readiness_percent=readiness,
        active_episode_id=episode_id,
        warnings=tuple(warnings),
    )
