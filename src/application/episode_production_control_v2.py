"""Generic V2 paid-video budget control for all Siraj episodes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.application.series_production_quality_v2 import (
    HARD_GENERATED_VIDEO_SPEND_USD,
    TARGET_GENERATED_VIDEO_SPEND_USD,
    SeriesProductionPolicyV2,
    load_policy,
)

SERIES_POLICY_REL = Path(
    "projects/_series/siraj-series-production-policy-v2.json"
)
ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
HARD_CAP_USD = HARD_GENERATED_VIDEO_SPEND_USD
TARGET_SPEND_USD = TARGET_GENERATED_VIDEO_SPEND_USD
VIDEO_TARGET_MIN_SECONDS = 0
VIDEO_TARGET_MAX_SECONDS = 25 * 60
VIDEO_PLANNED_SECONDS = 0
VIDEO_SHOT_COUNT = 0
ANIMATED_STILL_SHOT_COUNT = 0
GRAPHICS_SHOT_COUNT = 0
EDITORIAL_SHOT_COUNT = 0
PASS_THRESHOLD = 80


class EpisodeProductionPolicyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    hard_cap_usd: float
    target_spend_usd: float
    actual_spent_usd: float
    remaining_usd: float
    target_remaining_usd: float
    unique_paid_tasks: int
    receipt_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class EpisodeProgress:
    total_shots: int
    generated_video_planned_shots: int
    animated_still_shots: int
    graphics_shots: int
    planned_video_seconds: int
    accepted_video_shots: int
    accepted_video_seconds: int
    current_video_state: str
    next_video_shot_id: str | None
    next_video_label_ar: str | None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EpisodeProductionPolicyError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise EpisodeProductionPolicyError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _active_episode_id(repo_root: Path) -> str:
    state_path = repo_root.resolve() / ORCHESTRATOR_STATE_REL
    if state_path.is_file():
        state = _read_json(state_path)
        value = str(state.get("current_episode_id") or "").strip()
        if value:
            return value
    legacy = repo_root.resolve() / "projects" / "episode-001-adam"
    if legacy.is_dir():
        return "episode-001-adam"
    raise EpisodeProductionPolicyError("ACTIVE_EPISODE_NOT_FOUND")


def _episode_root(repo_root: Path, episode_id: str | None = None) -> Path:
    value = episode_id or _active_episode_id(repo_root)
    return repo_root.resolve() / "projects" / value


def load_series_policy(repo_root: Path) -> SeriesProductionPolicyV2:
    path = repo_root.resolve() / SERIES_POLICY_REL
    if not path.is_file():
        raise EpisodeProductionPolicyError(
            f"SERIES_PRODUCTION_POLICY_V2_NOT_FOUND:{path}"
        )
    try:
        return load_policy(path)
    except Exception as exc:
        raise EpisodeProductionPolicyError(
            f"SERIES_PRODUCTION_POLICY_V2_INVALID:{exc}"
        ) from exc


def load_episode_policy(
    repo_root: Path,
    episode_id: str | None = None,
) -> dict[str, Any]:
    series = load_series_policy(repo_root)
    root = _episode_root(repo_root, episode_id)
    path = root / "contracts" / "episode-production-policy-v2.json"
    if path.is_file():
        payload = _read_json(path)
    else:
        payload = {
            "schema_version": "siraj-episode-production-policy-v2",
            "status": "SERIES_POLICY_INHERITED",
            "episode_id": root.name,
            "budget": {
                "generated_video_target_usd": (
                    series.budget.target_generated_video_spend_usd
                ),
                "generated_video_hard_cap_usd": (
                    series.budget.hard_generated_video_spend_usd
                ),
                "preflight_required_before_each_paid_request": True,
                "hidden_paid_retry": "FORBIDDEN",
            },
            "media_mix": {
                "production_mode": "BUDGET_DRIVEN_VIDEO_FIRST",
                "generated_video_seconds_target": (
                    "NONE_COST_AND_QUALITY_DRIVEN"
                ),
                "flat_slideshow": "FORBIDDEN",
            },
        }
    budget = payload.get("budget")
    if not isinstance(budget, Mapping):
        raise EpisodeProductionPolicyError("EPISODE_BUDGET_SECTION_REQUIRED")
    if float(budget.get("generated_video_target_usd", -1)) != (
        TARGET_SPEND_USD
    ):
        raise EpisodeProductionPolicyError("VIDEO_TARGET_SPEND_MUST_BE_30")
    if float(budget.get("generated_video_hard_cap_usd", -1)) != HARD_CAP_USD:
        raise EpisodeProductionPolicyError("VIDEO_HARD_CAP_MUST_BE_35")
    if budget.get("preflight_required_before_each_paid_request") is not True:
        raise EpisodeProductionPolicyError("BUDGET_PREFLIGHT_REQUIRED")
    if budget.get("hidden_paid_retry") != "FORBIDDEN":
        raise EpisodeProductionPolicyError("HIDDEN_PAID_RETRY_FORBIDDEN")
    return payload


def load_episode_plan(
    repo_root: Path,
    episode_id: str | None = None,
) -> dict[str, Any]:
    root = _episode_root(repo_root, episode_id)
    candidates = (
        root / "cinematic" / "episode-production-plan-v2.json",
        root / "cinematic" / "episode-production-plan-v1.json",
    )
    path = next((item for item in candidates if item.is_file()), None)
    if path is None:
        raise EpisodeProductionPolicyError("EPISODE_PRODUCTION_PLAN_NOT_FOUND")
    plan = _read_json(path)
    shots = plan.get("shots")
    if not isinstance(shots, list) or not shots:
        raise EpisodeProductionPolicyError("EPISODE_PLAN_SHOTS_REQUIRED")
    ids = [
        str(item.get("shot_id") or "")
        for item in shots
        if isinstance(item, Mapping)
    ]
    if len(ids) != len(shots) or any(not value for value in ids):
        raise EpisodeProductionPolicyError("VALID_SHOT_IDS_REQUIRED")
    if len(set(ids)) != len(ids):
        raise EpisodeProductionPolicyError("DUPLICATE_SHOT_ID_IN_PLAN")
    return plan


def _is_video_receipt(record: Mapping[str, Any], path: Path) -> bool:
    fields = " ".join(
        str(record.get(key) or "")
        for key in (
            "category",
            "media_type",
            "treatment",
            "model_type",
            "output_path_relative",
            "output_filename",
        )
    ).lower()
    return (
        "video" in fields
        or ".mp4" in fields
        or "runware-video" in path.name.lower()
    )


def scan_actual_paid_spend(
    repo_root: Path,
    episode_id: str | None = None,
) -> BudgetSnapshot:
    project = _episode_root(repo_root, episode_id)
    seen_tasks: set[str] = set()
    receipt_paths: list[Path] = []
    spent = 0.0
    candidates = (
        sorted(
            path
            for path in project.rglob("*.json")
            if "receipt" in path.name.lower()
        )
        if project.is_dir()
        else []
    )
    for path in candidates:
        try:
            record = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, Mapping) or not _is_video_receipt(record, path):
            continue
        cost = record.get("actual_cost_usd")
        if not isinstance(cost, (int, float)) or float(cost) < 0:
            continue
        task_uuid = str(record.get("task_uuid") or "").strip()
        identity = task_uuid or f"path:{path.relative_to(repo_root.resolve())}"
        if identity in seen_tasks:
            continue
        seen_tasks.add(identity)
        spent += float(cost)
        receipt_paths.append(path)
    spent = round(spent, 8)
    return BudgetSnapshot(
        hard_cap_usd=HARD_CAP_USD,
        target_spend_usd=TARGET_SPEND_USD,
        actual_spent_usd=spent,
        remaining_usd=round(max(0.0, HARD_CAP_USD - spent), 8),
        target_remaining_usd=round(TARGET_SPEND_USD - spent, 8),
        unique_paid_tasks=len(seen_tasks),
        receipt_paths=tuple(receipt_paths),
    )


def assert_budget_allows_new_paid_request(
    repo_root: Path,
    estimated_max_cost_usd: float,
) -> BudgetSnapshot:
    estimate = float(estimated_max_cost_usd)
    if estimate <= 0:
        raise EpisodeProductionPolicyError("POSITIVE_ESTIMATED_COST_REQUIRED")
    load_episode_policy(repo_root)
    snapshot = scan_actual_paid_spend(repo_root)
    projected = snapshot.actual_spent_usd + estimate
    if projected > HARD_CAP_USD + 1e-9:
        raise EpisodeProductionPolicyError(
            "EPISODE_GENERATED_VIDEO_HARD_CAP_BLOCKED:"
            f"spent={snapshot.actual_spent_usd:.4f}:"
            f"estimate={estimate:.4f}:cap={HARD_CAP_USD:.2f}"
        )
    return snapshot


def episode_progress(repo_root: Path) -> EpisodeProgress:
    plan = load_episode_plan(repo_root)
    shots = plan["shots"]
    counts = {
        "GENERATED_VIDEO": 0,
        "ANIMATED_STILL_COMPOSITING": 0,
        "DYNAMIC_STILL": 0,
        "GRAPHICS": 0,
    }
    planned_video_seconds = 0
    next_id = None
    next_label = None
    for shot in shots:
        treatment = str(
            shot.get("final_budget_treatment")
            or shot.get("treatment")
            or ""
        )
        counts[treatment] = counts.get(treatment, 0) + 1
        seconds = int(
            shot.get("planned_generated_video_seconds")
            or (
                shot.get("planned_seconds", 0)
                if treatment == "GENERATED_VIDEO"
                else 0
            )
            or 0
        )
        planned_video_seconds += seconds
        if treatment == "GENERATED_VIDEO" and next_id is None:
            next_id = str(shot.get("shot_id"))
            next_label = str(shot.get("label_ar") or "")
    return EpisodeProgress(
        total_shots=len(shots),
        generated_video_planned_shots=counts.get("GENERATED_VIDEO", 0),
        animated_still_shots=(
            counts.get("ANIMATED_STILL_COMPOSITING", 0)
            + counts.get("DYNAMIC_STILL", 0)
        ),
        graphics_shots=counts.get("GRAPHICS", 0),
        planned_video_seconds=planned_video_seconds,
        accepted_video_shots=0,
        accepted_video_seconds=0,
        current_video_state="BUDGET_DRIVEN_PLAN_READY",
        next_video_shot_id=next_id,
        next_video_label_ar=next_label,
    )


def queue_rows(repo_root: Path) -> list[dict[str, Any]]:
    return [dict(item) for item in load_episode_plan(repo_root)["shots"]]
