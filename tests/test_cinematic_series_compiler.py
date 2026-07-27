from __future__ import annotations

import json
import unittest

from src.application.storyboard_runtime.cinematic_compiler import (
    BUDGET_ALLOCATION_STATUS,
    CINEMATIC_COMPILER_SCHEMA_VERSION,
    DEFAULT_EPISODE_SECONDS,
    DYNAMIC_BUDGET_PLANNER_SCHEMA_VERSION,
    MAX_EPISODE_SECONDS,
    MIN_EPISODE_SECONDS,
    CinematicBudgetEnvelope,
    CinematicBudgetGuardrails,
    CinematicCompilationPolicy,
    CinematicSeriesCompiler,
    DynamicCinematicBudgetPlanner,
    FixedProductionCost,
    MediaCategory,
    MediaTreatment,
    MotionNeed,
    PricedMediaOption,
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
        evidence = [] if missing_evidence_index == index else [f"evidence-{index}"]
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


def make_priced_options(compiled, *, premium_video_cost: float = 6.0):
    options = []
    for assignment in compiled.assignments:
        options.append(
            PricedMediaOption(
                option_id=f"{assignment.frame_id}-still",
                frame_id=assignment.frame_id,
                treatment=(
                    MediaTreatment.EVIDENCE_LED
                    if MediaTreatment.EVIDENCE_LED in assignment.allowed_treatments
                    else MediaTreatment.STILL_LED
                ),
                category=MediaCategory.IMAGE,
                estimated_cost_usd=1.0,
                quality_score=70,
                reliability_score=95,
            )
        )
        if MediaTreatment.GENERATED_VIDEO in assignment.allowed_treatments:
            options.append(
                PricedMediaOption(
                    option_id=f"{assignment.frame_id}-video",
                    frame_id=assignment.frame_id,
                    treatment=MediaTreatment.GENERATED_VIDEO,
                    category=MediaCategory.VIDEO,
                    estimated_cost_usd=premium_video_cost,
                    quality_score=97,
                    reliability_score=85,
                    generated_video_seconds=min(
                        10, assignment.maximum_generated_video_seconds
                    ),
                    provider_id="RUNWARE_TEST_FIXTURE",
                    model_id="video-model-fixture",
                    price_source_id="manual-test-fixture",
                )
            )
        if MediaTreatment.LOCAL_ANIMATION in assignment.allowed_treatments:
            options.append(
                PricedMediaOption(
                    option_id=f"{assignment.frame_id}-local",
                    frame_id=assignment.frame_id,
                    treatment=MediaTreatment.LOCAL_ANIMATION,
                    category=MediaCategory.LOCAL_ANIMATION,
                    estimated_cost_usd=2.0,
                    quality_score=82,
                    reliability_score=98,
                )
            )
    return tuple(options)


class CinematicSeriesCompilerTests(unittest.TestCase):
    def test_compiles_deterministic_twenty_two_minute_editorial_blueprint(self):
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
        self.assertEqual(first.plan.generated_video_seconds, 0)
        self.assertEqual(first.budget_allocation_status, BUDGET_ALLOCATION_STATUS)
        self.assertEqual(first.plan.runware_execution_status, RUNWARE_EXECUTION_STATUS)
        self.assertFalse(first.live_execution_allowed)

    def test_budget_contract_contains_only_forty_and_forty_five_guardrails(self):
        budget = CinematicBudgetGuardrails()
        budget.validate()
        self.assertEqual(budget.target_total_usd, 40.0)
        self.assertEqual(budget.hard_total_usd, 45.0)
        self.assertIs(CinematicBudgetEnvelope, CinematicBudgetGuardrails)
        self.assertFalse(hasattr(budget, "image_reserve_usd"))
        self.assertFalse(hasattr(budget, "video_reserve_usd"))
        self.assertFalse(hasattr(budget, "audio_reserve_usd"))
        self.assertFalse(hasattr(budget, "retry_reserve_usd"))

    def test_manifest_defers_category_and_video_allocation(self):
        compiled = CinematicSeriesCompiler().compile(
            make_storyboard(), make_contract()
        )
        payload = json.loads(compiled.to_json())
        self.assertEqual(
            payload["dynamic_budget_allocation"]["status"],
            BUDGET_ALLOCATION_STATUS,
        )
        self.assertIsNone(
            payload["dynamic_budget_allocation"]["category_totals_usd"]
        )
        self.assertIsNone(
            payload["dynamic_budget_allocation"]["allocated_total_usd"]
        )
        self.assertNotIn("budget_envelope_usd", payload)
        self.assertNotIn("image_reserve", payload["budget_guardrails_usd"])
        self.assertEqual(payload["duration"]["generated_video_planned_seconds"], 0)

    def test_narrative_arc_has_required_order_and_single_peak(self):
        compiled = CinematicSeriesCompiler().compile(
            make_storyboard(), make_contract()
        )
        functions = [item.narrative_function for item in compiled.plan.directives]
        levels = [item.spectacle_level for item in compiled.plan.directives]
        self.assertEqual(functions[0], NarrativeFunction.COLD_OPEN)
        self.assertEqual(functions[1], NarrativeFunction.CENTRAL_QUESTION)
        self.assertEqual(functions[-1], NarrativeFunction.NEXT_EPISODE_PROMISE)
        self.assertIn(NarrativeFunction.REVERSAL, functions)
        self.assertIn(NarrativeFunction.CLIMAX, functions)
        self.assertEqual(levels.count(SpectacleLevel.PEAK), 1)

    def test_assignments_express_preferences_not_spending_decisions(self):
        compiled = CinematicSeriesCompiler().compile(
            make_storyboard(), make_contract()
        )
        climax_index = next(
            index
            for index, directive in enumerate(compiled.plan.directives)
            if directive.narrative_function is NarrativeFunction.CLIMAX
        )
        assignment = compiled.assignments[climax_index]
        self.assertEqual(assignment.motion_need, MotionNeed.OPTIONAL)
        self.assertEqual(
            assignment.preferred_treatment, MediaTreatment.GENERATED_VIDEO
        )
        self.assertIn(MediaTreatment.LOCAL_ANIMATION, assignment.allowed_treatments)
        self.assertIn(MediaTreatment.STILL_LED, assignment.allowed_treatments)
        self.assertGreater(assignment.maximum_generated_video_seconds, 0)

    def test_closing_frame_calls_back_to_opening_frame(self):
        compiled = CinematicSeriesCompiler().compile(
            make_storyboard(), make_contract()
        )
        self.assertEqual(
            compiled.plan.directives[-1].callback_to_frame_id,
            compiled.plan.directives[0].frame_id,
        )

    def test_missing_evidence_falls_back_to_symbolic_visualization(self):
        storyboard = make_storyboard(missing_evidence_index=2)
        compiled = CinematicSeriesCompiler().compile(storyboard, make_contract())
        self.assertEqual(
            compiled.plan.directives[2].evidence_mode,
            EvidenceMode.SYMBOLIC_VISUALIZATION,
        )

    def test_dynamic_planner_selects_mix_under_forty(self):
        storyboard = make_storyboard()
        compiled = CinematicSeriesCompiler().compile(storyboard, make_contract())
        planned = DynamicCinematicBudgetPlanner().plan(
            storyboard,
            compiled,
            make_priced_options(compiled),
            fixed_costs=(
                FixedProductionCost(
                    "audio-package",
                    MediaCategory.AUDIO,
                    2.0,
                    "Narration, music, and final mix fixture.",
                ),
            ),
        )
        self.assertEqual(
            planned.schema_version, DYNAMIC_BUDGET_PLANNER_SCHEMA_VERSION
        )
        self.assertLessEqual(planned.allocated_total_usd, 40.0)
        self.assertFalse(planned.hard_headroom_used)
        self.assertFalse(planned.live_execution_allowed)
        self.assertEqual(len(planned.selected_options), storyboard.frame_count)
        self.assertIn("audio", dict(planned.category_totals_usd))
        self.assertGreater(planned.final_plan.generated_video_seconds, 0)
        self.assertLessEqual(planned.final_plan.generated_video_seconds, 300)

    def test_distribution_changes_when_video_price_changes(self):
        storyboard = make_storyboard()
        compiled = CinematicSeriesCompiler().compile(storyboard, make_contract())
        planner = DynamicCinematicBudgetPlanner()
        affordable = planner.plan(
            storyboard,
            compiled,
            make_priced_options(compiled, premium_video_cost=3.0),
        )
        expensive = planner.plan(
            storyboard,
            compiled,
            make_priced_options(compiled, premium_video_cost=20.0),
        )
        affordable_video_count = sum(
            item.category is MediaCategory.VIDEO
            for item in affordable.selected_options
        )
        expensive_video_count = sum(
            item.category is MediaCategory.VIDEO
            for item in expensive.selected_options
        )
        self.assertGreater(affordable_video_count, expensive_video_count)
        self.assertNotEqual(
            dict(affordable.category_totals_usd),
            dict(expensive.category_totals_usd),
        )

    def test_hard_headroom_requires_explicit_justification(self):
        storyboard = make_storyboard()
        compiled = CinematicSeriesCompiler().compile(storyboard, make_contract())
        with self.assertRaises(CinematicSeriesError):
            DynamicCinematicBudgetPlanner().plan(
                storyboard,
                compiled,
                make_priced_options(compiled),
                allow_hard_headroom=True,
            )

    def test_planner_rejects_plan_above_hard_cap(self):
        storyboard = make_storyboard()
        compiled = CinematicSeriesCompiler().compile(storyboard, make_contract())
        only_expensive = []
        for assignment in compiled.assignments:
            treatment = assignment.allowed_treatments[0]
            only_expensive.append(
                PricedMediaOption(
                    option_id=f"{assignment.frame_id}-only",
                    frame_id=assignment.frame_id,
                    treatment=treatment,
                    category=MediaCategory.IMAGE,
                    estimated_cost_usd=6.0,
                    quality_score=90,
                    reliability_score=90,
                )
            )
        with self.assertRaises(CinematicSeriesError):
            DynamicCinematicBudgetPlanner().plan(
                storyboard,
                compiled,
                only_expensive,
                allow_hard_headroom=True,
                hard_headroom_justification="Exceptional episode requirement.",
            )

    def test_policy_rejects_episode_outside_eighteen_to_twenty_five_minutes(self):
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

    def test_policy_rejects_changed_video_hard_limit(self):
        policy = CinematicCompilationPolicy(
            generated_video_hard_limit_seconds=301
        )
        with self.assertRaises(CinematicSeriesError):
            policy.validate()

    def test_frame_order_is_preserved_for_large_storyboard(self):
        storyboard = make_storyboard(frame_count=20)
        compiled = CinematicSeriesCompiler().compile(storyboard, make_contract())
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
