from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

POLICY_REL = Path(
    "projects/episode-001-adam/contracts/episode-production-policy-v1.json"
)
PLAN_REL = Path(
    "projects/episode-001-adam/cinematic/episode-production-plan-v1.json"
)
PROJECT_REL = Path("projects/episode-001-adam")
AUTOMATIC_STATE_REL = Path(
    "projects/episode-001-adam/cinematic/shot-packages/"
    "adam-dc2-s02-sh03/outputs/automatic-video-generation-state-v1.json"
)

HARD_CAP_USD = 40.0
VIDEO_TARGET_MIN_SECONDS = 120
VIDEO_TARGET_MAX_SECONDS = 180
VIDEO_PLANNED_SECONDS = 160
VIDEO_SHOT_COUNT = 20
ANIMATED_STILL_SHOT_COUNT = 44
GRAPHICS_SHOT_COUNT = 6
EDITORIAL_SHOT_COUNT = 70
PASS_THRESHOLD = 80


class EpisodeProductionPolicyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    hard_cap_usd: float
    actual_spent_usd: float
    remaining_usd: float
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


def load_episode_policy(repo_root: Path) -> dict[str, Any]:
    repo = repo_root.resolve()
    policy = _read_json(repo / POLICY_REL)
    if policy.get("status") != "HUMAN_DIRECTIVES_ACTIVE":
        raise EpisodeProductionPolicyError("PRODUCTION_POLICY_NOT_ACTIVE")

    budget = policy.get("budget")
    media = policy.get("media_mix")
    audio = policy.get("audio")
    review = policy.get("review")
    execution = policy.get("execution")
    for label, value in (
        ("budget", budget),
        ("media_mix", media),
        ("audio", audio),
        ("review", review),
        ("execution", execution),
    ):
        if not isinstance(value, Mapping):
            raise EpisodeProductionPolicyError(
                f"PRODUCTION_POLICY_SECTION_MISSING:{label}"
            )

    if float(budget.get("episode_hard_cap_usd", -1)) != HARD_CAP_USD:
        raise EpisodeProductionPolicyError("EPISODE_HARD_CAP_MUST_BE_40")
    if float(budget.get("headroom_usd", -1)) != 0.0:
        raise EpisodeProductionPolicyError("BUDGET_HEADROOM_FORBIDDEN")
    if budget.get("cap_override") != "FORBIDDEN":
        raise EpisodeProductionPolicyError("BUDGET_CAP_OVERRIDE_FORBIDDEN")
    if budget.get("hidden_paid_retry") != "FORBIDDEN":
        raise EpisodeProductionPolicyError("HIDDEN_PAID_RETRY_FORBIDDEN")

    if media.get("production_mode") != (
        "HYBRID_GENERATED_VIDEO_AND_ANIMATED_STILLS"
    ):
        raise EpisodeProductionPolicyError("HYBRID_MEDIA_MODE_REQUIRED")
    if int(media.get("generated_video_target_min_seconds", -1)) != (
        VIDEO_TARGET_MIN_SECONDS
    ):
        raise EpisodeProductionPolicyError("VIDEO_MINIMUM_CHANGED")
    if int(media.get("generated_video_target_max_seconds", -1)) != (
        VIDEO_TARGET_MAX_SECONDS
    ):
        raise EpisodeProductionPolicyError("VIDEO_MAXIMUM_CHANGED")
    if int(media.get("generated_video_default_plan_seconds", -1)) != (
        VIDEO_PLANNED_SECONDS
    ):
        raise EpisodeProductionPolicyError("VIDEO_PLAN_CHANGED")
    if media.get("flat_slideshow") != "FORBIDDEN":
        raise EpisodeProductionPolicyError("FLAT_SLIDESHOW_MUST_BE_FORBIDDEN")

    if audio.get("music") != "FORBIDDEN":
        raise EpisodeProductionPolicyError("MUSIC_MUST_BE_FORBIDDEN")
    if audio.get("musical_score") != "FORBIDDEN":
        raise EpisodeProductionPolicyError("MUSICAL_SCORE_MUST_BE_FORBIDDEN")
    if audio.get("songs") != "FORBIDDEN":
        raise EpisodeProductionPolicyError("SONGS_MUST_BE_FORBIDDEN")
    if audio.get("sound_effects") != "ALLOWED":
        raise EpisodeProductionPolicyError("SOUND_EFFECTS_MUST_BE_ALLOWED")
    if audio.get("sound_effect_type_restriction") != (
        "NONE_WHEN_SCENE_APPROPRIATE"
    ):
        raise EpisodeProductionPolicyError(
            "SCENE_APPROPRIATE_SFX_MUST_REMAIN_UNRESTRICTED"
        )

    if review.get("required_human_input") != (
        "ONE_INTEGER_ONLY_0_TO_100"
    ):
        raise EpisodeProductionPolicyError("SCORE_ONLY_REVIEW_REQUIRED")
    if int(review.get("pass_threshold", -1)) != PASS_THRESHOLD:
        raise EpisodeProductionPolicyError("PASS_THRESHOLD_CHANGED")
    if execution.get("surface") != "SIRAJ_DESKTOP_UI_ONLY":
        raise EpisodeProductionPolicyError("DESKTOP_UI_EXECUTION_REQUIRED")
    return policy


def load_episode_plan(repo_root: Path) -> dict[str, Any]:
    repo = repo_root.resolve()
    load_episode_policy(repo)
    plan = _read_json(repo / PLAN_REL)
    if plan.get("status") != "HUMAN_POLICY_BOUND_QUEUE_READY":
        raise EpisodeProductionPolicyError("EPISODE_QUEUE_NOT_READY")
    if float(plan.get("hard_cap_usd", -1)) != HARD_CAP_USD:
        raise EpisodeProductionPolicyError("PLAN_HARD_CAP_CHANGED")
    if plan.get("music") != "FORBIDDEN":
        raise EpisodeProductionPolicyError("PLAN_MUSIC_MUST_BE_FORBIDDEN")
    if plan.get("sound_effects") != (
        "ALLOWED_ANY_SCENE_APPROPRIATE_TYPE"
    ):
        raise EpisodeProductionPolicyError("PLAN_SFX_POLICY_CHANGED")

    shots = plan.get("shots")
    if not isinstance(shots, list) or len(shots) != EDITORIAL_SHOT_COUNT:
        raise EpisodeProductionPolicyError("PLAN_MUST_CONTAIN_70_SHOTS")
    ids = [item.get("shot_id") for item in shots if isinstance(item, Mapping)]
    if len(ids) != len(set(ids)):
        raise EpisodeProductionPolicyError("DUPLICATE_SHOT_ID_IN_PLAN")

    counts = {
        "GENERATED_VIDEO": 0,
        "ANIMATED_STILL_COMPOSITING": 0,
        "GRAPHICS": 0,
    }
    seconds = 0
    for item in shots:
        if not isinstance(item, Mapping):
            raise EpisodeProductionPolicyError("INVALID_PLAN_SHOT")
        treatment = str(item.get("final_budget_treatment", ""))
        if treatment not in counts:
            raise EpisodeProductionPolicyError(
                f"INVALID_TREATMENT:{treatment}"
            )
        counts[treatment] += 1
        seconds += int(item.get("planned_generated_video_seconds", 0))
        if item.get("sound_policy") != "SFX_ONLY_NO_MUSIC":
            raise EpisodeProductionPolicyError(
                f"SHOT_SOUND_POLICY_CHANGED:{item.get('shot_id')}"
            )

    expected = {
        "GENERATED_VIDEO": VIDEO_SHOT_COUNT,
        "ANIMATED_STILL_COMPOSITING": ANIMATED_STILL_SHOT_COUNT,
        "GRAPHICS": GRAPHICS_SHOT_COUNT,
    }
    if counts != expected:
        raise EpisodeProductionPolicyError(
            f"PLAN_TREATMENT_COUNTS_CHANGED:{counts}"
        )
    if seconds != VIDEO_PLANNED_SECONDS:
        raise EpisodeProductionPolicyError(
            f"PLAN_VIDEO_SECONDS_CHANGED:{seconds}"
        )
    return plan


def scan_actual_paid_spend(repo_root: Path) -> BudgetSnapshot:
    repo = repo_root.resolve()
    project = repo / PROJECT_REL
    seen_tasks: set[str] = set()
    receipt_paths: list[Path] = []
    spent = 0.0

    if project.is_dir():
        candidates = sorted(
            path
            for path in project.rglob("*.json")
            if "receipt" in path.name.lower()
        )
    else:
        candidates = []

    for path in candidates:
        try:
            record = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        cost = record.get("actual_cost_usd")
        task_uuid = str(record.get("task_uuid", "")).strip()
        if not isinstance(cost, (int, float)) or float(cost) < 0:
            continue
        identity = task_uuid or f"path:{path.relative_to(repo)}"
        if identity in seen_tasks:
            continue
        seen_tasks.add(identity)
        spent += float(cost)
        receipt_paths.append(path)

    spent = round(spent, 8)
    remaining = round(max(0.0, HARD_CAP_USD - spent), 8)
    return BudgetSnapshot(
        hard_cap_usd=HARD_CAP_USD,
        actual_spent_usd=spent,
        remaining_usd=remaining,
        unique_paid_tasks=len(seen_tasks),
        receipt_paths=tuple(receipt_paths),
    )


def assert_budget_allows_new_paid_request(
    repo_root: Path,
    estimated_max_cost_usd: float,
) -> BudgetSnapshot:
    estimate = float(estimated_max_cost_usd)
    if estimate <= 0:
        raise EpisodeProductionPolicyError(
            "POSITIVE_ESTIMATED_COST_REQUIRED"
        )
    policy = load_episode_policy(repo_root)
    budget = policy["budget"]
    if budget.get("preflight_required_before_each_paid_request") is not True:
        raise EpisodeProductionPolicyError("BUDGET_PREFLIGHT_REQUIRED")
    snapshot = scan_actual_paid_spend(repo_root)
    projected = snapshot.actual_spent_usd + estimate
    if projected > HARD_CAP_USD + 1e-9:
        raise EpisodeProductionPolicyError(
            "EPISODE_BUDGET_HARD_CAP_BLOCKED:"
            f"spent={snapshot.actual_spent_usd:.4f}:"
            f"estimate={estimate:.4f}:cap={HARD_CAP_USD:.2f}"
        )
    return snapshot


def episode_progress(repo_root: Path) -> EpisodeProgress:
    repo = repo_root.resolve()
    plan = load_episode_plan(repo)
    shots = plan["shots"]

    state_status = "NOT_STARTED"
    accepted_video_shots = 0
    accepted_video_seconds = 0
    state_path = repo / AUTOMATIC_STATE_REL
    if state_path.is_file():
        try:
            state = _read_json(state_path)
            state_status = str(state.get("status", "UNKNOWN"))
            if state_status == "ACCEPTED":
                accepted_video_shots = 1
                accepted_video_seconds = 8
        except EpisodeProductionPolicyError:
            state_status = "STATE_UNREADABLE"

    next_id = None
    next_label = None
    accepted_reference = str(plan.get("accepted_reference_shot_id", ""))
    for shot in shots:
        if shot.get("final_budget_treatment") != "GENERATED_VIDEO":
            continue
        if shot.get("shot_id") == accepted_reference and accepted_video_shots:
            continue
        next_id = str(shot.get("shot_id"))
        next_label = str(shot.get("label_ar"))
        break

    counts = plan["treatment_counts"]
    return EpisodeProgress(
        total_shots=len(shots),
        generated_video_planned_shots=int(counts["GENERATED_VIDEO"]),
        animated_still_shots=int(
            counts["ANIMATED_STILL_COMPOSITING"]
        ),
        graphics_shots=int(counts["GRAPHICS"]),
        planned_video_seconds=int(
            plan["generated_video_target_seconds"]["planned"]
        ),
        accepted_video_shots=accepted_video_shots,
        accepted_video_seconds=accepted_video_seconds,
        current_video_state=state_status,
        next_video_shot_id=next_id,
        next_video_label_ar=next_label,
    )


def queue_rows(repo_root: Path) -> list[dict[str, Any]]:
    plan = load_episode_plan(repo_root)
    progress = episode_progress(repo_root)
    accepted_reference = str(plan.get("accepted_reference_shot_id", ""))
    rows: list[dict[str, Any]] = []
    for shot in plan["shots"]:
        row = dict(shot)
        if (
            row.get("shot_id") == accepted_reference
            and progress.accepted_video_shots
        ):
            row["production_status"] = "ACCEPTED"
        rows.append(row)
    return rows
