"""Video-first wrapper around the existing Siraj cinematic compiler."""

from __future__ import annotations

from dataclasses import replace

from src.application.documentary_intelligence import deterministic_id
from src.application.series_production_quality_v2 import (
    HARD_GENERATED_VIDEO_SPEND_USD,
    TARGET_GENERATED_VIDEO_SPEND_USD,
)

from .cinematic_compiler import (
    CINEMATIC_COMPILER_SCHEMA_VERSION,
    CinematicBudgetGuardrails,
    CinematicCompilationPolicy,
    CinematicSeriesCompiler,
    CompiledCinematicEpisode,
    CompiledFrameAssignment,
    MediaTreatment,
    MotionNeed,
)
from .cinematic_series import NarrativeFunction


CINEMATIC_COMPILER_V2_SCHEMA_VERSION = "siraj-cinematic-compiler-video-first-v2"


class CinematicSeriesCompilerV2(CinematicSeriesCompiler):
    def compile(
        self,
        storyboard,
        contract,
        *,
        policy: CinematicCompilationPolicy | None = None,
        budget: CinematicBudgetGuardrails | None = None,
    ) -> CompiledCinematicEpisode:
        resolved_budget = budget or CinematicBudgetGuardrails(
            target_total_usd=TARGET_GENERATED_VIDEO_SPEND_USD,
            hard_total_usd=HARD_GENERATED_VIDEO_SPEND_USD,
        )
        base = super().compile(
            storyboard,
            contract,
            policy=policy,
            budget=resolved_budget,
        )
        directives = {
            item.frame_id: item for item in base.plan.directives
        }
        assignments = tuple(
            self._upgrade(item, directives[item.frame_id])
            for item in base.assignments
        )
        compilation_id = deterministic_id(
            "cinematic_compilation_video_first_v2",
            [
                base.compilation_id,
                [
                    [
                        item.frame_id,
                        item.preferred_treatment.value,
                        item.motion_need.value,
                        item.generation_priority,
                        item.maximum_generated_video_seconds,
                    ]
                    for item in assignments
                ],
            ],
        )
        return replace(
            base,
            compilation_id=compilation_id,
            schema_version=CINEMATIC_COMPILER_V2_SCHEMA_VERSION,
            assignments=assignments,
        )

    @staticmethod
    def _upgrade(
        assignment: CompiledFrameAssignment,
        directive,
    ) -> CompiledFrameAssignment:
        function = directive.narrative_function
        motion_required = function in {
            NarrativeFunction.COLD_OPEN,
            NarrativeFunction.ESCALATION,
            NarrativeFunction.REVERSAL,
            NarrativeFunction.CLIMAX,
            NarrativeFunction.CONSEQUENCE,
        }
        evidence_only = function in {
            NarrativeFunction.CENTRAL_QUESTION,
            NarrativeFunction.ORIENTATION,
        }
        preferred = assignment.preferred_treatment
        if motion_required:
            preferred = MediaTreatment.GENERATED_VIDEO
        elif (
            function is NarrativeFunction.DISCOVERY
            and preferred is MediaTreatment.GENERATED_IMAGE
        ):
            preferred = MediaTreatment.GENERATED_VIDEO
        allowed = list(assignment.allowed_treatments)
        if not evidence_only and MediaTreatment.GENERATED_VIDEO not in allowed:
            allowed.insert(0, MediaTreatment.GENERATED_VIDEO)
        if preferred not in allowed:
            allowed.insert(0, preferred)
        allowed = tuple(dict.fromkeys(allowed))
        maximum = (
            directive.planned_seconds
            if preferred is MediaTreatment.GENERATED_VIDEO
            else min(directive.planned_seconds, 12)
        )
        upgraded = replace(
            assignment,
            preferred_treatment=preferred,
            allowed_treatments=allowed,
            motion_need=(
                MotionNeed.REQUIRED
                if motion_required
                else MotionNeed.OPTIONAL
            ),
            generation_priority=min(
                100,
                assignment.generation_priority
                + (20 if preferred is MediaTreatment.GENERATED_VIDEO else 0),
            ),
            maximum_generated_video_seconds=maximum,
            narrative_reason=(
                assignment.narrative_reason
                + " V2 uses generated motion whenever temporal change carries meaning."
            ),
        )
        upgraded.validate()
        return upgraded
