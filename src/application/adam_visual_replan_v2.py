"""Budget-driven visual replanning for episode-001-adam under Siraj V2."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Any, Mapping

TARGET_VIDEO_USD = 30.0
HARD_VIDEO_USD = 35.0
OBSERVED_VIDEO_COST_PER_SECOND_USD = 5.3 / 160.0
MAX_STILL_PANEL_SECONDS = 7.0
PROVIDER_CLIP_SECONDS = 8


class AdamVisualReplanError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdamVisualReplanResult:
    storyboard: dict[str, Any]
    production_plan: dict[str, Any]
    summary: dict[str, Any]


def _duration(plan_shot: Mapping[str, Any], story_shot: Mapping[str, Any]) -> int:
    for key, source in (
        ("editorial_duration_seconds", plan_shot),
        ("planned_seconds", plan_shot),
        ("editorial_duration_seconds", story_shot),
        ("planned_seconds", story_shot),
        ("duration_seconds", story_shot),
    ):
        try:
            value = int(round(float(source.get(key, 0))))
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    raise AdamVisualReplanError(
        f"SHOT_DURATION_REQUIRED:{plan_shot.get('shot_id')}"
    )


def _combined_text(plan_shot: Mapping[str, Any], story_shot: Mapping[str, Any]) -> str:
    fields = (
        "label_ar",
        "dramatic_function_ar",
        "visual_brief_ar",
        "action_ar",
        "transformation_ar",
        "positive_prompt",
    )
    return " ".join(
        str(plan_shot.get(key) or story_shot.get(key) or "")
        for key in fields
    ).lower()


def _motion_required(plan_shot: Mapping[str, Any], story_shot: Mapping[str, Any]) -> bool:
    if str(plan_shot.get("motion_necessity") or "").upper() == "REQUIRED":
        return True
    text = _combined_text(plan_shot, story_shot)
    terms = (
        "خلق", "الطين", "يتكوّن", "يتكون", "يتشكل", "يتحوّل", "يتحول",
        "تتجمع", "ينفتح", "يصعد", "يهبط", "formation", "transform",
        "movement", "reveal",
    )
    return any(term in text for term in terms)


def _priority(plan_shot: Mapping[str, Any], story_shot: Mapping[str, Any]) -> int:
    try:
        score = int(plan_shot.get("video_priority_v2", 50))
    except (TypeError, ValueError):
        score = 50
    if _motion_required(plan_shot, story_shot):
        score += 40
    if str(plan_shot.get("scene_domain")) == "HEAVENLY_UNSEEN_SYMBOLIC":
        score += 25
    if str(plan_shot.get("final_budget_treatment")) == "GENERATED_VIDEO":
        score += 15
    text = _combined_text(plan_shot, story_shot)
    if any(term in text for term in ("السجود", "النفخ", "الاختبار", "الذروة")):
        score += 20
    return min(score, 200)


def _is_video_excluded(plan_shot: Mapping[str, Any]) -> bool:
    treatment = str(plan_shot.get("final_budget_treatment") or "")
    domain = str(plan_shot.get("scene_domain") or "")
    return treatment == "GRAPHICS" or domain == "DOCUMENTARY_EVIDENCE"


def _non_video_treatment(plan_shot: Mapping[str, Any]) -> str:
    if str(plan_shot.get("final_budget_treatment") or "") == "GRAPHICS":
        return "AUTHORED_GRAPHICS"
    if str(plan_shot.get("scene_domain") or "") == "DOCUMENTARY_EVIDENCE":
        return "DOCUMENT_OR_MAP"
    return "DYNAMIC_STILL_SEQUENCE"


def build_adam_visual_replan(
    legacy_storyboard: Mapping[str, Any],
    production_plan: Mapping[str, Any],
    *,
    cost_per_second_usd: float = OBSERVED_VIDEO_COST_PER_SECOND_USD,
    target_usd: float = TARGET_VIDEO_USD,
    hard_usd: float = HARD_VIDEO_USD,
) -> AdamVisualReplanResult:
    story_shots = legacy_storyboard.get("shots")
    plan_shots = production_plan.get("shots")
    if not isinstance(story_shots, list) or not story_shots:
        raise AdamVisualReplanError("LEGACY_STORYBOARD_SHOTS_REQUIRED")
    if not isinstance(plan_shots, list) or not plan_shots:
        raise AdamVisualReplanError("V2_PLAN_SHOTS_REQUIRED")
    if len(story_shots) != len(plan_shots):
        raise AdamVisualReplanError(
            f"SHOT_COUNT_MISMATCH:storyboard={len(story_shots)}:plan={len(plan_shots)}"
        )
    if cost_per_second_usd <= 0:
        raise AdamVisualReplanError("POSITIVE_VIDEO_COST_RATE_REQUIRED")
    if not 0 < target_usd <= hard_usd:
        raise AdamVisualReplanError("INVALID_VIDEO_BUDGET")

    rows: list[dict[str, Any]] = []
    for index, (story_raw, plan_raw) in enumerate(
        zip(story_shots, plan_shots, strict=True), start=1
    ):
        if not isinstance(story_raw, Mapping) or not isinstance(plan_raw, Mapping):
            raise AdamVisualReplanError(f"SHOT_OBJECT_REQUIRED:{index}")
        story = dict(story_raw)
        plan = dict(plan_raw)
        duration = _duration(plan, story)
        excluded = _is_video_excluded(plan)
        required = _motion_required(plan, story) and not excluded
        priority = _priority(plan, story)
        rows.append(
            {
                "index": index,
                "story": story,
                "plan": plan,
                "duration": duration,
                "excluded": excluded,
                "required": required,
                "priority": priority,
                "cost": round(duration * cost_per_second_usd, 6),
            }
        )

    selected = {row["index"] for row in rows if row["required"]}
    spent = round(sum(row["cost"] for row in rows if row["required"]), 6)
    if spent > hard_usd + 1e-9:
        raise AdamVisualReplanError(
            f"REQUIRED_VIDEO_EXCEEDS_HARD_CAP:spent={spent:.4f}:cap={hard_usd:.2f}"
        )

    optional = [
        row for row in rows
        if not row["excluded"] and row["index"] not in selected
    ]
    optional.sort(
        key=lambda row: (
            -(row["priority"] / max(row["cost"], 0.000001)),
            -row["priority"],
            row["index"],
        )
    )
    for row in optional:
        projected = spent + row["cost"]
        if projected <= target_usd + 1e-9:
            selected.add(row["index"])
            spent = round(projected, 6)

    out_story: list[dict[str, Any]] = []
    out_plan: list[dict[str, Any]] = []
    treatments: Counter[str] = Counter()
    domains: Counter[str] = Counter()
    video_seconds = 0
    missing_domain: list[str] = []
    required_not_video: list[str] = []

    for row in rows:
        story = row["story"]
        plan = row["plan"]
        duration = row["duration"]
        is_video = row["index"] in selected
        treatment = "GENERATED_VIDEO" if is_video else _non_video_treatment(plan)
        if row["required"] and not is_video:
            required_not_video.append(str(story.get("shot_id") or row["index"]))
        generated_seconds = duration if is_video else 0
        video_seconds += generated_seconds
        panel_count = (
            max(1, math.ceil(duration / 6.0))
            if treatment == "DYNAMIC_STILL_SEQUENCE"
            else 0
        )
        clip_count = (
            max(1, math.ceil(generated_seconds / PROVIDER_CLIP_SECONDS))
            if is_video else 0
        )
        domain = str(plan.get("scene_domain") or "")
        if not domain:
            missing_domain.append(str(story.get("shot_id") or row["index"]))

        merged_story = dict(story)
        merged_story.update(
            {
                "schema_version": "siraj-storyboard-shot-v2",
                "production_shot_id": str(
                    plan.get("shot_id") or story.get("shot_id") or row["index"]
                ),
                "scene_domain": domain,
                "character_location": str(plan.get("character_location") or "NONE"),
                "representation_mode": str(plan.get("representation_mode") or ""),
                "representation_claim": str(plan.get("representation_claim") or ""),
                "location_transition": str(plan.get("location_transition") or ""),
                "motion_necessity": "REQUIRED" if row["required"] else "OPTIONAL",
                "final_budget_treatment": treatment,
                "planned_seconds": duration,
                "planned_generated_video_seconds": generated_seconds,
                "estimated_generated_video_cost_usd": (
                    row["cost"] if is_video else 0.0
                ),
                "video_priority_v2": row["priority"],
                "provider_clip_seconds": PROVIDER_CLIP_SECONDS if is_video else 0,
                "provider_clip_count": clip_count,
                "motion_profile": (
                    "GENERATED_CONTINUOUS_MOTION"
                    if is_video
                    else (
                        "LAYERED_PARALLAX_MULTI_AXIS"
                        if treatment == "DYNAMIC_STILL_SEQUENCE"
                        else "AUTHORED"
                    )
                ),
                "still_panel_count": panel_count,
                "maximum_still_panel_seconds": (
                    round(duration / panel_count, 3) if panel_count else 0
                ),
                "simple_zoom_only": "FORBIDDEN",
                "last_frame_extension_max_seconds": 1.25,
            }
        )
        out_story.append(merged_story)

        merged_plan = dict(plan)
        merged_plan.update(
            {
                "final_budget_treatment": treatment,
                "planned_generated_video_seconds": generated_seconds,
                "estimated_generated_video_cost_usd": (
                    row["cost"] if is_video else 0.0
                ),
                "provider_clip_seconds": PROVIDER_CLIP_SECONDS if is_video else 0,
                "provider_clip_count": clip_count,
                "motion_profile": merged_story["motion_profile"],
                "still_panel_count": panel_count,
                "maximum_still_panel_seconds": merged_story[
                    "maximum_still_panel_seconds"
                ],
                "production_status": "V2_REPLANNED_NOT_PRODUCED",
            }
        )
        out_plan.append(merged_plan)
        treatments[treatment] += 1
        domains[domain or "MISSING"] += 1

    storyboard = dict(legacy_storyboard)
    storyboard.update(
        {
            "schema_version": "siraj-storyboard-and-media-plan-v2",
            "status": "V2_VISUAL_REPLAN_READY_FOR_HUMAN_REVIEW",
            "shots": out_story,
            "generated_video_budget": {
                "target_usd": target_usd,
                "hard_cap_usd": hard_usd,
                "estimated_cost_per_second_usd": round(cost_per_second_usd, 9),
                "estimated_spend_usd": round(spent, 6),
                "planned_generated_video_seconds": video_seconds,
                "seconds_target": "NONE_COST_AND_QUALITY_DRIVEN",
            },
        }
    )
    plan = dict(production_plan)
    plan.update(
        {
            "schema_version": "siraj-episode-production-plan-v2",
            "plan_id": "adam_episode_production_plan_v2_budget_driven",
            "policy_path": "contracts/episode-production-policy-v2.json",
            "status": "V2_VISUAL_REPLAN_READY_FOR_HUMAN_REVIEW",
            "shots": out_plan,
            "treatment_counts": dict(sorted(treatments.items())),
            "generated_video_budget": storyboard["generated_video_budget"],
            "next_stage": "HUMAN_VISUAL_REPLAN_REVIEW_BEFORE_PAID_EXECUTION",
        }
    )
    max_panel = max(
        (
            shot["maximum_still_panel_seconds"]
            for shot in out_story
            if shot["final_budget_treatment"] == "DYNAMIC_STILL_SEQUENCE"
        ),
        default=0,
    )
    summary = {
        "schema_version": "siraj-adam-visual-replan-summary-v2",
        "status": (
            "PASS_REPLAN_READY_FOR_HUMAN_REVIEW"
            if not required_not_video and not missing_domain
            else "BLOCKED_REPLAN_INCOMPLETE"
        ),
        "shot_count": len(rows),
        "generated_video": {
            "shot_count": treatments["GENERATED_VIDEO"],
            "seconds": video_seconds,
            "estimated_spend_usd": round(spent, 6),
            "target_usd": target_usd,
            "hard_cap_usd": hard_usd,
            "estimated_cost_per_second_usd": round(cost_per_second_usd, 9),
        },
        "treatment_counts": dict(sorted(treatments.items())),
        "scene_domain_counts": dict(sorted(domains.items())),
        "maximum_dynamic_still_panel_seconds": max_panel,
        "required_motion_not_video": required_not_video,
        "missing_scene_domain": missing_domain,
        "human_review_required": True,
        "paid_execution_authorized": False,
        "next_stage": "ARABIC_PERFORMANCE_SCRIPT_V2_AND_HUMAN_VISUAL_REVIEW",
    }
    return AdamVisualReplanResult(storyboard, plan, summary)
