from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from src.application.production_quality_gate_v2 import (
    evaluate_production_quality,
)
from src.application.series_production_quality_v2 import (
    HARD_GENERATED_VIDEO_SPEND_USD,
    TARGET_GENERATED_VIDEO_SPEND_USD,
    SeriesProductionPolicyV2,
    SceneDomain,
    RepresentationMode,
    motion_required_for_shot,
    write_policy,
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def infer_domain(shot: Mapping[str, Any]) -> tuple[str, str, str]:
    text = " ".join(
        str(shot.get(key) or "")
        for key in (
            "label_ar",
            "visual_brief_ar",
            "dramatic_function_ar",
            "positive_prompt",
        )
    ).lower()
    unseen_terms = (
        "السماء",
        "الجنة",
        "الملائكة",
        "العالم العلوي",
        "heaven",
        "paradise",
        "unseen",
    )
    document_terms = ("مخطوط", "وثيقة", "خريطة", "document", "map")
    if any(term in text for term in unseen_terms):
        return (
            SceneDomain.HEAVENLY_UNSEEN_SYMBOLIC.value,
            RepresentationMode.SYMBOLIC_UNSEEN.value,
            "SYMBOLIC_NON_DEFINITIVE",
        )
    if any(term in text for term in document_terms):
        return (
            SceneDomain.DOCUMENTARY_EVIDENCE.value,
            RepresentationMode.DOCUMENTARY.value,
            "DOCUMENTARY",
        )
    return (
        SceneDomain.EARTHLY_WORLD.value,
        RepresentationMode.EVIDENCE_BASED_RECONSTRUCTION.value,
        "EVIDENCE_BASED",
    )


def migrate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    shots = plan.get("shots")
    if not isinstance(shots, list):
        raise RuntimeError("PLAN_SHOTS_REQUIRED")
    migrated: list[dict[str, Any]] = []
    prior_domain: str | None = None
    for raw in shots:
        if not isinstance(raw, Mapping):
            raise RuntimeError("SHOT_OBJECT_REQUIRED")
        shot = dict(raw)
        domain, representation, claim = infer_domain(shot)
        shot["scene_domain"] = str(shot.get("scene_domain") or domain)
        shot["representation_mode"] = str(
            shot.get("representation_mode") or representation
        )
        shot["representation_claim"] = str(
            shot.get("representation_claim") or claim
        )
        shot["character_location"] = str(
            shot.get("character_location") or "NONE"
        )
        if prior_domain is not None and shot["scene_domain"] != prior_domain:
            shot["location_transition"] = str(
                shot.get("location_transition")
                or "EDITORIALLY_PLANNED_DOMAIN_TRANSITION"
            )
        shot["motion_necessity"] = (
            "REQUIRED" if motion_required_for_shot(shot) else "OPTIONAL"
        )
        existing = str(
            shot.get("final_budget_treatment")
            or shot.get("treatment")
            or ""
        )
        if shot["motion_necessity"] == "REQUIRED":
            shot["recommended_treatment_v2"] = "GENERATED_VIDEO"
            shot["video_priority_v2"] = 100
        elif existing == "GENERATED_VIDEO":
            shot["recommended_treatment_v2"] = "GENERATED_VIDEO"
            shot["video_priority_v2"] = 85
        elif shot["scene_domain"] == SceneDomain.DOCUMENTARY_EVIDENCE.value:
            shot["recommended_treatment_v2"] = "DOCUMENT_OR_MAP"
            shot["video_priority_v2"] = 20
        else:
            shot["recommended_treatment_v2"] = "GENERATED_VIDEO_OR_DYNAMIC_STILL"
            shot["video_priority_v2"] = 65
        if existing in {
            "ANIMATED_STILL_COMPOSITING",
            "GENERATED_IMAGE",
        }:
            shot["still_policy_v2"] = {
                "maximum_seconds": 7,
                "simple_zoom_only": "FORBIDDEN",
                "layered_parallax_required": True,
                "dynamic_light_or_internal_motion_required": True,
            }
        shot["last_frame_extension_policy_v2"] = {
            "maximum_seconds": 1.25,
            "long_freeze": "FORBIDDEN",
        }
        prior_domain = shot["scene_domain"]
        migrated.append(shot)

    plan["schema_version"] = "siraj-episode-production-plan-v2"
    plan["status"] = "V2_REPLAN_REQUIRED_BEFORE_PAID_EXECUTION"
    plan["generated_video_budget"] = {
        "target_usd": TARGET_GENERATED_VIDEO_SPEND_USD,
        "hard_cap_usd": HARD_GENERATED_VIDEO_SPEND_USD,
        "seconds_target": "NONE_COST_AND_QUALITY_DRIVEN",
    }
    plan["media_strategy"] = {
        "mode": "BUDGET_DRIVEN_VIDEO_FIRST",
        "still_usage": "LIMITED_AND_INTENTIONAL",
        "flat_slideshow": "FORBIDDEN",
    }
    plan["shots"] = migrated
    plan.pop("hard_cap_usd", None)
    plan.pop("generated_video_target_seconds", None)
    plan["treatment_counts_v1_preserved_for_audit_only"] = plan.pop(
        "treatment_counts", None
    )
    return plan


def migrate_policy(episode_id: str) -> dict[str, Any]:
    return {
        "schema_version": "siraj-episode-production-policy-v2",
        "status": "HUMAN_DIRECTIVES_ACTIVE",
        "episode_id": episode_id,
        "inherits": "projects/_series/siraj-series-production-policy-v2.json",
        "budget": {
            "generated_video_target_usd": TARGET_GENERATED_VIDEO_SPEND_USD,
            "generated_video_hard_cap_usd": HARD_GENERATED_VIDEO_SPEND_USD,
            "preflight_required_before_each_paid_request": True,
            "hidden_paid_retry": "FORBIDDEN",
            "cap_override": "FORBIDDEN",
        },
        "media_mix": {
            "production_mode": "BUDGET_DRIVEN_VIDEO_FIRST",
            "generated_video_seconds_target": "NONE_COST_AND_QUALITY_DRIVEN",
            "still_image_usage": "LIMITED_AND_INTENTIONAL",
            "flat_slideshow": "FORBIDDEN",
            "simple_zoom_only": "FORBIDDEN",
            "maximum_still_led_seconds": 7,
            "maximum_last_frame_extension_seconds": 1.25,
        },
        "audio": {
            "music": "FORBIDDEN",
            "sound_effects": "ALLOWED",
            "fully_diacritized_tts_required": True,
            "explicit_pause_plan_required": True,
            "target_words_per_minute": 116,
            "maximum_words_per_minute": 128,
            "human_language_review_required": True,
            "human_performance_review_required": True,
        },
        "unseen_world": {
            "explicit_scene_domain_required": True,
            "earthly_visual_default_for_unseen": "FORBIDDEN",
            "representation_claim": "SYMBOLIC_NON_DEFINITIVE",
            "unsupported_religious_detail": "FORBIDDEN",
            "location_continuity_required": True,
        },
        "release_gate": {
            "black_intervals_over_one_second": "BLOCKING",
            "unplanned_silence_over_three_seconds": "BLOCKING",
            "freeze_over_1_25_seconds": "BLOCKING",
            "cheap_still_montage": "BLOCKING",
            "world_continuity_violation": "BLOCKING",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--episode", default="episode-001-adam")
    parser.add_argument("--validate-existing", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    episode = repo / "projects" / args.episode
    if not (repo / ".git").exists():
        raise RuntimeError(f"NOT_A_GIT_REPOSITORY:{repo}")
    if not episode.is_dir():
        raise RuntimeError(f"EPISODE_NOT_FOUND:{episode}")

    series_policy_path = (
        repo / "projects" / "_series" / "siraj-series-production-policy-v2.json"
    )
    write_policy(series_policy_path, SeriesProductionPolicyV2())

    episode_policy_path = (
        episode / "contracts" / "episode-production-policy-v2.json"
    )
    write_json(episode_policy_path, migrate_policy(args.episode))

    old_plan = episode / "cinematic" / "episode-production-plan-v1.json"
    new_plan = episode / "cinematic" / "episode-production-plan-v2.json"
    if old_plan.is_file():
        migrated_plan = migrate_plan(read_json(old_plan))
        write_json(new_plan, migrated_plan)
    elif not new_plan.is_file():
        raise RuntimeError("NO_EPISODE_PLAN_FOUND")
    else:
        migrated_plan = read_json(new_plan)

    script_candidates = (
        episode / "script" / "episode-script-v2.json",
        episode / "script" / "episode-script-v1.json",
    )
    script_path = next((p for p in script_candidates if p.is_file()), None)
    storyboard_candidates = (
        episode / "cinematic" / "storyboard-and-media-plan-v2.json",
        episode / "cinematic" / "storyboard-and-media-plan-v1.json",
    )
    storyboard_path = next(
        (p for p in storyboard_candidates if p.is_file()),
        None,
    )

    report = {
        "schema_version": "siraj-series-quality-v2-migration-report",
        "release": "SIRAJ_SERIES_PRODUCTION_QUALITY_V2",
        "episode_id": args.episode,
        "status": "MIGRATED_REPLAN_AND_HUMAN_REVIEW_REQUIRED",
        "created": {
            "series_policy": str(series_policy_path.relative_to(repo)).replace("\\", "/"),
            "episode_policy": str(episode_policy_path.relative_to(repo)).replace("\\", "/"),
            "episode_plan": str(new_plan.relative_to(repo)).replace("\\", "/"),
        },
        "budget": {
            "generated_video_target_usd": TARGET_GENERATED_VIDEO_SPEND_USD,
            "generated_video_hard_cap_usd": HARD_GENERATED_VIDEO_SPEND_USD,
            "seconds_target": "NONE_COST_AND_QUALITY_DRIVEN",
        },
        "required_next_actions": [
            "FULLY_DIACRITIZE_AND_HUMAN_REVIEW_TTS_SCRIPT",
            "RECOMPILE_STORYBOARD_WITH_VIDEO_FIRST_V2",
            "REVIEW_HEAVENLY_UNSEEN_SCENE_DOMAINS",
            "REPLACE_CHEAP_STILL_MONTAGE",
            "RENDER_AND_RUN_PRODUCTION_QUALITY_GATE_V2",
        ],
    }

    if args.validate_existing and script_path and storyboard_path:
        script = read_json(script_path)
        storyboard = read_json(storyboard_path)
        gate = evaluate_production_quality(
            script=script,
            storyboard=storyboard,
            generated_video_spend_usd=0.0,
        )
        report["existing_material_gate"] = gate

    report_path = (
        episode / "orchestration" / "series-quality-v2-migration-report.json"
    )
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
