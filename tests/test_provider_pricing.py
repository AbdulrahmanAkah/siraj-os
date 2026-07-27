from __future__ import annotations

import json
import unittest
from dataclasses import replace

from src.application.storyboard_runtime.cinematic_compiler import (
    CinematicSeriesCompiler,
    MediaCategory,
    MediaTreatment,
)
from src.application.storyboard_runtime.cinematic_series import EpisodeSeriesContract
from src.application.storyboard_runtime.models import Storyboard, StoryboardFrame
from src.application.storyboard_runtime.provider_pricing import (
    BillingBasis,
    FrameQuoteSpec,
    ManualProviderTestRecord,
    PreciseDynamicCinematicBudgetPlanner,
    PreciseFixedProductionCost,
    PriceSourceKind,
    ProviderTestStatus,
    VerifiedMediaOptionFactory,
    VerifiedProviderPriceCatalog,
    manual_test_template,
)
from src.application.storyboard_runtime.cinematic_series import CinematicSeriesError


HEX_A = "a" * 64
HEX_B = "b" * 64


def make_storyboard(count: int = 9) -> Storyboard:
    frames = [
        StoryboardFrame(
            frame_id=f"frame-{index}",
            scene_id=f"scene-{index}",
            frame_purpose=f"purpose-{index}",
            referenced_evidence_ids=[f"evidence-{index}"],
            position=index,
        )
        for index in range(count)
    ]
    return Storyboard(
        storyboard_id="storyboard-provider-pricing",
        scene_plan_id="scene-plan-provider-pricing",
        frames=frames,
        frame_count=len(frames),
    )


def make_contract() -> EpisodeSeriesContract:
    return EpisodeSeriesContract(
        series_title="Siraj",
        season_title="Beginnings",
        episode_id="episode-001-adam",
        season_question="How did the human story begin?",
        central_question="What can the evidence establish?",
        emotional_promise="Awe and consequence without fabricated melodrama.",
        knowledge_promise="Separate evidence from reconstruction.",
        next_episode_question="What followed the first human generation?",
    )


def make_record(
    *,
    test_id: str,
    treatment: MediaTreatment,
    category: MediaCategory,
    total: str,
    units: str,
    basis: BillingBasis,
    video_seconds: int = 0,
    status: ProviderTestStatus = ProviderTestStatus.PASS,
    quality: int = 80,
    reliability: int = 90,
    provider: str = "RUNWARE",
) -> ManualProviderTestRecord:
    return ManualProviderTestRecord(
        test_id=test_id,
        provider_id=provider,
        model_id=f"model-{test_id}",
        source_kind=PriceSourceKind.MANUAL_PROVIDER_TEST,
        treatment=treatment,
        category=category,
        billing_basis=basis,
        observed_total_cost_usd=total,
        billed_units=units,
        generated_output_count=int(units) if basis is BillingBasis.PER_OUTPUT else 1,
        generated_video_seconds=video_seconds,
        quality_score=quality,
        reliability_score=reliability,
        latency_ms=2500,
        request_fingerprint_sha256=HEX_A,
        response_fingerprint_sha256=HEX_B,
        tested_at_utc="2026-07-28T00:00:00Z",
        status=status,
    )


class ProviderPricingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storyboard = make_storyboard()
        self.compiled = CinematicSeriesCompiler().compile(
            self.storyboard,
            make_contract(),
        )
        self.still_record = make_record(
            test_id="local-still",
            treatment=MediaTreatment.STILL_LED,
            category=MediaCategory.IMAGE,
            total="0.003125",
            units="1",
            basis=BillingBasis.PER_OUTPUT,
            provider="LOCAL",
            quality=55,
            reliability=100,
        )
        self.video_record = make_record(
            test_id="runware-video",
            treatment=MediaTreatment.GENERATED_VIDEO,
            category=MediaCategory.VIDEO,
            total="0.0625",
            units="5",
            basis=BillingBasis.PER_SECOND,
            video_seconds=5,
            quality=95,
            reliability=90,
        )

    def test_manual_observation_preserves_sub_cent_price(self) -> None:
        self.still_record.validate()
        self.assertEqual(str(self.still_record.unit_price), "0.003125")

    def test_catalog_rejects_failed_test(self) -> None:
        failed = make_record(
            test_id="failed",
            treatment=MediaTreatment.STILL_LED,
            category=MediaCategory.IMAGE,
            total="0",
            units="1",
            basis=BillingBasis.PER_OUTPUT,
            status=ProviderTestStatus.FAIL,
        )
        with self.assertRaises(CinematicSeriesError):
            VerifiedProviderPriceCatalog.build((failed,))

    def test_catalog_is_deterministic_and_offline(self) -> None:
        first = VerifiedProviderPriceCatalog.build(
            (self.video_record, self.still_record)
        )
        second = VerifiedProviderPriceCatalog.build(
            (self.still_record, self.video_record)
        )
        self.assertEqual(first, second)
        manifest = first.to_manifest()
        self.assertFalse(manifest["live_execution_allowed"])
        self.assertNotIn("api_key", first.to_json().lower())

    def test_credentials_are_forbidden(self) -> None:
        record = replace(self.still_record, credentials_recorded=True)
        with self.assertRaises(CinematicSeriesError):
            record.validate()

    def test_per_second_observation_must_match_video_seconds(self) -> None:
        bad = make_record(
            test_id="bad-video",
            treatment=MediaTreatment.GENERATED_VIDEO,
            category=MediaCategory.VIDEO,
            total="0.05",
            units="4",
            basis=BillingBasis.PER_SECOND,
            video_seconds=5,
        )
        with self.assertRaises(CinematicSeriesError):
            bad.validate()

    def test_quote_factory_keeps_six_decimal_cost(self) -> None:
        catalog = VerifiedProviderPriceCatalog.build((self.still_record,))
        option = VerifiedMediaOptionFactory().quote(
            self.compiled,
            catalog,
            (
                FrameQuoteSpec(
                    quote_id="q-1",
                    frame_id="frame-0",
                    provider_test_id="local-still",
                    requested_units="1",
                ),
            ),
        )[0]
        self.assertEqual(option.estimated_cost_usd, "0.003125")
        self.assertEqual(option.cost_micro_usd, 3125)

    def test_per_second_quote_requires_explicit_matching_duration(self) -> None:
        catalog = VerifiedProviderPriceCatalog.build((self.video_record,))
        with self.assertRaises(CinematicSeriesError):
            VerifiedMediaOptionFactory().quote(
                self.compiled,
                catalog,
                (
                    FrameQuoteSpec(
                        quote_id="q-video",
                        frame_id="frame-0",
                        provider_test_id="runware-video",
                        requested_units="10",
                        generated_video_seconds=8,
                    ),
                ),
            )

    def test_quote_rejects_video_over_frame_ceiling(self) -> None:
        catalog = VerifiedProviderPriceCatalog.build((self.video_record,))
        with self.assertRaises(CinematicSeriesError):
            VerifiedMediaOptionFactory().quote(
                self.compiled,
                catalog,
                (
                    FrameQuoteSpec(
                        quote_id="q-video",
                        frame_id="frame-0",
                        provider_test_id="runware-video",
                        requested_units="31",
                        generated_video_seconds=31,
                    ),
                ),
            )

    def _all_still_options(self):
        catalog = VerifiedProviderPriceCatalog.build(
            (self.still_record, self.video_record)
        )
        specs = [
            FrameQuoteSpec(
                quote_id=f"still-{frame.frame_id}",
                frame_id=frame.frame_id,
                provider_test_id="local-still",
                requested_units="1",
            )
            for frame in self.storyboard.frames
        ]
        return catalog, list(
            VerifiedMediaOptionFactory().quote(self.compiled, catalog, specs)
        )

    def test_precise_planner_selects_complete_mix(self) -> None:
        catalog, options = self._all_still_options()
        climax = next(
            assignment
            for assignment, directive in zip(
                self.compiled.assignments,
                self.compiled.plan.directives,
                strict=True,
            )
            if directive.narrative_function.value == "climax"
        )
        options.extend(
            VerifiedMediaOptionFactory().quote(
                self.compiled,
                catalog,
                (
                    FrameQuoteSpec(
                        quote_id="video-climax",
                        frame_id=climax.frame_id,
                        provider_test_id="runware-video",
                        requested_units="20",
                        generated_video_seconds=20,
                    ),
                ),
            )
        )
        result = PreciseDynamicCinematicBudgetPlanner().plan(
            self.storyboard,
            self.compiled,
            options,
        )
        self.assertEqual(len(result.selected_options), self.storyboard.frame_count)
        self.assertLess(float(result.allocated_total_usd), 40.0)
        self.assertEqual(result.final_plan.generated_video_seconds, 20)
        self.assertFalse(result.live_execution_allowed)

    def test_precise_planner_accounts_for_fixed_costs_exactly(self) -> None:
        _, options = self._all_still_options()
        fixed = PreciseFixedProductionCost(
            item_id="narration",
            category=MediaCategory.AUDIO,
            estimated_cost_usd="1.234567",
            description="Observed narration production cost.",
            price_source_id="manual-audio-observation",
        )
        result = PreciseDynamicCinematicBudgetPlanner().plan(
            self.storyboard,
            self.compiled,
            options,
            fixed_costs=(fixed,),
        )
        expected = 1.234567 + 9 * 0.003125
        self.assertAlmostEqual(float(result.allocated_total_usd), expected, places=6)
        self.assertEqual(dict(result.category_totals_usd)["audio"], "1.234567")

    def test_hard_headroom_requires_justification(self) -> None:
        _, options = self._all_still_options()
        with self.assertRaises(CinematicSeriesError):
            PreciseDynamicCinematicBudgetPlanner().plan(
                self.storyboard,
                self.compiled,
                options,
                allow_hard_headroom=True,
            )

    def test_every_frame_requires_an_explicit_option(self) -> None:
        catalog, options = self._all_still_options()
        del catalog
        with self.assertRaises(CinematicSeriesError):
            PreciseDynamicCinematicBudgetPlanner().plan(
                self.storyboard,
                self.compiled,
                options[:-1],
            )

    def test_image_only_catalog_cannot_create_video_quote(self) -> None:
        catalog = VerifiedProviderPriceCatalog.build((self.still_record,))
        with self.assertRaises(CinematicSeriesError):
            VerifiedMediaOptionFactory().quote(
                self.compiled,
                catalog,
                (
                    FrameQuoteSpec(
                        quote_id="missing-video-source",
                        frame_id="frame-0",
                        provider_test_id="runware-video",
                        requested_units="5",
                        generated_video_seconds=5,
                    ),
                ),
            )

    def test_template_is_non_executable_and_contains_no_secret(self) -> None:
        template = manual_test_template()
        payload = json.dumps(template, sort_keys=True)
        self.assertFalse(template["live_execution_authorized"])
        self.assertFalse(template["credentials_recorded"])
        self.assertNotIn("api_key", payload.lower())


if __name__ == "__main__":
    unittest.main()
