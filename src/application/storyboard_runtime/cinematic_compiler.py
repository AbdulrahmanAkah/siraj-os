"""Dynamic cinematic compiler and budget planner for Siraj storyboards.

The compiler creates an editorial blueprint. It does not pre-allocate money to
images, video, audio, or retries and it does not reserve a fixed amount of
AI-video time. The budget planner makes those decisions only after priced media
options are supplied. No provider call or paid execution occurs in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import json
from typing import Iterable, Mapping

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


CINEMATIC_COMPILER_SCHEMA_VERSION = "siraj-cinematic-compiler-v2"
DYNAMIC_BUDGET_PLANNER_SCHEMA_VERSION = "siraj-dynamic-budget-planner-v1"
MIN_EPISODE_SECONDS = 18 * 60
DEFAULT_EPISODE_SECONDS = 22 * 60
MAX_EPISODE_SECONDS = 25 * 60
MIN_COMPILABLE_FRAMES = 7
BUDGET_ALLOCATION_STATUS = "DEFERRED_PENDING_PRICED_MEDIA_OPTIONS"
PROVIDER_PRICE_ESTIMATE_STATUS = "UNAVAILABLE_PENDING_MANUAL_PROVIDER_TEST"
PRICED_OPTIONS_STATUS = "PRICED_MEDIA_OPTIONS_SUPPLIED_OFFLINE"


class MediaTreatment(StrEnum):
    EVIDENCE_LED = "evidence_led"
    STILL_LED = "still_led"
    LOCAL_ANIMATION = "local_animation"
    GENERATED_IMAGE = "generated_image"
    GENERATED_VIDEO = "generated_video"
    MAP_LED = "map_led"
    DOCUMENT_LED = "document_led"
    HYBRID_SEQUENCE = "hybrid_sequence"  # compatibility option


class MotionNeed(StrEnum):
    NONE = "none"
    OPTIONAL = "optional"
    REQUIRED = "required"


class MediaCategory(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    LOCAL_ANIMATION = "local_animation"
    UPSCALE_REPAIR = "upscale_repair"
    DOCUMENT = "document"
    MAP = "map"
    OTHER = "other"


MOTION_CAPABLE_TREATMENTS = frozenset(
    {
        MediaTreatment.LOCAL_ANIMATION,
        MediaTreatment.GENERATED_VIDEO,
        MediaTreatment.HYBRID_SEQUENCE,
    }
)


@dataclass(frozen=True, slots=True)
class CinematicBudgetGuardrails:
    """Only the episode-level financial constraints are fixed."""

    target_total_usd: float = TARGET_MEDIA_BUDGET_USD
    hard_total_usd: float = HARD_MEDIA_BUDGET_USD

    def validate(self) -> None:
        if self.target_total_usd != TARGET_MEDIA_BUDGET_USD:
            raise CinematicSeriesError("The target episode budget is fixed at USD 40.")
        if self.hard_total_usd != HARD_MEDIA_BUDGET_USD:
            raise CinematicSeriesError("The hard episode budget is fixed at USD 45.")
        if self.hard_total_usd < self.target_total_usd:
            raise CinematicSeriesError("Hard budget must not be below target budget.")


# Backward-compatible import name. The object is now guardrails, not a category
# envelope and therefore exposes no image/video/audio/retry reserves.
CinematicBudgetEnvelope = CinematicBudgetGuardrails


@dataclass(frozen=True, slots=True)
class CinematicCompilationPolicy:
    target_episode_seconds: int = DEFAULT_EPISODE_SECONDS
    minimum_episode_seconds: int = MIN_EPISODE_SECONDS
    maximum_episode_seconds: int = MAX_EPISODE_SECONDS
    generated_video_hard_limit_seconds: int = GENERATED_VIDEO_HARD_LIMIT_SECONDS
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
        if (
            self.generated_video_hard_limit_seconds
            != GENERATED_VIDEO_HARD_LIMIT_SECONDS
        ):
            raise CinematicSeriesError(
                "Generated-video hard limit is fixed at 300 seconds."
            )
        if self.minimum_storyboard_frames < MIN_COMPILABLE_FRAMES:
            raise CinematicSeriesError(
                "The compiler requires at least seven storyboard frames."
            )


@dataclass(frozen=True, slots=True)
class CompiledFrameAssignment:
    frame_id: str
    preferred_treatment: MediaTreatment
    allowed_treatments: tuple[MediaTreatment, ...]
    motion_need: MotionNeed
    generation_priority: int
    narrative_reason: str
    maximum_generated_video_seconds: int

    def validate(self) -> None:
        if not self.frame_id.strip():
            raise CinematicSeriesError("Compiled frame id must not be blank.")
        if not self.allowed_treatments:
            raise CinematicSeriesError("At least one media treatment must be allowed.")
        if self.preferred_treatment not in self.allowed_treatments:
            raise CinematicSeriesError(
                "Preferred treatment must be one of the allowed treatments."
            )
        if len(set(self.allowed_treatments)) != len(self.allowed_treatments):
            raise CinematicSeriesError("Allowed media treatments must be unique.")
        if not 0 <= self.generation_priority <= 100:
            raise CinematicSeriesError(
                "Generation priority must be between 0 and 100."
            )
        if not self.narrative_reason.strip():
            raise CinematicSeriesError("Narrative reason must not be blank.")
        if not (
            0
            <= self.maximum_generated_video_seconds
            <= GENERATED_VIDEO_HARD_LIMIT_SECONDS
        ):
            raise CinematicSeriesError(
                "Frame generated-video ceiling must be between 0 and 300 seconds."
            )
        if (
            self.motion_need is MotionNeed.REQUIRED
            and not MOTION_CAPABLE_TREATMENTS.intersection(self.allowed_treatments)
        ):
            raise CinematicSeriesError(
                "Motion-required frames need at least one motion-capable treatment."
            )


@dataclass(frozen=True, slots=True)
class CompiledCinematicEpisode:
    compilation_id: str
    schema_version: str
    plan: CinematicStoryboardPlan
    policy: CinematicCompilationPolicy
    budget: CinematicBudgetGuardrails
    assignments: tuple[CompiledFrameAssignment, ...]
    budget_allocation_status: str = BUDGET_ALLOCATION_STATUS
    live_execution_allowed: bool = False
    provider_price_estimate_status: str = PROVIDER_PRICE_ESTIMATE_STATUS

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
                "generated_video_allocation_status": self.budget_allocation_status,
                "generated_video_planned_seconds": self.plan.generated_video_seconds,
                "generated_video_hard_limit_seconds": (
                    self.policy.generated_video_hard_limit_seconds
                ),
            },
            "budget_guardrails_usd": {
                "target_total": self.budget.target_total_usd,
                "hard_total": self.budget.hard_total_usd,
            },
            "dynamic_budget_allocation": {
                "status": self.budget_allocation_status,
                "allocated_total_usd": None,
                "category_totals_usd": None,
            },
            "anticipation_score": self.plan.anticipation_score,
            "runware_execution_status": self.plan.runware_execution_status,
            "live_execution_allowed": self.live_execution_allowed,
            "provider_price_estimate_status": self.provider_price_estimate_status,
            "frames": [
                {
                    "frame_id": directive.frame_id,
                    "narrative_function": directive.narrative_function.value,
                    "evidence_mode": directive.evidence_mode.value,
                    "spectacle_level": directive.spectacle_level.value,
                    "planned_seconds": directive.planned_seconds,
                    "generated_video_seconds": directive.generated_video_seconds,
                    "callback_to_frame_id": directive.callback_to_frame_id,
                    "preferred_treatment": assignment.preferred_treatment.value,
                    "allowed_treatments": [
                        item.value for item in assignment.allowed_treatments
                    ],
                    "motion_need": assignment.motion_need.value,
                    "generation_priority": assignment.generation_priority,
                    "maximum_generated_video_seconds": (
                        assignment.maximum_generated_video_seconds
                    ),
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


@dataclass(frozen=True, slots=True)
class PricedMediaOption:
    option_id: str
    frame_id: str
    treatment: MediaTreatment
    category: MediaCategory
    estimated_cost_usd: float
    quality_score: int
    reliability_score: int
    generated_video_seconds: int = 0
    provider_id: str = "OFFLINE_OR_LOCAL"
    model_id: str = "UNSPECIFIED"
    price_source_id: str = "MANUAL_OR_TEST_FIXTURE"

    def validate(self) -> None:
        for value, name in (
            (self.option_id, "option_id"),
            (self.frame_id, "frame_id"),
            (self.provider_id, "provider_id"),
            (self.model_id, "model_id"),
            (self.price_source_id, "price_source_id"),
        ):
            if not value.strip():
                raise CinematicSeriesError(f"{name} must not be blank.")
        if self.estimated_cost_usd < 0:
            raise CinematicSeriesError("Estimated media cost cannot be negative.")
        if round(self.estimated_cost_usd, 2) != self.estimated_cost_usd:
            raise CinematicSeriesError("Estimated media cost must use at most two decimals.")
        if not 0 <= self.quality_score <= 100:
            raise CinematicSeriesError("Quality score must be between 0 and 100.")
        if not 0 <= self.reliability_score <= 100:
            raise CinematicSeriesError("Reliability score must be between 0 and 100.")
        if not (
            0
            <= self.generated_video_seconds
            <= GENERATED_VIDEO_HARD_LIMIT_SECONDS
        ):
            raise CinematicSeriesError(
                "Generated-video seconds must be between 0 and 300."
            )
        if (
            self.generated_video_seconds > 0
            and self.treatment
            not in {MediaTreatment.GENERATED_VIDEO, MediaTreatment.HYBRID_SEQUENCE}
        ):
            raise CinematicSeriesError(
                "Generated-video seconds require a generated-video treatment."
            )


@dataclass(frozen=True, slots=True)
class FixedProductionCost:
    item_id: str
    category: MediaCategory
    estimated_cost_usd: float
    description: str

    def validate(self) -> None:
        if not self.item_id.strip() or not self.description.strip():
            raise CinematicSeriesError(
                "Fixed production cost id and description must not be blank."
            )
        if self.estimated_cost_usd < 0:
            raise CinematicSeriesError("Fixed production cost cannot be negative.")
        if round(self.estimated_cost_usd, 2) != self.estimated_cost_usd:
            raise CinematicSeriesError(
                "Fixed production cost must use at most two decimals."
            )


@dataclass(frozen=True, slots=True)
class BudgetedCinematicEpisode:
    allocation_id: str
    schema_version: str
    editorial_compilation_id: str
    final_plan: CinematicStoryboardPlan
    selected_options: tuple[PricedMediaOption, ...]
    fixed_costs: tuple[FixedProductionCost, ...]
    category_totals_usd: tuple[tuple[str, float], ...]
    allocated_total_usd: float
    budget_limit_usd: float
    hard_headroom_used: bool
    hard_headroom_justification: str | None
    provider_price_estimate_status: str = PRICED_OPTIONS_STATUS
    live_execution_allowed: bool = False

    def to_manifest(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "allocation_id": self.allocation_id,
            "editorial_compilation_id": self.editorial_compilation_id,
            "final_plan_id": self.final_plan.plan_id,
            "budget": {
                "allocated_total_usd": self.allocated_total_usd,
                "budget_limit_usd": self.budget_limit_usd,
                "hard_headroom_used": self.hard_headroom_used,
                "hard_headroom_justification": self.hard_headroom_justification,
                "category_totals_usd": dict(self.category_totals_usd),
            },
            "generated_video_seconds": self.final_plan.generated_video_seconds,
            "provider_price_estimate_status": self.provider_price_estimate_status,
            "live_execution_allowed": self.live_execution_allowed,
            "selected_options": [
                {
                    "option_id": item.option_id,
                    "frame_id": item.frame_id,
                    "treatment": item.treatment.value,
                    "category": item.category.value,
                    "estimated_cost_usd": item.estimated_cost_usd,
                    "quality_score": item.quality_score,
                    "reliability_score": item.reliability_score,
                    "generated_video_seconds": item.generated_video_seconds,
                    "provider_id": item.provider_id,
                    "model_id": item.model_id,
                    "price_source_id": item.price_source_id,
                }
                for item in self.selected_options
            ],
            "fixed_costs": [
                {
                    "item_id": item.item_id,
                    "category": item.category.value,
                    "estimated_cost_usd": item.estimated_cost_usd,
                    "description": item.description,
                }
                for item in self.fixed_costs
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
    """Compile a deterministic editorial blueprint from an existing storyboard."""

    def __init__(self, runtime: CinematicSeriesRuntime | None = None) -> None:
        self._runtime = runtime or CinematicSeriesRuntime()

    def compile(
        self,
        storyboard: Storyboard,
        contract: EpisodeSeriesContract,
        *,
        policy: CinematicCompilationPolicy | None = None,
        budget: CinematicBudgetGuardrails | None = None,
    ) -> CompiledCinematicEpisode:
        resolved_policy = policy or CinematicCompilationPolicy()
        resolved_budget = budget or CinematicBudgetGuardrails()
        contract.validate()
        resolved_policy.validate()
        resolved_budget.validate()
        self._validate_storyboard(storyboard, resolved_policy)

        functions = self._assign_narrative_functions(storyboard.frame_count)
        planned_seconds = self._allocate_integer_total(
            resolved_policy.target_episode_seconds,
            [self._duration_weight(item) for item in functions],
        )

        directives = tuple(
            self._build_directive(
                frame=frame,
                function=function,
                planned_seconds=duration,
                first_frame_id=storyboard.frames[0].frame_id,
            )
            for frame, function, duration in zip(
                storyboard.frames,
                functions,
                planned_seconds,
                strict=True,
            )
        )
        plan = self._runtime.build_plan(storyboard, contract, directives)
        assignments = tuple(
            self._build_assignment(directive) for directive in directives
        )
        compilation_id = deterministic_id(
            "cinematic_compilation",
            [
                CINEMATIC_COMPILER_SCHEMA_VERSION,
                plan.plan_id,
                resolved_policy.target_episode_seconds,
                resolved_budget.target_total_usd,
                resolved_budget.hard_total_usd,
                [
                    [
                        item.frame_id,
                        item.preferred_treatment.value,
                        [value.value for value in item.allowed_treatments],
                        item.motion_need.value,
                        item.generation_priority,
                        item.maximum_generated_video_seconds,
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

    def _build_directive(
        self,
        *,
        frame: StoryboardFrame,
        function: NarrativeFunction,
        planned_seconds: int,
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
            generated_video_seconds=0,
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
    def _spectacle_level(function: NarrativeFunction) -> SpectacleLevel:
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
        evidence_led = directive.evidence_mode is EvidenceMode.DOCUMENTARY_EVIDENCE

        preferred = {
            NarrativeFunction.COLD_OPEN: MediaTreatment.GENERATED_VIDEO,
            NarrativeFunction.CENTRAL_QUESTION: MediaTreatment.EVIDENCE_LED,
            NarrativeFunction.ORIENTATION: MediaTreatment.MAP_LED,
            NarrativeFunction.DISCOVERY: (
                MediaTreatment.EVIDENCE_LED
                if evidence_led
                else MediaTreatment.GENERATED_IMAGE
            ),
            NarrativeFunction.ESCALATION: MediaTreatment.LOCAL_ANIMATION,
            NarrativeFunction.REVERSAL: (
                MediaTreatment.EVIDENCE_LED
                if evidence_led
                else MediaTreatment.GENERATED_VIDEO
            ),
            NarrativeFunction.CLIMAX: MediaTreatment.GENERATED_VIDEO,
            NarrativeFunction.CONSEQUENCE: MediaTreatment.LOCAL_ANIMATION,
            NarrativeFunction.NEXT_EPISODE_PROMISE: MediaTreatment.LOCAL_ANIMATION,
        }[function]

        allowed = {
            NarrativeFunction.COLD_OPEN: (
                MediaTreatment.GENERATED_VIDEO,
                MediaTreatment.LOCAL_ANIMATION,
                MediaTreatment.GENERATED_IMAGE,
                MediaTreatment.STILL_LED,
            ),
            NarrativeFunction.CENTRAL_QUESTION: (
                MediaTreatment.EVIDENCE_LED,
                MediaTreatment.DOCUMENT_LED,
                MediaTreatment.MAP_LED,
                MediaTreatment.STILL_LED,
            ),
            NarrativeFunction.ORIENTATION: (
                MediaTreatment.MAP_LED,
                MediaTreatment.DOCUMENT_LED,
                MediaTreatment.EVIDENCE_LED,
                MediaTreatment.STILL_LED,
            ),
            NarrativeFunction.DISCOVERY: (
                MediaTreatment.EVIDENCE_LED,
                MediaTreatment.DOCUMENT_LED,
                MediaTreatment.GENERATED_IMAGE,
                MediaTreatment.LOCAL_ANIMATION,
                MediaTreatment.STILL_LED,
            ),
            NarrativeFunction.ESCALATION: (
                MediaTreatment.LOCAL_ANIMATION,
                MediaTreatment.GENERATED_VIDEO,
                MediaTreatment.GENERATED_IMAGE,
                MediaTreatment.STILL_LED,
            ),
            NarrativeFunction.REVERSAL: (
                MediaTreatment.EVIDENCE_LED,
                MediaTreatment.DOCUMENT_LED,
                MediaTreatment.LOCAL_ANIMATION,
                MediaTreatment.GENERATED_VIDEO,
                MediaTreatment.STILL_LED,
            ),
            NarrativeFunction.CLIMAX: (
                MediaTreatment.GENERATED_VIDEO,
                MediaTreatment.LOCAL_ANIMATION,
                MediaTreatment.GENERATED_IMAGE,
                MediaTreatment.STILL_LED,
            ),
            NarrativeFunction.CONSEQUENCE: (
                MediaTreatment.LOCAL_ANIMATION,
                MediaTreatment.GENERATED_IMAGE,
                MediaTreatment.EVIDENCE_LED,
                MediaTreatment.STILL_LED,
            ),
            NarrativeFunction.NEXT_EPISODE_PROMISE: (
                MediaTreatment.LOCAL_ANIMATION,
                MediaTreatment.GENERATED_VIDEO,
                MediaTreatment.GENERATED_IMAGE,
                MediaTreatment.STILL_LED,
            ),
        }[function]

        motion_need = (
            MotionNeed.NONE
            if function
            in {
                NarrativeFunction.CENTRAL_QUESTION,
                NarrativeFunction.ORIENTATION,
                NarrativeFunction.DISCOVERY,
            }
            else MotionNeed.OPTIONAL
        )
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
        maximum_video = {
            NarrativeFunction.COLD_OPEN: 30,
            NarrativeFunction.CENTRAL_QUESTION: 0,
            NarrativeFunction.ORIENTATION: 0,
            NarrativeFunction.DISCOVERY: 12,
            NarrativeFunction.ESCALATION: 30,
            NarrativeFunction.REVERSAL: 30,
            NarrativeFunction.CLIMAX: 60,
            NarrativeFunction.CONSEQUENCE: 20,
            NarrativeFunction.NEXT_EPISODE_PROMISE: 15,
        }[function]
        maximum_video = min(maximum_video, directive.planned_seconds)
        reason = {
            NarrativeFunction.COLD_OPEN: "Establish immediate curiosity and visual identity.",
            NarrativeFunction.CENTRAL_QUESTION: "Clarify the episode promise with restrained evidence.",
            NarrativeFunction.ORIENTATION: "Ground time, place, actors, and evidentiary limits.",
            NarrativeFunction.DISCOVERY: "Reward attention with a material evidentiary reveal.",
            NarrativeFunction.ESCALATION: "Increase consequence without reaching the climax early.",
            NarrativeFunction.REVERSAL: "Reframe the viewer's current understanding.",
            NarrativeFunction.CLIMAX: "Concentrate the strongest dramatic and visual payoff.",
            NarrativeFunction.CONSEQUENCE: "Show what the climax changes beyond the event.",
            NarrativeFunction.NEXT_EPISODE_PROMISE: "Open the next necessary question after the climax.",
        }[function]
        assignment = CompiledFrameAssignment(
            frame_id=directive.frame_id,
            preferred_treatment=preferred,
            allowed_treatments=allowed,
            motion_need=motion_need,
            generation_priority=priority,
            narrative_reason=reason,
            maximum_generated_video_seconds=maximum_video,
        )
        assignment.validate()
        return assignment

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
        if compiled.budget_allocation_status != BUDGET_ALLOCATION_STATUS:
            raise CinematicSeriesError("Budget allocation must remain deferred.")
        if compiled.provider_price_estimate_status != PROVIDER_PRICE_ESTIMATE_STATUS:
            raise CinematicSeriesError("Provider prices must remain unavailable.")
        if compiled.live_execution_allowed:
            raise CinematicSeriesError("Live provider execution must remain disabled.")
        if compiled.plan.runware_execution_status != RUNWARE_EXECUTION_STATUS:
            raise CinematicSeriesError("Runware execution gate changed unexpectedly.")
        if compiled.plan.generated_video_seconds != 0:
            raise CinematicSeriesError(
                "Editorial compilation cannot pre-allocate generated-video seconds."
            )
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
                compiled.budget.target_total_usd,
                compiled.budget.hard_total_usd,
                [
                    [
                        item.frame_id,
                        item.preferred_treatment.value,
                        [value.value for value in item.allowed_treatments],
                        item.motion_need.value,
                        item.generation_priority,
                        item.maximum_generated_video_seconds,
                    ]
                    for item in compiled.assignments
                ],
            ],
        )
        if compiled.compilation_id != expected_compilation_id:
            raise CinematicSeriesError("Compilation id is not deterministic.")


class DynamicCinematicBudgetPlanner:
    """Choose the best priced media mix under the episode budget guardrails."""

    def __init__(self, runtime: CinematicSeriesRuntime | None = None) -> None:
        self._runtime = runtime or CinematicSeriesRuntime()

    def plan(
        self,
        storyboard: Storyboard,
        compiled: CompiledCinematicEpisode,
        options: Iterable[PricedMediaOption],
        *,
        fixed_costs: Iterable[FixedProductionCost] = (),
        allow_hard_headroom: bool = False,
        hard_headroom_justification: str | None = None,
    ) -> BudgetedCinematicEpisode:
        if not CinematicSeriesCompiler(self._runtime).validate_compilation(
            storyboard, compiled
        ):
            raise CinematicSeriesError("Editorial compilation is invalid.")
        ordered_options = tuple(options)
        ordered_fixed = tuple(fixed_costs)
        for item in ordered_options:
            item.validate()
        for item in ordered_fixed:
            item.validate()
        if len({item.option_id for item in ordered_options}) != len(ordered_options):
            raise CinematicSeriesError("Priced media option ids must be unique.")
        if len({item.item_id for item in ordered_fixed}) != len(ordered_fixed):
            raise CinematicSeriesError("Fixed production cost ids must be unique.")
        if allow_hard_headroom and not (hard_headroom_justification or "").strip():
            raise CinematicSeriesError(
                "Using the USD 45 hard headroom requires explicit justification."
            )
        if not allow_hard_headroom and hard_headroom_justification is not None:
            raise CinematicSeriesError(
                "Headroom justification is invalid when hard headroom is disabled."
            )

        budget_limit = (
            compiled.budget.hard_total_usd
            if allow_hard_headroom
            else compiled.budget.target_total_usd
        )
        base_cost_cents = sum(
            self._to_cents(item.estimated_cost_usd) for item in ordered_fixed
        )
        if base_cost_cents > self._to_cents(budget_limit):
            raise CinematicSeriesError(
                "Fixed production costs already exceed the selected budget limit."
            )

        option_groups: dict[str, list[PricedMediaOption]] = {}
        for item in ordered_options:
            option_groups.setdefault(item.frame_id, []).append(item)

        assignment_by_id = {item.frame_id: item for item in compiled.assignments}
        expected_frame_ids = [item.frame_id for item in compiled.assignments]
        extra_frame_ids = sorted(set(option_groups).difference(expected_frame_ids))
        if extra_frame_ids:
            raise CinematicSeriesError(
                f"Priced options reference unknown frames: {extra_frame_ids}"
            )

        eligible_groups: list[tuple[PricedMediaOption, ...]] = []
        for frame_id in expected_frame_ids:
            assignment = assignment_by_id[frame_id]
            eligible = tuple(
                sorted(
                    (
                        item
                        for item in option_groups.get(frame_id, [])
                        if self._option_is_eligible(assignment, item)
                    ),
                    key=lambda item: item.option_id,
                )
            )
            if not eligible:
                raise CinematicSeriesError(
                    f"No eligible priced media option exists for frame {frame_id}."
                )
            eligible_groups.append(eligible)

        states: dict[
            int,
            tuple[int, tuple[str, ...], tuple[PricedMediaOption, ...]],
        ] = {base_cost_cents: (0, (), ())}
        limit_cents = self._to_cents(budget_limit)

        for assignment, group in zip(
            compiled.assignments,
            eligible_groups,
            strict=True,
        ):
            next_states: dict[
                int,
                tuple[int, tuple[str, ...], tuple[PricedMediaOption, ...]],
            ] = {}
            for current_cost, (current_score, current_ids, current_items) in states.items():
                for option in group:
                    next_cost = current_cost + self._to_cents(
                        option.estimated_cost_usd
                    )
                    if next_cost > limit_cents:
                        continue
                    next_score = current_score + self._option_utility(
                        assignment, option
                    )
                    next_ids = (*current_ids, option.option_id)
                    candidate = (
                        next_score,
                        next_ids,
                        (*current_items, option),
                    )
                    existing = next_states.get(next_cost)
                    if existing is None or self._candidate_better(
                        candidate, existing
                    ):
                        next_states[next_cost] = candidate
            states = next_states
            if not states:
                raise CinematicSeriesError(
                    "No complete media plan fits the selected budget limit."
                )

        selected_cost_cents, best = sorted(
            states.items(),
            key=lambda item: (
                -item[1][0],  # highest editorial utility
                item[0],      # then lower cost
                item[1][1],   # then stable option-id order
            ),
        )[0]
        selected = best[2]
        generated_video_seconds = sum(
            item.generated_video_seconds for item in selected
        )
        if generated_video_seconds > compiled.policy.generated_video_hard_limit_seconds:
            raise CinematicSeriesError(
                "Selected media plan exceeds the 300-second video ceiling."
            )

        selected_by_frame = {item.frame_id: item for item in selected}
        final_directives = tuple(
            replace(
                directive,
                generated_video_seconds=(
                    selected_by_frame[directive.frame_id].generated_video_seconds
                ),
            )
            for directive in compiled.plan.directives
        )
        final_plan = self._runtime.build_plan(
            storyboard,
            compiled.plan.contract,
            final_directives,
        )
        category_totals = self._category_totals(selected, ordered_fixed)
        allocated_total = self._from_cents(selected_cost_cents)
        hard_headroom_used = allocated_total > compiled.budget.target_total_usd
        if hard_headroom_used and not allow_hard_headroom:
            raise CinematicSeriesError("Hard budget headroom was used without approval.")

        allocation_id = deterministic_id(
            "cinematic_budget_allocation",
            [
                DYNAMIC_BUDGET_PLANNER_SCHEMA_VERSION,
                compiled.compilation_id,
                final_plan.plan_id,
                [item.option_id for item in selected],
                [item.item_id for item in ordered_fixed],
                allocated_total,
                budget_limit,
                hard_headroom_justification,
            ],
        )
        result = BudgetedCinematicEpisode(
            allocation_id=allocation_id,
            schema_version=DYNAMIC_BUDGET_PLANNER_SCHEMA_VERSION,
            editorial_compilation_id=compiled.compilation_id,
            final_plan=final_plan,
            selected_options=selected,
            fixed_costs=ordered_fixed,
            category_totals_usd=category_totals,
            allocated_total_usd=allocated_total,
            budget_limit_usd=budget_limit,
            hard_headroom_used=hard_headroom_used,
            hard_headroom_justification=(
                hard_headroom_justification if hard_headroom_used else None
            ),
        )
        self._validate_result(storyboard, compiled, result)
        return result

    @staticmethod
    def _option_is_eligible(
        assignment: CompiledFrameAssignment,
        option: PricedMediaOption,
    ) -> bool:
        if option.treatment not in assignment.allowed_treatments:
            return False
        if (
            assignment.motion_need is MotionNeed.REQUIRED
            and option.treatment not in MOTION_CAPABLE_TREATMENTS
        ):
            return False
        if (
            option.generated_video_seconds
            > assignment.maximum_generated_video_seconds
        ):
            return False
        return True

    @staticmethod
    def _option_utility(
        assignment: CompiledFrameAssignment,
        option: PricedMediaOption,
    ) -> int:
        weighted_quality = 7 * option.quality_score + 3 * option.reliability_score
        score = assignment.generation_priority * weighted_quality
        if option.treatment is assignment.preferred_treatment:
            score += assignment.generation_priority * 250
        if (
            assignment.motion_need is MotionNeed.OPTIONAL
            and option.treatment in MOTION_CAPABLE_TREATMENTS
        ):
            score += assignment.generation_priority * 40
        return score

    @staticmethod
    def _candidate_better(
        candidate: tuple[int, tuple[str, ...], tuple[PricedMediaOption, ...]],
        existing: tuple[int, tuple[str, ...], tuple[PricedMediaOption, ...]],
    ) -> bool:
        if candidate[0] != existing[0]:
            return candidate[0] > existing[0]
        return candidate[1] < existing[1]

    @staticmethod
    def _category_totals(
        selected: tuple[PricedMediaOption, ...],
        fixed_costs: tuple[FixedProductionCost, ...],
    ) -> tuple[tuple[str, float], ...]:
        totals: dict[str, int] = {}
        for item in selected:
            totals[item.category.value] = totals.get(item.category.value, 0) + int(
                round(item.estimated_cost_usd * 100)
            )
        for item in fixed_costs:
            totals[item.category.value] = totals.get(item.category.value, 0) + int(
                round(item.estimated_cost_usd * 100)
            )
        return tuple(
            (category, round(cents / 100, 2))
            for category, cents in sorted(totals.items())
        )

    @staticmethod
    def _to_cents(value: float) -> int:
        return int(round(value * 100))

    @staticmethod
    def _from_cents(value: int) -> float:
        return round(value / 100, 2)

    def _validate_result(
        self,
        storyboard: Storyboard,
        compiled: CompiledCinematicEpisode,
        result: BudgetedCinematicEpisode,
    ) -> None:
        if result.live_execution_allowed:
            raise CinematicSeriesError("Budget planning cannot enable live execution.")
        if result.editorial_compilation_id != compiled.compilation_id:
            raise CinematicSeriesError("Budget result references another compilation.")
        if len(result.selected_options) != storyboard.frame_count:
            raise CinematicSeriesError("Every frame must have one selected media option.")
        if [item.frame_id for item in result.selected_options] != [
            item.frame_id for item in storyboard.frames
        ]:
            raise CinematicSeriesError("Selected options must preserve frame order.")
        if not self._runtime.validate_plan(storyboard, result.final_plan):
            raise CinematicSeriesError("Final budgeted cinematic plan is invalid.")
        if result.allocated_total_usd > result.budget_limit_usd:
            raise CinematicSeriesError("Budget result exceeds its selected limit.")
        if result.allocated_total_usd > compiled.budget.hard_total_usd:
            raise CinematicSeriesError("Budget result exceeds the hard episode cap.")
        if (
            result.final_plan.generated_video_seconds
            > compiled.policy.generated_video_hard_limit_seconds
        ):
            raise CinematicSeriesError("Final plan exceeds the video hard limit.")
