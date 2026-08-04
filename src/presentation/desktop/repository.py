from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .models import (
    ActivityRecord,
    DashboardSnapshot,
    EpisodeRecord,
    EpisodeStage,
)

_TITLE_OVERRIDES = {
    "episode-001-adam": "آدم",
    "episode-002-noah": "نوح",
    "episode-003-abraham": "إبراهيم",
}

_FINAL_VIDEO_CANDIDATES = (
    "publish/final-video.mp4",
    "outputs/final-video.mp4",
    "cinematic/final-video.mp4",
    "video/final-video.mp4",
)

_FINAL_RECEIPT_CANDIDATES = (
    "publish/final-video-receipt.json",
    "evidence/final-video-human-approval-v1.json",
    "contracts/youtube-publish-readiness-v1.json",
)


def find_repo_root(start: Path | None = None) -> Path:
    candidate = (start or Path.cwd()).resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for current in (candidate, *candidate.parents):
        if (
            (current / "pyproject.toml").is_file()
            and (current / "projects").is_dir()
        ):
            return current
    raise FileNotFoundError("SIRAJ_REPOSITORY_ROOT_NOT_FOUND")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _manifest_path(project_path: Path) -> Path | None:
    candidates = sorted(
        (project_path / "cinematic").glob("*production-manifest*.json")
    )
    if not candidates:
        return None
    preferred = [
        item
        for item in candidates
        if "veo-production-manifest-v1" in item.name
    ]
    return (preferred or candidates)[-1]


def _title_for(project_path: Path) -> str:
    if project_path.name in _TITLE_OVERRIDES:
        return _TITLE_OVERRIDES[project_path.name]
    slug = project_path.name.split("-", 2)[-1]
    return slug.replace("-", " ").strip().title() or project_path.name


def _find_final_video(project_path: Path) -> Path | None:
    for relative in _FINAL_VIDEO_CANDIDATES:
        candidate = project_path / relative
        if candidate.is_file():
            return candidate
    return None


def _receipt_is_approved(project_path: Path) -> bool:
    for relative in _FINAL_RECEIPT_CANDIDATES:
        payload = _read_json(project_path / relative)
        if payload is None:
            continue
        approval_values = {
            payload.get("approved"),
            payload.get("human_approval"),
            payload.get("publish_ready"),
            payload.get("final_video_approval"),
        }
        status = str(payload.get("status", "")).upper()
        if True in approval_values or status in {
            "APPROVED",
            "PASS",
            "PUBLISH_READY",
            "READY_FOR_YOUTUBE",
        }:
            return True
    return False


def _current_shot(project_path: Path) -> str:
    package_root = project_path / "cinematic" / "shot-packages"
    packages = sorted(package_root.glob("**/*.json")) if package_root.is_dir() else []
    for package in reversed(packages):
        payload = _read_json(package)
        if payload and isinstance(payload.get("shot_id"), str):
            return payload["shot_id"]
    return "—"


def _count_shots(shots: Iterable[Any]) -> tuple[int, int, int]:
    total = approved = generated = 0
    for item in shots:
        if not isinstance(item, dict):
            continue
        total += 1
        status = str(item.get("status", "")).upper()
        if "APPROVED" in status or status in {"PASS", "ACCEPTED"}:
            approved += 1
        if "GENERATED" in status or "RENDERED" in status:
            generated += 1
    return total, approved, generated


def _derive_stage(
    *,
    manifest: dict[str, Any] | None,
    final_video: Path | None,
    receipt_approved: bool,
) -> tuple[EpisodeStage, tuple[str, ...], str]:
    if final_video is not None and receipt_approved:
        return EpisodeStage.PUBLISH_READY, (), "فتح ملف النشر"
    if final_video is not None:
        return (
            EpisodeStage.VIDEO_REVIEW,
            ("FINAL_VIDEO_HUMAN_APPROVAL_REQUIRED",),
            "مراجعة الفيديو",
        )
    if manifest is None:
        return (
            EpisodeStage.DRAFT,
            ("PRODUCTION_MANIFEST_MISSING",),
            "فتح الحلقة",
        )

    master_approval = bool(manifest.get("master_visual_approval"))
    final_master_approval = bool(manifest.get("final_master_visual_approval"))
    bulk_policy = str(
        (manifest.get("execution_policy") or {}).get(
            "full_episode_bulk_generation",
            "",
        )
    ).upper()

    blockers: list[str] = []
    if not master_approval:
        blockers.append("MASTER_VISUAL_APPROVAL_REQUIRED")
    if not final_master_approval:
        blockers.append("FINAL_MASTER_VISUAL_APPROVAL_REQUIRED")
    if "BLOCKED" in bulk_policy:
        blockers.append("FULL_EPISODE_BULK_GENERATION_BLOCKED")

    if not blockers:
        return EpisodeStage.READY_FOR_CONVERSION, (), "بدء التحويل"
    return EpisodeStage.IN_PRODUCTION, tuple(blockers), "استكمال"


def load_episode_record(project_path: Path) -> EpisodeRecord:
    manifest_path = _manifest_path(project_path)
    manifest = _read_json(manifest_path) if manifest_path else None
    final_video = _find_final_video(project_path)
    receipt_approved = _receipt_is_approved(project_path)
    stage, blockers, next_action = _derive_stage(
        manifest=manifest,
        final_video=final_video,
        receipt_approved=receipt_approved,
    )

    shots = manifest.get("shots", []) if manifest else []
    total, approved, generated = _count_shots(shots)
    declared_count = int(manifest.get("shot_count", total) or total) if manifest else 0
    shot_count = max(total, declared_count)
    duration = int(manifest.get("editorial_duration_seconds", 0) or 0) if manifest else 0
    model_payload = manifest.get("primary_video_model", {}) if manifest else {}
    if not isinstance(model_payload, dict):
        model_payload = {}

    return EpisodeRecord(
        episode_id=project_path.name,
        title_ar=_title_for(project_path),
        project_path=project_path,
        stage=stage,
        duration_seconds=duration,
        shot_count=shot_count,
        approved_shot_count=approved,
        generated_shot_count=generated,
        provider=str(model_payload.get("provider", "—")),
        model=str(model_payload.get("model", "—")),
        current_shot_id=_current_shot(project_path),
        next_action_ar=next_action,
        final_video_path=final_video,
        manifest_path=manifest_path,
        blockers=blockers,
    )


def discover_episode_records(repo_root: Path) -> tuple[EpisodeRecord, ...]:
    projects_root = repo_root / "projects"
    if not projects_root.is_dir():
        return ()
    project_paths = sorted(
        path
        for path in projects_root.glob("episode-*")
        if path.is_dir()
    )
    return tuple(load_episode_record(path) for path in project_paths)


def _collect_outputs(repo_root: Path) -> tuple[Path, ...]:
    candidates: list[Path] = []
    for episode in sorted((repo_root / "projects").glob("episode-*")):
        for pattern in (
            "cinematic/*.json",
            "contracts/*.json",
            "evidence/*.json",
            "publish/*.mp4",
            "outputs/*.mp4",
        ):
            candidates.extend(sorted(episode.glob(pattern)))
    return tuple(candidates[-8:])


def build_dashboard_snapshot(repo_root: Path) -> DashboardSnapshot:
    episodes = discover_episode_records(repo_root)
    total_shots = sum(item.shot_count for item in episodes)
    approved_shots = sum(item.approved_shot_count for item in episodes)
    generated_shots = sum(item.generated_shot_count for item in episodes)
    publish_ready_count = sum(item.publish_ready for item in episodes)
    readiness = (
        round(100 * publish_ready_count / len(episodes))
        if episodes
        else 0
    )

    activities: list[ActivityRecord] = []
    for episode in episodes[:5]:
        activities.append(
            ActivityRecord(
                time_label="الآن",
                message_ar=(
                    f"{episode.title_ar}: {episode.stage_label_ar} — "
                    f"{episode.current_shot_id}"
                ),
                status="PASS" if episode.publish_ready else "INFO",
            )
        )

    warnings: list[str] = []
    if not episodes:
        warnings.append("NO_EPISODES_DISCOVERED")
    if not any(item.conversion_ready for item in episodes):
        warnings.append("NO_EPISODE_READY_FOR_VIDEO_CONVERSION")

    return DashboardSnapshot(
        repo_root=repo_root,
        episodes=episodes,
        activities=tuple(activities),
        output_files=_collect_outputs(repo_root),
        generated_clip_count=generated_shots,
        approved_shot_count=approved_shots,
        total_shot_count=total_shots,
        estimated_cost_usd=0.0,
        readiness_percent=readiness,
        active_episode_id=episodes[0].episode_id if episodes else None,
        warnings=tuple(warnings),
    )
