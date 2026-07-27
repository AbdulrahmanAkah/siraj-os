"""Deterministic compiler from a Siraj storyboard to a cinematic-series plan.

This module performs editorial planning only. It allocates narrative functions,
episode time, generated-video time, media treatment, and budget envelopes
without contacting any provider or estimating provider-specific prices.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from typing import Iterable

from src.application.documentary_intelligence import deterministic_id

from .cinematic_series import (
    GENERATED_VIDEO_HARD_LIMIT_SECONDS,
    HARD_MEDIA_BUDGET_USD,
    RUNWARE_EXECUTION_STATUS,
    TARGET_MEDIA_BUDGET_USD,
    CinematicFrameDirective,
    CinematicSeriesError,
    CinematicSeriesRuntime,
    CinematicStoryboardPlan,
    EpisodeSeriesContract,
    EvidenceMode,
    NarrativeFunction,
    SpectacleLevel,
)
from .models import Storyboard, StoryboardFrame


CINEMATIC_COMPILER_SCHEMA_VERSION = "siraj-cinematic-compiler-v1"
MIN_EPISODE_SECONDS = 18 * 60
DEFAULT_EPISODE_SECONDS = 22 * 60
MAX_EPISODE_SECONDS = 25 * 60
DEFAULT_GENERATED_VIDEO_TARGET_SECONDS = 150
MIN_COMPILABLE_FRAMES = 7


class MediaTreatment(StrEnum):
    EVIDENCE_LED = "evidence_led"
    STILL_LED = "still_led"
    HYBRID_SEQUENCE = "hybrid_sequence"


@dataclass(frozen=True, slots=True)
class CinematicBudgetEnvelope:
    """Editorial reservation, not a provider-price estimate."""

    image_reserve_usd: float = 8.0
    video_reserve_usd: float = 29.0
    audio_reserve_usd: float = 1.0
    retry_reserve_usd: float = 2.0
    hard_headroom_usd: float = 5.0

    @property
    def target_total_usd(self) -> float:
        return round(
            self.image_reserve_usd
            + self.video_reserve_usd
            + self.audio_reserve_usd
            + self.retry_reserve_usd,
            2,
        )

    @property
    def hard_total_usd(self) -> float:
        return round(self.target_total_usd + self.hard_headroom_usd, 2)

    def validate(self) -> None:
        values = (
            self.image_reserve_usd,
            self.video_reserve_usd,
            self.audio_reserve_usd,
            self.retry_reserve_usd,
            self.hard_headroom_usd,
        )
        if any(value < 0 for value in values):
            raise CinematicSeriesError("Budget-envelope values cannot be negative.")
        if self.target_total_usd != TARGET_MEDIA_BUDGET_USD:
            raise CinematicSeriesError(
                "The cinematic compiler target envelope must equal USD 40."
            )
        if self.hard_total_usd != HARD_MEDIA_BUDGET_USD:
            raise CinematicSeriesError(
                "The cinematic compiler hard envelope must equal USD 45."
            )


@dataclass(frozen=True, slots=True)
class CinematicCompilationPolicy:
    target_episode_seconds: int = DEFAULT_EPISODE_SECONDS
    minimum_episode_seconds: int = MIN_EPISODE_SECONDS
    maximum_episode_seconds: int = MAX_EPISODE_SECONDS
    generated_video_target_seconds: int = DEFAULT_GENERATED_VIDEO_TARGET_SECONDS
    minimum_storyboard_frames: int = MIN_COMPILABLE_FRAMES

    def validate(self) -> None:
        if self.minimum_episode_seconds != MIN_EPISODE_SECONDS:
            raise CinematicSeriesError("Minimum episode duration is fixed at 18 minutes.")
        if self.maximum_episode_seconds != MAX_EPISODE_SECONDS:
            raise CinematicSeriesError("Maximum episode duration is fixed at 25 minutes.")
        if not (
            self.minimum_episode_seconds
            <= self.target_episode_seconds
            <= self.maximum_episode_seconds
        ):
            raise CinematicSeriesError(
                "Target episode duration must be between 18 and 25 minutes."
            )
        if not (
            0
            < self.generated_video_target_seconds
            <= GENERATED_VIDEO_HARD_LIMIT_SECONDS
        ):
            raise CinematicSeriesError(
                "Generated-video target must be positive and no more than 300 seconds."
            )
        if self.minimum_storyboard_frames < MIN_COMPILABLE_FRAMES:
            raise CinematicSeriesError(
                "The compiler requires at least seven storyboard frames."
            )


@dataclass(frozen=True, slots=True)
class CompiledFrameAssignment:
    frame_id: str
    media_treatment: MediaTreatment
    generation_priority: int
    narrative_reason: str
    reserved_generated_video_seconds: int

    def validate(self) -> None:
        if not self.frame_id.strip():
            raise CinematicSeriesError("Compiled frame id must not be blank.")
        if not 0 <= self.generation_priority <= 100:
            raise CinematicSeriesError(
                "Generation priority must be between 0 and 100."
            )
        if not self.narrative_reason.strip():
            raise CinematicSeriesError("Narrative reason must not be blank.")
        if self.reserved_generated_video_seconds < 0:
            raise CinematicSeriesError(
                "Reserved generated-video seconds cannot be negative."
            )
        if (
            self.reserved_generated_video_seconds > 0
            and self.media_treatment is not MediaTreatment.HYBRID_SEQUENCE
        ):
            raise CinematicSeriesError(
                "Generated-video reservations require HYBRID_SEQUENCE treatment."
            )


@dataclass(frozen=True, slots=True)
class CompiledCinematicEpisode:
    compilation_id: str
    schema_version: str
    plan: CinematicStoryboardPlan
    policy: CinematicCompilationPolicy
    budget: CinematicBudgetEnvelope
    assignments: tuple[CompiledFrameAssignment, ...]
    live_execution_allowed: bool = False
    provider_price_estimate_status: str = "UNAVAILABLE_PENDING_MANUAL_PROVIDER_TEST"

    def to_manifest(self) -> dict[str, object]:
        contract = self.plan.contract
        return {
            "schema_version": self.schema_version,
            "compilation_id": self.compilation_id,
            "plan_id": self.plan.plan_id,
            "storyboard_id": self.plan.storyboard_id,
            "episode_contract": {
                "series_title": contract.series_title,
                "season_title": contract.season_title,
                "episode_id": contract.episode_id,
                "season_question": contract.season_question,
                "central_question": contract.central_question,
                "emotional_promise": contract.emotional_promise,
                "knowledge_promise": contract.knowledge_promise,
                "unresolved_thread_from_previous": (
                    contract.unresolved_thread_from_previous
                ),
                "next_episode_question": contract.next_episode_question,
            },
            "duration": {
                "target_episode_seconds": self.policy.target_episode_seconds,
                "planned_episode_seconds": sum(
                    item.planned_seconds for item in self.plan.directives
                ),
                "generated_video_target_seconds": (
                    self.policy.generated_video_target_seconds
                ),
                "generated_video_planned_seconds": (
                    self.plan.generated_video_seconds
                ),
                "generated_video_hard_limit_seconds": (
                    contract.generated_video_hard_limit_seconds
                ),
            },
            "budget_envelope_usd": {
                "image_reserve": self.budget.image_reserve_usd,
                "video_reserve": self.budget.video_reserve_usd,
                "audio_reserve": self.budget.audio_reserve_usd,
                "retry_reserve": self.budget.retry_reserve_usd,
                "target_total": self.budget.target_total_usd,
                "hard_headroom": self.budget.hard_headroom_usd,
                "hard_total": self.budget.hard_total_usd,
            },
            "anticipation_score": self.plan.anticipation_score,
            "runware_execution_status": self.plan.runware_execution_status,
            "live_execution_allowed": self.live_execution_allowed,
            "provider_price_estimate_status": (
                self.provider_price_estimate_status
            ),
            "frames": [
                {
                    "frame_id": directive.frame_id,
                    "narrative_function": directive.narrative_function.value,
                    "evidence_mode": directive.evidence_mode.value,
                    "spectacle_level": directive.spectacle_level.value,
                    "planned_seconds": directive.planned_seconds,
                    "generated_video_seconds": (
                        directive.generated_video_seconds
                    ),
                    "callback_to_frame_id": (
                        directive.callback_to_frame_id
                    ),
                    "media_treatment": assignment.media_treatment.value,
                    "generation_priority": assignment.generation_priority,
                    "narrative_reason": assignment.narrative_reason,
                }
                for directive, assignment in zip(
                    self.plan.directives,
                    self.assignments,
                    strict=True,
                )
            ],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_manifest(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class CinematicSeriesCompiler:
    """Compile a complete deterministic baseline from an existing storyboard."""

    def __init__(self, runtime: CinematicSeriesRuntime | None = None) -> None:
        self._runtime = runtime or CinematicSeriesRuntime()

    def compile(
        self,
        storyboard: Storyboard,
        contract: EpisodeSeriesContract,
        *,
        policy: CinematicCompilationPolicy | None = None,
        budget: CinematicBudgetEnvelope | None = None,
    ) -> CompiledCinematicEpisode:
        resolved_policy = policy or CinematicCompilationPolicy()
        resolved_budget = budget or CinematicBudgetEnvelope()
        contract.validate()
        resolved_policy.validate()
        resolved_budget.validate()
        self._validate_storyboard(storyboard, resolved_policy)

        functions = self._assign_narrative_functions(storyboard.frame_count)
        planned_seconds = self._allocate_integer_total(
            resolved_policy.target_episode_seconds,
            [self._duration_weight(item) for item in functions],
        )
        generated_video_seconds = self._allocate_video_seconds(
            functions,
            planned_seconds,
            resolved_policy.generated_video_target_seconds,
        )

        directives = tuple(
            self._build_directive(
                frame=frame,
                function=function,
                planned_seconds=duration,
                generated_video_seconds=video_seconds,
                first_frame_id=storyboard.frames[0].frame_id,
            )
            for frame, function, duration, video_seconds in zip(
                storyboard.frames,
                functions,
                planned_seconds,
                generated_video_seconds,
                strict=True,
            )
        )
        plan = self._runtime.build_plan(storyboard, contract, directives)
        assignments = tuple(
            self._build_assignment(directive)
            for directive in directives
        )
        compilation_id = deterministic_id(
            "cinematic_compilation",
            [
                CINEMATIC_COMPILER_SCHEMA_VERSION,
                plan.plan_id,
                resolved_policy.target_episode_seconds,
                resolved_policy.generated_video_target_seconds,
                resolved_budget.target_total_usd,
                resolved_budget.hard_total_usd,
                [
                    [
                        item.frame_id,
                        item.media_treatment.value,
                        item.generation_priority,
                    ]
                    for item in assignments
                ],
            ],
        )
        compiled = CompiledCinematicEpisode(
            compilation_id=compilation_id,
            schema_version=CINEMATIC_COMPILER_SCHEMA_VERSION,
            plan=plan,
            policy=resolved_policy,
            budget=resolved_budget,
            assignments=assignments,
        )
        self._validate_compilation(storyboard, compiled)
        return compiled

    def validate_compilation(
        self,
        storyboard: Storyboard,
        compiled: CompiledCinematicEpisode,
    ) -> bool:
        try:
            self._validate_compilation(storyboard, compiled)
            rebuilt = self.compile(
                storyboard,
                compiled.plan.contract,
                policy=compiled.policy,
                budget=compiled.budget,
            )
            return rebuilt == compiled
        except (CinematicSeriesError, TypeError, ValueError):
            return False

    @staticmethod
    def _validate_storyboard(
        storyboard: Storyboard,
        policy: CinematicCompilationPolicy,
    ) -> None:
        if not isinstance(storyboard, Storyboard):
            raise CinematicSeriesError("Expected a Storyboard instance.")
        if storyboard.validation_state != "VALID":
            raise CinematicSeriesError("Storyboard must be valid.")
        if storyboard.frame_count != len(storyboard.frames):
            raise CinematicSeriesError("Storyboard frame count is inconsistent.")
        if storyboard.frame_count < policy.minimum_storyboard_frames:
            raise CinematicSeriesError(
                "Storyboard has too few frames for a complete cinematic arc."
            )
        positions = [frame.position for frame in storyboard.frames]
        if positions != list(range(storyboard.frame_count)):
            raise CinematicSeriesError(
                "Storyboard frames must be ordered with contiguous positions."
            )
        frame_ids = [frame.frame_id for frame in storyboard.frames]
        if any(not frame_id.strip() for frame_id in frame_ids):
            raise CinematicSeriesError("Storyboard frame ids must not be blank.")
        if len(set(frame_ids)) != len(frame_ids):
            raise CinematicSeriesError("Storyboard frame ids must be unique.")

    @staticmethod
    def _assign_narrative_functions(
        frame_count: int,
    ) -> tuple[NarrativeFunction, ...]:
        if frame_count < MIN_COMPILABLE_FRAMES:
            raise CinematicSeriesError(
                "At least seven frames are required for cinematic compilation."
            )

        functions = [NarrativeFunction.DISCOVERY] * frame_count
        functions[0] = NarrativeFunction.COLD_OPEN
        functions[1] = NarrativeFunction.CENTRAL_QUESTION
        functions[-1] = NarrativeFunction.NEXT_EPISODE_PROMISE
        functions[-2] = NarrativeFunction.CONSEQUENCE

        climax_index = min(
            frame_count - 3,
            max(4, round((frame_count - 1) * 0.72)),
        )
        reversal_index = min(
            climax_index - 1,
            max(3, round((frame_count - 1) * 0.52)),
        )
        functions[climax_index] = NarrativeFunction.CLIMAX
        functions[reversal_index] = NarrativeFunction.REVERSAL

        if frame_count >= 8:
            functions[2] = NarrativeFunction.ORIENTATION

        for index in range(2, frame_count - 2):
            if index in (reversal_index, climax_index):
                continue
            if index < reversal_index:
                functions[index] = (
                    NarrativeFunction.ORIENTATION
                    if index == 2 and frame_count >= 8
                    else NarrativeFunction.DISCOVERY
                )
            elif index < climax_index:
                functions[index] = NarrativeFunction.ESCALATION
            else:
                functions[index] = NarrativeFunction.CONSEQUENCE

        return tuple(functions)

    @staticmethod
    def _duration_weight(function: NarrativeFunction) -> float:
        return {
            NarrativeFunction.COLD_OPEN: 0.65,
            NarrativeFunction.CENTRAL_QUESTION: 0.85,
            NarrativeFunction.ORIENTATION: 1.00,
            NarrativeFunction.DISCOVERY: 1.45,
            NarrativeFunction.ESCALATION: 1.35,
            NarrativeFunction.REVERSAL: 1.10,
            NarrativeFunction.CLIMAX: 1.30,
            NarrativeFunction.CONSEQUENCE: 1.00,
            NarrativeFunction.NEXT_EPISODE_PROMISE: 0.65,
        }[function]

    @staticmethod
    def _video_weight(function: NarrativeFunction) -> float:
        return {
            NarrativeFunction.COLD_OPEN: 1.00,
            NarrativeFunction.CENTRAL_QUESTION: 0.00,
            NarrativeFunction.ORIENTATION: 0.15,
            NarrativeFunction.DISCOVERY: 0.35,
            NarrativeFunction.ESCALATION: 0.80,
            NarrativeFunction.REVERSAL: 0.90,
            NarrativeFunction.CLIMAX: 1.50,
            NarrativeFunction.CONSEQUENCE: 0.50,
            NarrativeFunction.NEXT_EPISODE_PROMISE: 0.35,
        }[function]

    @staticmethod
    def _allocate_integer_total(
        total: int,
        weights: Iterable[float],
    ) -> tuple[int, ...]:
        ordered = tuple(weights)
        if total <= 0:
            raise CinematicSeriesError("Allocation total must be positive.")
        if not ordered or any(weight < 0 for weight in ordered):
            raise CinematicSeriesError("Allocation weights are invalid.")
        weight_total = sum(ordered)
        if weight_total <= 0:
            raise CinematicSeriesError("At least one allocation weight is required.")

        exact = [total * weight / weight_total for weight in ordered]
        allocated = [int(value) for value in exact]
        remainder = total - sum(allocated)
        order = sorted(
            range(len(ordered)),
            key=lambda index: (-(exact[index] - allocated[index]), index),
        )
        for index in order[:remainder]:
            allocated[index] += 1
        return tuple(allocated)

    def _allocate_video_seconds(
        self,
        functions: tuple[NarrativeFunction, ...],
        planned_seconds: tuple[int, ...],
        target: int,
    ) -> tuple[int, ...]:
        weights = [self._video_weight(item) for item in functions]
        allocated = list(self._allocate_integer_total(target, weights))

        overflow = 0
        for index, value in enumerate(allocated):
            cap = planned_seconds[index]
            if value > cap:
                overflow += value - cap
                allocated[index] = cap

        if overflow:
            candidates = [
                index
                for index, weight in enumerate(weights)
                if weight > 0 and allocated[index] < planned_seconds[index]
            ]
            while overflow and candidates:
                changed = False
                for index in candidates:
                    if overflow == 0:
                        break
                    if allocated[index] < planned_seconds[index]:
                        allocated[index] += 1
                        overflow -= 1
                        changed = True
                if not changed:
                    break
            if overflow:
                raise CinematicSeriesError(
                    "The requested generated-video target cannot fit the episode."
                )

        return tuple(allocated)

    def _build_directive(
        self,
        *,
        frame: StoryboardFrame,
        function: NarrativeFunction,
        planned_seconds: int,
        generated_video_seconds: int,
        first_frame_id: str,
    ) -> CinematicFrameDirective:
        callback = (
            first_frame_id
            if function is NarrativeFunction.NEXT_EPISODE_PROMISE
            else None
        )
        return CinematicFrameDirective(
            frame_id=frame.frame_id,
            narrative_function=function,
            evidence_mode=self._evidence_mode(frame, function),
            spectacle_level=self._spectacle_level(function),
            planned_seconds=planned_seconds,
            generated_video_seconds=generated_video_seconds,
            callback_to_frame_id=callback,
        )

    @staticmethod
    def _evidence_mode(
        frame: StoryboardFrame,
        function: NarrativeFunction,
    ) -> EvidenceMode:
        if function in (
            NarrativeFunction.COLD_OPEN,
            NarrativeFunction.NEXT_EPISODE_PROMISE,
        ):
            return EvidenceMode.ATMOSPHERIC_TRANSITION
        if not frame.referenced_evidence_ids:
            return EvidenceMode.SYMBOLIC_VISUALIZATION
        if function in (
            NarrativeFunction.CENTRAL_QUESTION,
            NarrativeFunction.ORIENTATION,
            NarrativeFunction.DISCOVERY,
            NarrativeFunction.REVERSAL,
        ):
            return EvidenceMode.DOCUMENTARY_EVIDENCE
        return EvidenceMode.EVIDENCE_BASED_RECONSTRUCTION

    @staticmethod
    def _spectacle_level(
        function: NarrativeFunction,
    ) -> SpectacleLevel:
        return {
            NarrativeFunction.COLD_OPEN: SpectacleLevel.CONTROLLED,
            NarrativeFunction.CENTRAL_QUESTION: SpectacleLevel.QUIET,
            NarrativeFunction.ORIENTATION: SpectacleLevel.QUIET,
            NarrativeFunction.DISCOVERY: SpectacleLevel.CONTROLLED,
            NarrativeFunction.ESCALATION: SpectacleLevel.ELEVATED,
            NarrativeFunction.REVERSAL: SpectacleLevel.ELEVATED,
            NarrativeFunction.CLIMAX: SpectacleLevel.PEAK,
            NarrativeFunction.CONSEQUENCE: SpectacleLevel.CONTROLLED,
            NarrativeFunction.NEXT_EPISODE_PROMISE: SpectacleLevel.QUIET,
        }[function]

    @staticmethod
    def _build_assignment(
        directive: CinematicFrameDirective,
    ) -> CompiledFrameAssignment:
        function = directive.narrative_function
        if directive.generated_video_seconds > 0:
            treatment = MediaTreatment.HYBRID_SEQUENCE
        elif directive.evidence_mode is EvidenceMode.DOCUMENTARY_EVIDENCE:
            treatment = MediaTreatment.EVIDENCE_LED
        else:
            treatment = MediaTreatment.STILL_LED

        priority = {
            NarrativeFunction.COLD_OPEN: 90,
            NarrativeFunction.CENTRAL_QUESTION: 20,
            NarrativeFunction.ORIENTATION: 25,
            NarrativeFunction.DISCOVERY: 45,
            NarrativeFunction.ESCALATION: 70,
            NarrativeFunction.REVERSAL: 85,
            NarrativeFunction.CLIMAX: 100,
            NarrativeFunction.CONSEQUENCE: 60,
            NarrativeFunction.NEXT_EPISODE_PROMISE: 75,
        }[function]
        reason = {
            NarrativeFunction.COLD_OPEN: "Establish immediate curiosity and visual identity.",
            NarrativeFunction.CENTRAL_QUESTION: "Clarify the episode promise with restrained evidence.",
            NarrativeFunction.ORIENTATION: "Ground time, place, actors, and evidentiary limits.",
            NarrativeFunction.DISCOVERY: "Reward attention with a material evidentiary reveal.",
            NarrativeFunction.ESCALATION: "Increase consequence without reaching the climax early.",
            NarrativeFunction.REVERSAL: "Reframe the viewer's current understanding.",
            NarrativeFunction.CLIMAX: "Concentrate the episode's strongest dramatic and visual payoff.",
            NarrativeFunction.CONSEQUENCE: "Show what the climax changes beyond the isolated event.",
            NarrativeFunction.NEXT_EPISODE_PROMISE: "Open a necessary question and callback after the climax.",
        }[function]
        return CompiledFrameAssignment(
            frame_id=directive.frame_id,
            media_treatment=treatment,
            generation_priority=priority,
            narrative_reason=reason,
            reserved_generated_video_seconds=directive.generated_video_seconds,
        )

    def _validate_compilation(
        self,
        storyboard: Storyboard,
        compiled: CompiledCinematicEpisode,
    ) -> None:
        if not isinstance(compiled, CompiledCinematicEpisode):
            raise CinematicSeriesError(
                "Expected a CompiledCinematicEpisode instance."
            )
        compiled.policy.validate()
        compiled.budget.validate()
        if compiled.schema_version != CINEMATIC_COMPILER_SCHEMA_VERSION:
            raise CinematicSeriesError("Unexpected cinematic compiler schema.")
        if compiled.live_execution_allowed:
            raise CinematicSeriesError(
                "Live provider execution must remain disabled."
            )
        if (
            compiled.plan.runware_execution_status
            != RUNWARE_EXECUTION_STATUS
        ):
            raise CinematicSeriesError("Runware execution gate changed unexpectedly.")
        if not self._runtime.validate_plan(storyboard, compiled.plan):
            raise CinematicSeriesError("Compiled cinematic plan is invalid.")
        if len(compiled.assignments) != storyboard.frame_count:
            raise CinematicSeriesError(
                "Every frame requires one compiled media assignment."
            )
        frame_ids = [frame.frame_id for frame in storyboard.frames]
        assignment_ids = [item.frame_id for item in compiled.assignments]
        directive_ids = [item.frame_id for item in compiled.plan.directives]
        if assignment_ids != frame_ids or directive_ids != frame_ids:
            raise CinematicSeriesError(
                "Compiled assignments must preserve storyboard order."
            )
        for assignment in compiled.assignments:
            assignment.validate()
        planned_seconds = sum(
            item.planned_seconds for item in compiled.plan.directives
        )
        if planned_seconds != compiled.policy.target_episode_seconds:
            raise CinematicSeriesError(
                "Compiled episode duration does not match the target."
            )
        if (
            compiled.plan.generated_video_seconds
            != compiled.policy.generated_video_target_seconds
        ):
            raise CinematicSeriesError(
                "Generated-video allocation does not match the target."
            )
        if (
            compiled.plan.generated_video_seconds
            > GENERATED_VIDEO_HARD_LIMIT_SECONDS
        ):
            raise CinematicSeriesError(
                "Generated-video allocation exceeds the hard limit."
            )
        if compiled.plan.anticipation_score < 8:
            raise CinematicSeriesError(
                "Compiled episode does not meet the anticipation baseline."
            )
        expected_compilation_id = deterministic_id(
            "cinematic_compilation",
            [
                CINEMATIC_COMPILER_SCHEMA_VERSION,
                compiled.plan.plan_id,
                compiled.policy.target_episode_seconds,
                compiled.policy.generated_video_target_seconds,
                compiled.budget.target_total_usd,
                compiled.budget.hard_total_usd,
                [
                    [
                        item.frame_id,
                        item.media_treatment.value,
                        item.generation_priority,
                    ]
                    for item in compiled.assignments
                ],
            ],
        )
        if compiled.compilation_id != expected_compilation_id:
            raise CinematicSeriesError("Compilation id is not deterministic.")
