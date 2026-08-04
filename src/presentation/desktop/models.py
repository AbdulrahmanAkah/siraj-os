from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class EpisodeStage(StrEnum):
    DRAFT = "DRAFT"
    IN_PRODUCTION = "IN_PRODUCTION"
    READY_FOR_CONVERSION = "READY_FOR_CONVERSION"
    VIDEO_REVIEW = "VIDEO_REVIEW"
    PUBLISH_READY = "PUBLISH_READY"
    BLOCKED = "BLOCKED"


_STAGE_LABELS = {
    EpisodeStage.DRAFT: "مسودة",
    EpisodeStage.IN_PRODUCTION: "قيد الإعداد",
    EpisodeStage.READY_FOR_CONVERSION: "جاهزة للتحويل",
    EpisodeStage.VIDEO_REVIEW: "قيد مراجعة الفيديو",
    EpisodeStage.PUBLISH_READY: "جاهزة للنشر",
    EpisodeStage.BLOCKED: "معلّقة",
}


@dataclass(frozen=True, slots=True)
class EpisodeRecord:
    episode_id: str
    title_ar: str
    project_path: Path
    stage: EpisodeStage
    duration_seconds: int = 0
    shot_count: int = 0
    approved_shot_count: int = 0
    generated_shot_count: int = 0
    provider: str = "—"
    model: str = "—"
    current_shot_id: str = "—"
    next_action_ar: str = "فتح الحلقة"
    final_video_path: Path | None = None
    manifest_path: Path | None = None
    blockers: tuple[str, ...] = ()

    @property
    def stage_label_ar(self) -> str:
        return _STAGE_LABELS[self.stage]

    @property
    def duration_label(self) -> str:
        return format_duration(self.duration_seconds)

    @property
    def conversion_ready(self) -> bool:
        return self.stage == EpisodeStage.READY_FOR_CONVERSION

    @property
    def publish_ready(self) -> bool:
        return self.stage == EpisodeStage.PUBLISH_READY

    @property
    def progress_fraction(self) -> float:
        if self.shot_count <= 0:
            return 0.0
        completed = max(self.approved_shot_count, self.generated_shot_count)
        return min(1.0, max(0.0, completed / self.shot_count))


@dataclass(frozen=True, slots=True)
class ActivityRecord:
    time_label: str
    message_ar: str
    status: str = "INFO"


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    repo_root: Path
    episodes: tuple[EpisodeRecord, ...]
    activities: tuple[ActivityRecord, ...] = ()
    output_files: tuple[Path, ...] = ()
    generated_clip_count: int = 0
    approved_shot_count: int = 0
    total_shot_count: int = 0
    estimated_cost_usd: float = 0.0
    readiness_percent: int = 0
    active_episode_id: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ready_for_conversion(self) -> tuple[EpisodeRecord, ...]:
        return tuple(
            episode
            for episode in self.episodes
            if episode.conversion_ready
        )

    @property
    def publish_ready(self) -> tuple[EpisodeRecord, ...]:
        return tuple(
            episode
            for episode in self.episodes
            if episode.publish_ready
        )

    @property
    def active_episode(self) -> EpisodeRecord | None:
        if not self.episodes:
            return None
        if self.active_episode_id is not None:
            for episode in self.episodes:
                if episode.episode_id == self.active_episode_id:
                    return episode
        return self.episodes[0]


def format_duration(seconds: int) -> str:
    safe_seconds = max(0, int(seconds))
    hours, remainder = divmod(safe_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
