from __future__ import annotations

import unittest

from src.application.storyboard_runtime.cinematic_series import (
    GENERATED_VIDEO_HARD_LIMIT_SECONDS,
    HARD_MEDIA_BUDGET_USD,
    RUNWARE_EXECUTION_STATUS,
    TARGET_MEDIA_BUDGET_USD,
    CinematicFrameDirective,
    CinematicSeriesError,
    CinematicSeriesRuntime,
    EpisodeSeriesContract,
    EvidenceMode,
    NarrativeFunction,
    SpectacleLevel,
    validate_episode_handoff,
)
from src.application.storyboard_runtime.models import Storyboard, StoryboardFrame


def make_storyboard(*, evidence: bool = True) -> Storyboard:
    frames = [
        StoryboardFrame(
            frame_id=f"frame-{index}",
            scene_id=f"scene-{index}",
            frame_purpose=f"purpose-{index}",
            referenced_evidence_ids=[f"evidence-{index}"] if evidence else [],
            position=index,
        )
        for index in range(7)
    ]
    return Storyboard(
        storyboard_id="storyboard-001",
        scene_plan_id="scene-plan-001",
        frames=frames,
        frame_count=len(frames),
    )


def make_contract(
    *,
    episode_id: str = "episode-001",
    unresolved: str | None = None,
    next_question: str = "What followed the first human generation?",
) -> EpisodeSeriesContract:
    return EpisodeSeriesContract(
        series_title="Siraj",
        season_title="Beginnings",
        episode_id=episode_id,
        season_question="How did the human story begin?",
        central_question="What can the surviving evidence establish?",
        emotional_promise="Origin, loss, and consequence without melodrama.",
        knowledge_promise="Separate evidence from later reconstruction.",
        unresolved_thread_from_previous=unresolved,
        next_episode_question=next_question,
    )


def make_directives() -> tuple[CinematicFrameDirective, ...]:
    return (
        CinematicFrameDirective(
            "frame-0",
            NarrativeFunction.COLD_OPEN,
            EvidenceMode.ATMOSPHERIC_TRANSITION,
            SpectacleLevel.CONTROLLED,
            45,
            8,
        ),
        CinematicFrameDirective(
            "frame-1",
            NarrativeFunction.CENTRAL_QUESTION,
            EvidenceMode.DOCUMENTARY_EVIDENCE,
            SpectacleLevel.QUIET,
            70,
        ),
        CinematicFrameDirective(
            "frame-2",
            NarrativeFunction.DISCOVERY,
            EvidenceMode.EVIDENCE_BASED_RECONSTRUCTION,
            SpectacleLevel.CONTROLLED,
            360,
            30,
        ),
        CinematicFrameDirective(
            "frame-3",
            NarrativeFunction.REVERSAL,
            EvidenceMode.DOCUMENTARY_EVIDENCE,
            SpectacleLevel.ELEVATED,
            210,
            12,
        ),
        CinematicFrameDirective(
            "frame-4",
            NarrativeFunction.CLIMAX,
            EvidenceMode.EVIDENCE_BASED_RECONSTRUCTION,
            SpectacleLevel.PEAK,
            180,
            45,
        ),
        CinematicFrameDirective(
            "frame-5",
            NarrativeFunction.CONSEQUENCE,
            EvidenceMode.PLAUSIBLE_RECONSTRUCTION,
            SpectacleLevel.CONTROLLED,
            160,
            18,
        ),
        CinematicFrameDirective(
            "frame-6",
            NarrativeFunction.NEXT_EPISODE_PROMISE,
            EvidenceMode.ATMOSPHERIC_TRANSITION,
            SpectacleLevel.QUIET,
            45,
            6,
            "frame-0",
        ),
    )


class CinematicSeriesRuntimeTests(unittest.TestCase):
    def test_builds_valid_budgeted_cinematic_overlay(self) -> None:
        runtime = CinematicSeriesRuntime()
        storyboard = make_storyboard()
        plan = runtime.build_plan(storyboard, make_contract(), make_directives())
        self.assertTrue(runtime.validate_plan(storyboard, plan))
        self.assertEqual(plan.contract.target_media_budget_usd, 40.0)
        self.assertEqual(plan.contract.hard_media_budget_usd, 45.0)
        self.assertLessEqual(plan.generated_video_seconds, 300)
        self.assertEqual(plan.runware_execution_status, RUNWARE_EXECUTION_STATUS)
        self.assertGreaterEqual(plan.anticipation_score, 8)

    def test_budget_constants_are_fixed(self) -> None:
        self.assertEqual(TARGET_MEDIA_BUDGET_USD, 40.0)
        self.assertEqual(HARD_MEDIA_BUDGET_USD, 45.0)
        self.assertEqual(GENERATED_VIDEO_HARD_LIMIT_SECONDS, 300)

    def test_rejects_missing_cold_open(self) -> None:
        directives = list(make_directives())
        first = directives[0]
        directives[0] = CinematicFrameDirective(
            first.frame_id,
            NarrativeFunction.ORIENTATION,
            first.evidence_mode,
            first.spectacle_level,
            first.planned_seconds,
            first.generated_video_seconds,
        )
        with self.assertRaises(CinematicSeriesError):
            CinematicSeriesRuntime().build_plan(
                make_storyboard(), make_contract(), directives
            )

    def test_rejects_constant_peak_spectacle(self) -> None:
        directives = tuple(
            CinematicFrameDirective(
                item.frame_id,
                item.narrative_function,
                item.evidence_mode,
                SpectacleLevel.PEAK,
                item.planned_seconds,
                item.generated_video_seconds,
                item.callback_to_frame_id,
            )
            for item in make_directives()
        )
        with self.assertRaises(CinematicSeriesError):
            CinematicSeriesRuntime().build_plan(
                make_storyboard(), make_contract(), directives
            )

    def test_rejects_video_over_five_minutes(self) -> None:
        directives = list(make_directives())
        item = directives[2]
        directives[2] = CinematicFrameDirective(
            item.frame_id,
            item.narrative_function,
            item.evidence_mode,
            item.spectacle_level,
            400,
            301,
        )
        with self.assertRaises(CinematicSeriesError):
            CinematicSeriesRuntime().build_plan(
                make_storyboard(), make_contract(), directives
            )

    def test_documentary_evidence_requires_evidence_refs(self) -> None:
        with self.assertRaises(CinematicSeriesError):
            CinematicSeriesRuntime().build_plan(
                make_storyboard(evidence=False),
                make_contract(),
                make_directives(),
            )

    def test_directives_must_cover_storyboard_in_order(self) -> None:
        directives = list(make_directives())
        directives[1], directives[2] = directives[2], directives[1]
        with self.assertRaises(CinematicSeriesError):
            CinematicSeriesRuntime().build_plan(
                make_storyboard(), make_contract(), directives
            )

    def test_episode_handoff_requires_exact_question_continuity(self) -> None:
        previous = make_contract(next_question="Who inherited the first conflict?")
        current = make_contract(
            episode_id="episode-002",
            unresolved="Who inherited the first conflict?",
            next_question="How did early communities remember catastrophe?",
        )
        validate_episode_handoff(previous, current)

    def test_episode_handoff_rejects_unrelated_opening(self) -> None:
        previous = make_contract(next_question="Who inherited the first conflict?")
        current = make_contract(
            episode_id="episode-002",
            unresolved="An unrelated opening question.",
        )
        with self.assertRaises(CinematicSeriesError):
            validate_episode_handoff(previous, current)


if __name__ == "__main__":
    unittest.main()
