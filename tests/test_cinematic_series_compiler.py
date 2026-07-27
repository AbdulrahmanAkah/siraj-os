from __future__ import annotations

import json
import unittest

from src.application.storyboard_runtime.cinematic_compiler import (
    CINEMATIC_COMPILER_SCHEMA_VERSION,
    DEFAULT_EPISODE_SECONDS,
    DEFAULT_GENERATED_VIDEO_TARGET_SECONDS,
    MAX_EPISODE_SECONDS,
    MIN_EPISODE_SECONDS,
    CinematicBudgetEnvelope,
    CinematicCompilationPolicy,
    CinematicSeriesCompiler,
    MediaTreatment,
)
from src.application.storyboard_runtime.cinematic_series import (
    CinematicSeriesError,
    EpisodeSeriesContract,
    EvidenceMode,
    NarrativeFunction,
    RUNWARE_EXECUTION_STATUS,
    SpectacleLevel,
)
from src.application.storyboard_runtime.models import Storyboard, StoryboardFrame


def make_storyboard(
    frame_count: int = 9,
    *,
    missing_evidence_index: int | None = None,
) -> Storyboard:
    frames = []
    for index in range(frame_count):
        evidence = (
            []
            if missing_evidence_index == index
            else [f"evidence-{index}"]
        )
        frames.append(
            StoryboardFrame(
                frame_id=f"frame-{index}",
                scene_id=f"scene-{index}",
                frame_purpose=f"purpose-{index}",
                referenced_evidence_ids=evidence,
                position=index,
            )
        )
    return Storyboard(
        storyboard_id="storyboard-001",
        scene_plan_id="scene-plan-001",
        frames=frames,
        frame_count=len(frames),
    )


def make_contract() -> EpisodeSeriesContract:
    return EpisodeSeriesContract(
        series_title="Siraj",
        season_title="Beginnings",
        episode_id="episode-001-adam",
        season_question="How did the human story begin?",
        central_question="What can the surviving evidence establish?",
        emotional_promise="Origin, loss, and consequence without melodrama.",
        knowledge_promise="Separate evidence from later reconstruction.",
        next_episode_question="What followed the first human generation?",
    )


class CinematicSeriesCompilerTests(unittest.TestCase):
    def test_compiles_deterministic_twenty_two_minute_episode(self) -> None:
        storyboard = make_storyboard()
        compiler = CinematicSeriesCompiler()
        first = compiler.compile(storyboard, make_contract())
        second = compiler.compile(storyboard, make_contract())

        self.assertEqual(first, second)
        self.assertTrue(compiler.validate_compilation(storyboard, first))
        self.assertEqual(first.schema_version, CINEMATIC_COMPILER_SCHEMA_VERSION)
        self.assertEqual(
            sum(item.planned_seconds for item in first.plan.directives),
            DEFAULT_EPISODE_SECONDS,
        )
        self.assertEqual(
            first.plan.generated_video_seconds,
            DEFAULT_GENERATED_VIDEO_TARGET_SECONDS,
        )
        self.assertEqual(
            first.plan.runware_execution_status,
            RUNWARE_EXECUTION_STATUS,
        )
        self.assertFalse(first.live_execution_allowed)
        self.assertGreaterEqual(first.plan.anticipation_score, 8)

    def test_budget_envelope_is_exactly_forty_and_forty_five(self) -> None:
        budget = CinematicBudgetEnvelope()
        budget.validate()
        self.assertEqual(budget.target_total_usd, 40.0)
        self.assertEqual(budget.hard_total_usd, 45.0)

    def test_narrative_arc_has_required_order_and_single_peak(self) -> None:
        compiled = CinematicSeriesCompiler().compile(
            make_storyboard(),
            make_contract(),
        )
        functions = [
            item.narrative_function for item in compiled.plan.directives
        ]
        levels = [
            item.spectacle_level for item in compiled.plan.directives
        ]
        self.assertEqual(functions[0], NarrativeFunction.COLD_OPEN)
        self.assertEqual(functions[1], NarrativeFunction.CENTRAL_QUESTION)
        self.assertEqual(
            functions[-1],
            NarrativeFunction.NEXT_EPISODE_PROMISE,
        )
        self.assertIn(NarrativeFunction.REVERSAL, functions)
        self.assertIn(NarrativeFunction.CLIMAX, functions)
        self.assertEqual(levels.count(SpectacleLevel.PEAK), 1)
        self.assertLess(
            functions.index(NarrativeFunction.CLIMAX),
            functions.index(NarrativeFunction.NEXT_EPISODE_PROMISE),
        )

    def test_closing_frame_calls_back_to_opening_frame(self) -> None:
        compiled = CinematicSeriesCompiler().compile(
            make_storyboard(),
            make_contract(),
        )
        self.assertEqual(
            compiled.plan.directives[-1].callback_to_frame_id,
            compiled.plan.directives[0].frame_id,
        )

    def test_missing_evidence_falls_back_to_symbolic_visualization(self) -> None:
        storyboard = make_storyboard(missing_evidence_index=2)
        compiled = CinematicSeriesCompiler().compile(
            storyboard,
            make_contract(),
        )
        self.assertEqual(
            compiled.plan.directives[2].evidence_mode,
            EvidenceMode.SYMBOLIC_VISUALIZATION,
        )

    def test_generated_video_is_hybrid_not_full_episode(self) -> None:
        compiled = CinematicSeriesCompiler().compile(
            make_storyboard(),
            make_contract(),
        )
        for directive, assignment in zip(
            compiled.plan.directives,
            compiled.assignments,
            strict=True,
        ):
            if directive.generated_video_seconds:
                self.assertEqual(
                    assignment.media_treatment,
                    MediaTreatment.HYBRID_SEQUENCE,
                )
                self.assertLess(
                    directive.generated_video_seconds,
                    directive.planned_seconds,
                )

    def test_manifest_is_stable_json_and_contains_no_live_price_claim(self) -> None:
        compiled = CinematicSeriesCompiler().compile(
            make_storyboard(),
            make_contract(),
        )
        payload = json.loads(compiled.to_json())
        self.assertEqual(
            payload["schema_version"],
            CINEMATIC_COMPILER_SCHEMA_VERSION,
        )
        self.assertEqual(
            payload["provider_price_estimate_status"],
            "UNAVAILABLE_PENDING_MANUAL_PROVIDER_TEST",
        )
        self.assertFalse(payload["live_execution_allowed"])
        self.assertEqual(
            payload["budget_envelope_usd"]["target_total"],
            40.0,
        )
        self.assertEqual(
            payload["budget_envelope_usd"]["hard_total"],
            45.0,
        )

    def test_rejects_storyboard_with_fewer_than_seven_frames(self) -> None:
        with self.assertRaises(CinematicSeriesError):
            CinematicSeriesCompiler().compile(
                make_storyboard(frame_count=6),
                make_contract(),
            )

    def test_policy_rejects_episode_outside_eighteen_to_twenty_five_minutes(self) -> None:
        low = CinematicCompilationPolicy(
            target_episode_seconds=MIN_EPISODE_SECONDS - 1
        )
        high = CinematicCompilationPolicy(
            target_episode_seconds=MAX_EPISODE_SECONDS + 1
        )
        with self.assertRaises(CinematicSeriesError):
            low.validate()
        with self.assertRaises(CinematicSeriesError):
            high.validate()

    def test_policy_rejects_generated_video_above_five_minutes(self) -> None:
        policy = CinematicCompilationPolicy(
            generated_video_target_seconds=301
        )
        with self.assertRaises(CinematicSeriesError):
            policy.validate()

    def test_frame_order_is_preserved_for_large_storyboard(self) -> None:
        storyboard = make_storyboard(frame_count=20)
        compiled = CinematicSeriesCompiler().compile(
            storyboard,
            make_contract(),
        )
        self.assertEqual(
            [item.frame_id for item in compiled.plan.directives],
            [item.frame_id for item in storyboard.frames],
        )
        self.assertEqual(
            [item.frame_id for item in compiled.assignments],
            [item.frame_id for item in storyboard.frames],
        )


if __name__ == "__main__":
    unittest.main()
