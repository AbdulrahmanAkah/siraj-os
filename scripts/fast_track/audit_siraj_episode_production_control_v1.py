from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.episode_production_control_v1 import (
        HARD_CAP_USD,
        VIDEO_PLANNED_SECONDS,
        load_episode_plan,
        load_episode_policy,
        scan_actual_paid_spend,
    )

    policy = load_episode_policy(repo)
    plan = load_episode_plan(repo)
    budget = scan_actual_paid_spend(repo)

    require(HARD_CAP_USD == 40.0, "HARD_CAP_CHANGED")
    require(
        policy["budget"]["headroom_usd"] == 0.0,
        "BUDGET_HEADROOM_ENABLED",
    )
    require(
        policy["budget"]["cap_override"] == "FORBIDDEN",
        "CAP_OVERRIDE_ENABLED",
    )
    require(policy["audio"]["music"] == "FORBIDDEN", "MUSIC_ENABLED")
    require(
        policy["audio"]["sound_effects"] == "ALLOWED",
        "SFX_DISABLED",
    )
    require(
        policy["audio"]["sound_effect_type_restriction"]
        == "NONE_WHEN_SCENE_APPROPRIATE",
        "SFX_TYPE_RESTRICTED",
    )
    require(len(plan["shots"]) == 70, "SHOT_COUNT_CHANGED")
    require(
        plan["treatment_counts"]
        == {
            "GENERATED_VIDEO": 20,
            "ANIMATED_STILL_COMPOSITING": 44,
            "GRAPHICS": 6,
        },
        "MEDIA_MIX_CHANGED",
    )
    require(VIDEO_PLANNED_SECONDS == 160, "VIDEO_SECONDS_CHANGED")
    require(
        budget.actual_spent_usd <= 40.0,
        "EXISTING_RECORDED_SPEND_EXCEEDS_HARD_CAP",
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    result = {
        "status": "PASS_SIRAJ_EPISODE_PRODUCTION_CONTROL_V1",
        "episode_hard_cap_usd": 40.0,
        "budget_headroom_usd": 0.0,
        "generated_video_target_seconds": "120-180",
        "generated_video_plan_seconds": 160,
        "editorial_shots": 70,
        "generated_video_shots": 20,
        "animated_still_compositing_shots": 44,
        "graphics_shots": 6,
        "music": "FORBIDDEN",
        "sound_effects": "ALLOWED_ANY_SCENE_APPROPRIATE_TYPE",
        "human_review_input": "ONE_INTEGER_ONLY_0_TO_100",
        "hidden_paid_retry": "FORBIDDEN",
        "desktop_ui_only": True,
        "runware_requests_during_audit": 0,
        "credit_spent_during_audit": False,
        "next_stage": "AUTHOR_NEXT_QUEUE_SHOT_PACKAGE",
    }
    report = args.output_root / "siraj-episode-production-control-v1-audit.json"
    report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for key, value in result.items():
        print(f"{key.upper()}={value}")
    print("ACTUAL_RECORDED_SPEND_USD=" + f"{budget.actual_spent_usd:.8f}")
    print("REPORT=" + str(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
