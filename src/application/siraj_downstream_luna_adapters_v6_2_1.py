"""Luna downstream production adapters hardened for V6.2.1 visual policy."""

from __future__ import annotations

from pathlib import Path

from src.application.siraj_luna_stage_transport_v6_1 import (
    execute_authorized_json_stage,
)


def semantic_prompt_direction(
    repo_root: Path,
    episode_id: str,
    storyboard: dict,
):
    instructions = """
Create the production-ready visual prompt plan from the certified audio-bound
storyboard.

SERIES VISUAL MIX LAW (SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2):
- True generated-video timeline coverage must remain between 50% and 75% of
  the exact episode timeline.
- The range is a hard whole-episode constraint, not a quota target. Select
  the percentage through directorial optimization from the approved sequence
  grammar and cinematic function.
- Animated stills, graphics/local animation, provider-requested-but-unused
  duration, loops and reused clips do not count as true video coverage.
- There is NO creative 8-second scene limit.
- Provider duration must be selected from the current provider contract for
  actual timeline use plus explicit edit handles; never use a fixed fallback.
  If one continuous cinematic scene must last longer, represent it as
  video_subshots under one scene_continuity_id. Every subshot must be a genuine
  forward visual progression, with a unique visual_progression_id, distinct
  camera/action/composition, and its own prompt. Never loop, duplicate, freeze,
  or restate the same shot to fill time.
- Every visual item must exactly cover its assigned narration time range.

DUPLICATE LAW:
- No repeated prompt wording that produces the same visual idea.
- No semantically duplicated shots even when wording differs.
- Adjacent shots must have meaningful visual progression.
- ONE GENERATED ASSET -> ONE TIMELINE SLOT by default.
- Reuse requires explicit editorial reuse_justification.
- Long-scene subshots must preserve continuity anchors while changing visual
  progression.

Each item MUST contain:
shot_id, queue_index, beat_id, segment_ids, start_seconds, end_seconds,
final_budget_treatment selected from ANIMATED_STILL_COMPOSITING /
GENERATED_VIDEO / GRAPHICS, semantic_beat, subject, environment, composition,
camera_angle, camera_movement, scene_continuity_id, visual_progression_id,
runware_positive_prompt_en, runware_negative_prompt_en, contains_people.
When GENERATED_VIDEO duration exceeds the provider's current supported unit,
also return video_subshots. Each subshot must include start_seconds,
end_seconds, visual_progression_id, runware_positive_prompt_en, and all
continuity-critical fields. When treatment is GRAPHICS, include graphics_spec.

Do not impose a fixed number of images, videos, scenes, or shots.
Do not generate Arabic text inside provider images/video.
Return JSON with status PASS and items only after self-review.
"""
    return execute_authorized_json_stage(
        repo_root,
        episode_id,
        "LUNA_SEMANTIC_PROMPT_DIRECTION",
        instructions,
        storyboard,
        "preproduction/luna-semantic-prompt-direction-v6-2-1.json",
    )


def narration_visual_alignment(
    repo_root: Path,
    episode_id: str,
    script: dict,
    prompts: dict,
):
    instructions = """
Audit every planned visual against exact narration meaning and timeline.
Also enforce SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2 true-video floor and ceiling,
the hard whole-episode 50%-75% range, and the long-scene progressive
subshot rule, continuity without duplication, and the rule that asset reuse
requires explicit editorial justification. Fail generic, semantically repeated,
temporally misplaced, theologically invented, or visually stagnant shot plans.
Return PASS only when the complete plan is safe for pre-spend deterministic
duplicate validation.
"""
    return execute_authorized_json_stage(
        repo_root,
        episode_id,
        "NARRATION_VISUAL_ALIGNMENT_GATE",
        instructions,
        {"script": script, "prompts": prompts},
        "preproduction/narration-visual-alignment-gate-v6-2-1.json",
    )
