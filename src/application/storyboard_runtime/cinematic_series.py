"""Budget-aware cinematic-series overlay for the Siraj storyboard runtime.

The layer is deterministic and offline. It validates narrative continuity,
evidence posture, spectacle contrast, and media limits. It does not contact
Runware or any other external provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from src.application.documentary_intelligence import deterministic_id

from .models import Storyboard


TARGET_MEDIA_BUDGET_USD = 30.0
HARD_MEDIA_BUDGET_USD = 35.0
GENERATED_VIDEO_HARD_LIMIT_SECONDS = 25 * 60
GENERATED_VIDEO_SECONDS_POLICY = "BUDGET_DRIVEN_NO_FIXED_TARGET"
MAXIMUM_PEAK_BEATS = 2
RUNWARE_EXECUTION_STATUS = "BLOCKED_PENDING_MANUAL_PROVIDER_TEST"


class CinematicSeriesError(ValueError):
    """Raised when a cinematic-series contract is structurally invalid."""


class NarrativeFunction(StrEnum):
    COLD_OPEN = "cold_open"
    CENTRAL_QUESTION = "central_question"
    ORIENTATION = "orientation"
    DISCOVERY = "discovery"
    ESCALATION = "escalation"
    REVERSAL = "reversal"
    CLIMAX = "climax"
    CONSEQUENCE = "consequence"
    NEXT_EPISODE_PROMISE = "next_episode_promise"


class EvidenceMode(StrEnum):
    DOCUMENTARY_EVIDENCE = "documentary_evidence"
    EVIDENCE_BASED_RECONSTRUCTION = "evidence_based_reconstruction"
    PLAUSIBLE_RECONSTRUCTION = "plausible_reconstruction"
    SYMBOLIC_VISUALIZATION = "symbolic_visualization"
    ATMOSPHERIC_TRANSITION = "atmospheric_transition"


class SpectacleLevel(StrEnum):
    QUIET = "quiet"
    CONTROLLED = "controlled"
    ELEVATED = "elevated"
    PEAK = "peak"


@dataclass(frozen=True, slots=True)
class EpisodeSeriesContract:
    series_title: str
    season_title: str
    episode_id: str
    season_question: str
    central_question: str
    emotional_promise: str
    knowledge_promise: str
    next_episode_question: str
    unresolved_thread_from_previous: str | None = None
    target_media_budget_usd: float = TARGET_MEDIA_BUDGET_USD
    hard_media_budget_usd: float = HARD_MEDIA_BUDGET_USD
    generated_video_hard_limit_seconds: int = GENERATED_VIDEO_HARD_LIMIT_SECONDS

    def validate(self) -> None:
        required = (
            self.series_title,
            self.season_title,
            self.episode_id,
            self.season_question,
            self.central_question,
            self.emotional_promise,
            self.knowledge_promise,
            self.next_episode_question,
        )
        if any(not value.strip() for value in required):
            raise CinematicSeriesError("Series contract fields must not be blank.")
        if self.central_question.strip() == self.next_episode_question.strip():
            raise CinematicSeriesError(
                "The next-episode question must advance the series."
            )
        if self.target_media_budget_usd != TARGET_MEDIA_BUDGET_USD:
            raise CinematicSeriesError("The generated-video target budget is fixed at USD 30.")
        if self.hard_media_budget_usd != HARD_MEDIA_BUDGET_USD:
            raise CinematicSeriesError("The generated-video hard cap is fixed at USD 35.")
        if (
            self.generated_video_hard_limit_seconds
            != GENERATED_VIDEO_HARD_LIMIT_SECONDS
        ):
            raise CinematicSeriesError(
                "Generated-video duration has no editorial target; the technical ceiling is the episode duration."
            )


@dataclass(frozen=True, slots=True)
class CinematicFrameDirective:
    frame_id: str
    narrative_function: NarrativeFunction
    evidence_mode: EvidenceMode
    spectacle_level: SpectacleLevel
    planned_seconds: int
    generated_video_seconds: int = 0
    callback_to_frame_id: str | None = None

    def validate(self) -> None:
        if not self.frame_id.strip():
            raise CinematicSeriesError("frame_id must not be blank.")
        if self.planned_seconds <= 0:
            raise CinematicSeriesError("planned_seconds must be positive.")
        if self.generated_video_seconds < 0:
            raise CinematicSeriesError(
                "generated_video_seconds cannot be negative."
            )
        if self.generated_video_seconds > self.planned_seconds:
            raise CinematicSeriesError(
                "Generated-video seconds cannot exceed the frame duration."
            )
        if (
            self.narrative_function is NarrativeFunction.NEXT_EPISODE_PROMISE
            and self.spectacle_level is SpectacleLevel.PEAK
        ):
            raise CinematicSeriesError(
                "The next-episode promise must create anticipation, not a second climax."
            )


@dataclass(frozen=True, slots=True)
class CinematicStoryboardPlan:
    plan_id: str
    storyboard_id: str
    contract: EpisodeSeriesContract
    directives: tuple[CinematicFrameDirective, ...]
    anticipation_score: int
    generated_video_seconds: int
    runware_execution_status: str = RUNWARE_EXECUTION_STATUS
    validation_state: str = "VALID"


class CinematicSeriesRuntime:
    """Build and validate a cinematic overlay for an existing storyboard."""

    def build_plan(
        self,
        storyboard: Storyboard,
        contract: EpisodeSeriesContract,
        directives: Iterable[CinematicFrameDirective],
    ) -> CinematicStoryboardPlan:
        contract.validate()
        ordered = tuple(directives)
        self._validate_storyboard(storyboard)
        self._validate_directives(storyboard, ordered)

        generated_video_seconds = sum(
            item.generated_video_seconds for item in ordered
        )
        anticipation_score = self._anticipation_score(contract, ordered)
        plan_id = deterministic_id(
            "cinematic_storyboard_plan",
            [
                storyboard.storyboard_id,
                contract.episode_id,
                [item.frame_id for item in ordered],
                [item.narrative_function.value for item in ordered],
                generated_video_seconds,
            ],
        )
        return CinematicStoryboardPlan(
            plan_id=plan_id,
            storyboard_id=storyboard.storyboard_id,
            contract=contract,
            directives=ordered,
            anticipation_score=anticipation_score,
            generated_video_seconds=generated_video_seconds,
        )

    def validate_plan(
        self,
        storyboard: Storyboard,
        plan: CinematicStoryboardPlan,
    ) -> bool:
        try:
            if not isinstance(plan, CinematicStoryboardPlan):
                return False
            if plan.storyboard_id != storyboard.storyboard_id:
                return False
            if plan.runware_execution_status != RUNWARE_EXECUTION_STATUS:
                return False
            if plan.validation_state != "VALID":
                return False
            rebuilt = self.build_plan(storyboard, plan.contract, plan.directives)
            return rebuilt == plan
        except (CinematicSeriesError, ValueError, TypeError):
            return False

    @staticmethod
    def _validate_storyboard(storyboard: Storyboard) -> None:
        if not isinstance(storyboard, Storyboard):
            raise CinematicSeriesError("Expected a Storyboard instance.")
        if storyboard.validation_state != "VALID":
            raise CinematicSeriesError("Storyboard must be valid.")
        if storyboard.frame_count != len(storyboard.frames):
            raise CinematicSeriesError("Storyboard frame count is inconsistent.")
        if not storyboard.frames:
            raise CinematicSeriesError("Storyboard must contain frames.")

    @staticmethod
    def _validate_directives(
        storyboard: Storyboard,
        directives: tuple[CinematicFrameDirective, ...],
    ) -> None:
        if len(directives) != storyboard.frame_count:
            raise CinematicSeriesError(
                "Every storyboard frame requires exactly one cinematic directive."
            )
        for item in directives:
            item.validate()

        expected_ids = [frame.frame_id for frame in storyboard.frames]
        observed_ids = [item.frame_id for item in directives]
        if observed_ids != expected_ids:
            raise CinematicSeriesError(
                "Cinematic directives must preserve storyboard frame order."
            )
        if len(set(observed_ids)) != len(observed_ids):
            raise CinematicSeriesError("Duplicate cinematic frame directives.")

        functions = [item.narrative_function for item in directives]
        required = {
            NarrativeFunction.COLD_OPEN,
            NarrativeFunction.CENTRAL_QUESTION,
            NarrativeFunction.CLIMAX,
            NarrativeFunction.NEXT_EPISODE_PROMISE,
        }
        missing = sorted(item.value for item in required.difference(functions))
        if missing:
            raise CinematicSeriesError(f"Missing narrative functions: {missing}")
        if functions[0] is not NarrativeFunction.COLD_OPEN:
            raise CinematicSeriesError("The first frame must be the cold open.")
        if functions[-1] is not NarrativeFunction.NEXT_EPISODE_PROMISE:
            raise CinematicSeriesError(
                "The final frame must be the next-episode promise."
            )
        if functions.index(NarrativeFunction.CLIMAX) >= len(functions) - 1:
            raise CinematicSeriesError(
                "The climax must occur before the next-episode promise."
            )

        peak_count = sum(
            item.spectacle_level is SpectacleLevel.PEAK for item in directives
        )
        if peak_count > MAXIMUM_PEAK_BEATS:
            raise CinematicSeriesError(
                "Too many peak beats; cinematic impact requires contrast."
            )

        generated_seconds = sum(
            item.generated_video_seconds for item in directives
        )
        if generated_seconds > GENERATED_VIDEO_HARD_LIMIT_SECONDS:
            raise CinematicSeriesError(
                "Generated video exceeds the technical episode-duration ceiling."
            )

        frame_by_id = {frame.frame_id: frame for frame in storyboard.frames}
        prior_ids: set[str] = set()
        for item in directives:
            frame = frame_by_id[item.frame_id]
            if (
                item.evidence_mode is EvidenceMode.DOCUMENTARY_EVIDENCE
                and not frame.referenced_evidence_ids
            ):
                raise CinematicSeriesError(
                    "Documentary-evidence directives require referenced evidence."
                )
            if item.callback_to_frame_id is not None:
                if item.callback_to_frame_id not in prior_ids:
                    raise CinematicSeriesError(
                        "Callbacks must reference an earlier storyboard frame."
                    )
            prior_ids.add(item.frame_id)

    @staticmethod
    def _anticipation_score(
        contract: EpisodeSeriesContract,
        directives: tuple[CinematicFrameDirective, ...],
    ) -> int:
        functions = {item.narrative_function for item in directives}
        score = 3  # distinct next-episode question is mandatory
        if contract.unresolved_thread_from_previous:
            score += 2
        if NarrativeFunction.REVERSAL in functions:
            score += 2
        if NarrativeFunction.CONSEQUENCE in functions:
            score += 1
        if any(item.callback_to_frame_id for item in directives):
            score += 2
        return score


def validate_episode_handoff(
    previous: EpisodeSeriesContract,
    current: EpisodeSeriesContract,
) -> None:
    previous.validate()
    current.validate()
    expected = previous.next_episode_question.strip()
    observed = (current.unresolved_thread_from_previous or "").strip()
    if observed != expected:
        raise CinematicSeriesError(
            f"Continuity break between {previous.episode_id} and {current.episode_id}."
        )
