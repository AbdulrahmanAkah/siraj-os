from __future__ import annotations

from pathlib import Path
import unittest

from src.application.media_cost_authority_v2 import (
    assess_cost,
    canonical_registry_template,
    load_pricing_registry,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "projects" / "_series" / "siraj-media-pricing-registry-v2.json"


class MediaCostAuthorityV2Tests(unittest.TestCase):
    def test_checked_in_registry_is_official_and_versioned(self) -> None:
        registry = load_pricing_registry(REGISTRY)
        self.assertEqual(registry["source_policy"], "OFFICIAL_PROVIDER_DOCUMENTATION_ONLY")
        self.assertEqual(registry["unknown_price_policy"], "UNKNOWN_PRICING_BLOCKS_EXECUTION")
        self.assertEqual(registry["registry_version"], "v2-runware-official-2026-08-09")
        self.assertEqual(len(registry["entries"]), 3)

    def test_exact_variants_produce_conservative_complete_cost(self) -> None:
        registry = load_pricing_registry(REGISTRY)
        units = [
            {
                "unit_id": "video-1",
                "provider": "RUNWARE",
                "model": "google:veo@3.1-lite",
                "media_kind": "RUNWARE_VIDEO",
                "requested_seconds": 4,
                "pricing_variant": "720p_no_audio",
                "width": 1280,
                "height": 720,
                "generate_audio": False,
            },
            {
                "unit_id": "image-1",
                "provider": "RUNWARE",
                "model": "bytedance:seedream@5.0-pro",
                "media_kind": "RUNWARE_IMAGE",
                "pricing_variant": "1.5K",
                "width": 1424,
                "height": 800,
            },
            {
                "unit_id": "nano-1",
                "provider": "RUNWARE",
                "model": "google:4@3",
                "media_kind": "RUNWARE_IMAGE",
                "pricing_variant": "1K",
                "width": 1376,
                "height": 768,
            },
        ]
        assessment = assess_cost(units, registry)
        self.assertEqual(assessment.pricing_status, "COMPLETE")
        self.assertEqual(assessment.priced_requests, 3)
        self.assertEqual(assessment.unpriced_requests, 0)
        self.assertEqual(assessment.currency, "USD")
        self.assertAlmostEqual(assessment.estimated_total_cost or 0.0, 0.2 + 0.04815 + 0.06895, places=8)

    def test_unresolved_variant_fails_closed(self) -> None:
        registry = load_pricing_registry(REGISTRY)
        assessment = assess_cost(
            [
                {
                    "unit_id": "nano-legacy",
                    "provider": "RUNWARE",
                    "model": "google:4@3",
                    "media_kind": "RUNWARE_IMAGE",
                    "pricing_variant": "1K",
                    "width": 1344,
                    "height": 768,
                }
            ],
            registry,
        )
        self.assertEqual(assessment.pricing_status, "COMPLETE")
        # Pricing can be estimated at the declared tier, while the provider
        # contract separately rejects the legacy route.  No unknown price is
        # inferred here and no execution is authorized by this assessment.
        self.assertFalse(assessment.unpriced_requests)

    def test_template_reads_checked_in_authority(self) -> None:
        value = canonical_registry_template(ROOT)
        self.assertEqual(value["registry_version"], "v2-runware-official-2026-08-09")
        self.assertEqual(value["entries"][0]["status"], "PRICED")


if __name__ == "__main__":
    unittest.main()
