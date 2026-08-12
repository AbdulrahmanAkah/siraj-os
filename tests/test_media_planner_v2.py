from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.artifact_provenance_v1 import canonical_sha256
from src.application.media_cost_authority_v2 import (
    CostAuthorityError,
    assess_cost,
    load_pricing_registry,
    require_complete_pricing_for_provider_execution,
)
from src.application.provider_model_contracts import ProviderModelContractError, validate_runware_task
from src.application.runware_image_model_routing_v1 import route_image_shot
from src.application.siraj_cinematic_media_mix_policy_v2 import (
    MediaMixPolicyError,
    POLICY,
    coverage_diagnostics,
    validate_no_reuse_or_loop,
    validate_true_video_coverage,
    true_video_seconds_from_units,
)
from src.application.siraj_media_planner_v2 import (
    build_media_planner_v2_proposal,
    classify_shot,
)


REPO = Path(__file__).resolve().parents[1]
PLAN = REPO / "projects/episode-002-adam-temptation-fall-repentance/preproduction/siraj-promoted-provider-ready-prompt-plan-v1.json"
REGISTRY = REPO / "projects/_series/siraj-media-pricing-registry-v2.json"
EPISODE_DURATION = 623.584


@pytest.mark.parametrize(
    ("percent", "status"),
    [
        (49.99, "FAIL_UNDER_VIDEO_FLOOR"),
        (50.0, "PASS"),
        (60.0, "PASS"),
        (75.0, "PASS"),
        (75.01, "FAIL_OVER_VIDEO_CEILING"),
    ],
)
def test_hard_true_video_coverage_range(percent: float, status: str) -> None:
    result = validate_true_video_coverage(100.0, percent)
    assert result.status == status


def test_policy_is_central_and_old_two_thirds_is_inactive() -> None:
    assert POLICY.policy_id == "SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2"
    assert POLICY.min_true_video_fraction == 0.50
    assert POLICY.max_true_video_fraction == 0.75
    assert POLICY.old_two_thirds_policy_active is False


def _load_items() -> list[dict[str, object]]:
    value = json.loads(PLAN.read_text(encoding="utf-8-sig"))
    return list(value["items"])


def test_planner_proposal_is_range_valid_and_structurally_immutable() -> None:
    items = _load_items()
    proposal = build_media_planner_v2_proposal(
        items,
        episode_id="episode-002-adam-temptation-fall-repentance",
        episode_duration_seconds=EPISODE_DURATION,
        structural_fingerprint="94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42",
        creative_overlay_sha256="254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509",
    )
    coverage = proposal["coverage"]
    assert coverage["coverage_validation"]["status"] == "PASS"
    assert 50.0 <= coverage["true_generated_video_timeline_percent"] <= 75.0
    assert proposal["quality_constraints"]["structural_change"] == "NONE"
    assert proposal["quality_constraints"]["provider_submission"] is False
    original = {str(item["shot_id"]): item for item in items}
    for row in proposal["shots"]:
        source = original[row["shot_id"]]
        assert row["queue_index"] == source["queue_index"]
        assert row["start_seconds"] == source["start_seconds"]
        assert row["end_seconds"] == source["end_seconds"]
        assert row["segment_ids"] == source["segment_ids"]
        assert row["beat_id"] == source["beat_id"]


def test_provider_duration_is_derived_not_fixed_eight_seconds() -> None:
    proposal = build_media_planner_v2_proposal(
        _load_items(),
        episode_id="episode-002-adam-temptation-fall-repentance",
        episode_duration_seconds=EPISODE_DURATION,
        structural_fingerprint="fp",
        creative_overlay_sha256="overlay",
    )
    units = proposal["video_units"]
    assert any(unit["timeline_required_seconds"] < 1.0 and unit["requested_seconds"] == 4 for unit in units)
    assert any(unit["requested_seconds"] != 8 for unit in units)
    assert all(unit["requested_seconds"] in {4, 6, 8} for unit in units)
    assert all(unit["expected_unused_seconds"] >= 0 for unit in units)


def test_veo_duration_uses_official_discrete_contract() -> None:
    task = {
        "taskType": "videoInference",
        "taskUUID": "planning-only",
        "model": "google:veo@3.1-lite",
        "positivePrompt": "A distinct cinematic motion phase.",
        "width": 1280,
        "height": 720,
        "duration": 2,
        "numberResults": 1,
        "deliveryMethod": "async",
        "includeCost": True,
        "providerSettings": {"google": {"generateAudio": False}},
    }
    with pytest.raises(ProviderModelContractError, match="VEO31_DURATION_OUT_OF_CONTRACT"):
        validate_runware_task(task)


def test_nano_banana_route_uses_official_1k_16_9_dimensions() -> None:
    route = route_image_shot(
        {
            "final_budget_treatment": "ANIMATED_STILL_COMPOSITING",
            "runware_positive_prompt_en": "A close-up portrait composition.",
            "visual_brief_ar": "close-up portrait",
        }
    )
    assert (route.width, route.height) == (1376, 768)


def test_still_preferred_and_video_required_are_not_cost_only_decisions() -> None:
    still = {
        "shot_id": "S-STILL",
        "queue_index": 6,
        "final_budget_treatment": "GENERATED_VIDEO",
        "motion": "Locked-off hold with only slight ambient dimming; no new visual event.",
        "camera_movement": "",
        "visual_concept": "An intentional iconic still hold.",
    }
    required = {
        "shot_id": "S-REQUIRED",
        "queue_index": 47,
        "final_budget_treatment": "ANIMATED_STILL_COMPOSITING",
        "motion": "Three-stage observable progression before, event, and after with a surface transformation.",
        "camera_movement": "Camera shifts laterally and the open area widens.",
        "visual_concept": "Causal consequence unfolds across time.",
    }
    assert classify_shot(still).classification == "ANIMATED_STILL_PREFERRED"
    assert classify_shot(required).classification == "VIDEO_REQUIRED_FOR_INTENT"


def test_cost_registry_unknown_prices_fail_closed() -> None:
    registry = load_pricing_registry(REGISTRY)
    assessment = assess_cost(
        [
            {
                "unit_id": "v1",
                "provider": "RUNWARE",
                "model": "google:veo@3.1-lite",
                "media_kind": "RUNWARE_VIDEO",
                "requested_seconds": 4,
            }
        ],
        registry,
    )
    assert assessment.pricing_status == "UNKNOWN"
    assert assessment.unpriced_requests == 1
    assert assessment.provider_execution_allowed is False


def test_complete_pricing_produces_bounded_envelope_without_network() -> None:
    registry = {
        "schema_version": "siraj-media-pricing-registry-v2",
        "registry_version": "fixture-v2",
        "entries": [
            {
                "provider": "RUNWARE",
                "model": "google:veo@3.1-lite",
                "media_kind": "RUNWARE_VIDEO",
                "status": "PRICED",
                "billing_unit": "per_generated_video_second",
                "unit_price": 0.10,
                "currency": "USD",
                "registry_version": "fixture-v2",
                "source": "OFFLINE_TEST_FIXTURE",
                "effective_at_utc": "2026-08-09T00:00:00Z",
            }
        ],
    }
    assessment = assess_cost(
        [{"unit_id": "v1", "provider": "RUNWARE", "model": "google:veo@3.1-lite", "media_kind": "RUNWARE_VIDEO", "requested_seconds": 4}],
        registry,
    )
    assert assessment.pricing_status == "COMPLETE"
    assert assessment.estimated_total_cost == 0.4
    assert assessment.maximum_bound == 0.4
    assert assessment.provider_execution_allowed is True


def test_stale_or_mismatched_pricing_version_blocks_execution() -> None:
    registry = {
        "schema_version": "siraj-media-pricing-registry-v2",
        "registry_version": "fixture-v2",
        "entries": [
            {
                "provider": "RUNWARE",
                "model": "google:veo@3.1-lite",
                "media_kind": "RUNWARE_VIDEO",
                "status": "PRICED",
                "billing_unit": "per_generated_video_second",
                "unit_price": 0.10,
                "currency": "USD",
                "registry_version": "old-v1",
                "source": "OFFLINE_TEST_FIXTURE",
                "effective_at_utc": "2026-08-09T00:00:00Z",
                "valid_until_utc": "2020-01-01T00:00:00Z",
            }
        ],
    }
    assessment = assess_cost(
        [{"unit_id": "v1", "provider": "RUNWARE", "model": "google:veo@3.1-lite", "media_kind": "RUNWARE_VIDEO", "requested_seconds": 4}],
        registry,
    )
    assert assessment.pricing_status == "UNKNOWN"
    assert assessment.provider_execution_allowed is False


def test_veo_negative_prompt_is_rejected() -> None:
    payload = {
        "taskType": "videoInference",
        "taskUUID": "planning-only",
        "model": "google:veo@3.1-lite",
        "positivePrompt": "distinct approved motion",
        "negativePrompt": "do not",
        "width": 1280,
        "height": 720,
        "duration": 4,
        "numberResults": 1,
        "deliveryMethod": "async",
        "includeCost": True,
        "providerSettings": {"google": {"generateAudio": False, "personGeneration": "dont_allow"}},
    }
    validated = validate_runware_task(payload)
    assert "negativePrompt" not in validated.payload
    assert validated.internal_metadata.get("internalNegativeConstraints") is None


def test_no_reuse_or_loop_and_coverage_does_not_count_provider_overhead() -> None:
    unit = {"unit_id": "v1", "media_kind": "RUNWARE_VIDEO", "direction_fingerprint": canonical_sha256({"shot": "1"}), "looped": False}
    validate_no_reuse_or_loop([unit])
    with pytest.raises(MediaMixPolicyError, match="VIDEO_LOOP_OR_REUSE_FORBIDDEN"):
        validate_no_reuse_or_loop([{**unit, "unit_id": "v2", "looped": True}])
    assert validate_true_video_coverage(100.0, 4.0).status == "FAIL_UNDER_VIDEO_FLOOR"
    assert coverage_diagnostics([], episode_duration_seconds=100.0)["longest_no_true_video_span_seconds"] == 100.0


def test_current_ep002_provider_execution_is_fail_closed_before_network() -> None:
    with pytest.raises(CostAuthorityError, match="MEDIA_PLAN_INVALID_UNDER_VIDEO_FLOOR"):
        require_complete_pricing_for_provider_execution(
            REPO,
            "episode-002-adam-temptation-fall-repentance",
        )


def test_cheap_still_fallback_cannot_push_a_plan_below_floor() -> None:
    # The cost objective can choose among eligible units, but policy validation
    # remains an independent hard boundary.
    assert validate_true_video_coverage(100.0, 49.99).status == "FAIL_UNDER_VIDEO_FLOOR"
    assert validate_true_video_coverage(100.0, 50.0).status == "PASS"


def test_directorial_target_and_sequence_percentages_are_derived() -> None:
    proposal = build_media_planner_v2_proposal(
        _load_items(),
        episode_id="episode-002-adam-temptation-fall-repentance",
        episode_duration_seconds=EPISODE_DURATION,
        structural_fingerprint="fp",
        creative_overlay_sha256="overlay",
    )
    target = proposal["directorial_target"]["directorially_preferred_video_percent"]
    assert 50.0 <= target <= 75.0
    percentages = {round(float(row["true_video_percent"]), 3) for row in proposal["sequences"]}
    assert len(percentages) > 1
    assert proposal["cinematic_range"]["minimum_cinematically_justified_video_seconds"] >= EPISODE_DURATION * 0.50


def test_only_true_video_units_count_not_stills_graphics_or_unused_seconds() -> None:
    units = [
        {"unit_id": "v1", "media_kind": "RUNWARE_VIDEO", "start_seconds": 0, "end_seconds": 4, "requested_seconds": 8},
        {"unit_id": "i1", "media_kind": "RUNWARE_IMAGE", "start_seconds": 4, "end_seconds": 20, "requested_seconds": 8},
        {"unit_id": "g1", "media_kind": "LOCAL_GRAPHICS", "start_seconds": 20, "end_seconds": 30, "requested_seconds": 8},
    ]
    assert true_video_seconds_from_units(units, episode_duration_seconds=100.0) == 4.0
