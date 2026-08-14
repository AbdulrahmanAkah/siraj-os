from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.presentation.desktop.shorts_caption_ux_v1 import (
    CAPTION_FRAME_HEIGHT,
    CAPTION_FRAME_WIDTH,
    CAPTION_LABELS_AR,
    CAPTION_MAX_LINES,
    CAPTIONS_DEFAULT_ENABLED,
    CaptionTechnicalDetails,
    CaptionUxContractError,
    CaptionVisualFixtureError,
    LongformCaptionUxViewModel,
    REQUIRED_VISUAL_SCENARIOS,
    SURFACE_LONGFORM,
    SURFACE_SHORTS_PRODUCTION,
    SURFACE_SHORTS_REVIEW,
    build_caption_ux_view_model,
    build_longform_caption_ux_view_model,
    build_shorts_caption_ux_view_model,
    load_visual_fixture_manifest,
    parse_visual_fixture_manifest,
)


REPO = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO / "tests" / "fixtures" / "shorts_caption_visual_fixtures_v1.json"


def _details() -> CaptionTechnicalDetails:
    return CaptionTechnicalDetails(
        timing_source="TRUSTED_HASH_BOUND_SENTENCE_TIMING",
        cue_count=4,
        status="READY",
        source_sha256="a" * 64,
        transcript_sha256="b" * 64,
    )


def test_shorts_production_and_review_default_to_enabled_without_raw_cues() -> None:
    for surface in (SURFACE_SHORTS_PRODUCTION, SURFACE_SHORTS_REVIEW):
        model = build_shorts_caption_ux_view_model(surface, _details())
        public = model.to_public_dict()
        assert CAPTIONS_DEFAULT_ENABLED is True
        assert model.captions_enabled is True
        assert model.toggle_visible is True
        assert model.toggle_label == CAPTION_LABELS_AR["toggle"]
        assert model.state_label == CAPTION_LABELS_AR["enabled"]
        assert public["technical_details"]["timing_source"] == "TRUSTED_HASH_BOUND_SENTENCE_TIMING"
        assert public["technical_details"]["cue_count"] == 4
        assert public["technical_details"]["status"] == "READY"
        assert public["raw_cue_json_visible"] is False
        assert "cues" not in public
        assert "raw_cues" not in public


def test_human_can_explicitly_disable_short_captions_without_mutating_evidence() -> None:
    model = build_shorts_caption_ux_view_model(SURFACE_SHORTS_REVIEW, _details())
    disabled = model.with_captions_enabled(False)
    assert disabled.captions_enabled is False
    assert disabled.state_label == CAPTION_LABELS_AR["disabled"]
    assert disabled.technical_details == model.technical_details
    assert disabled.to_public_dict()["technical_details"] == model.to_public_dict()["technical_details"]


def test_technical_details_reject_invalid_values_fail_closed() -> None:
    with pytest.raises(CaptionUxContractError, match="cue_count"):
        CaptionTechnicalDetails(timing_source="SOURCE", cue_count=-1, status="READY")
    with pytest.raises(CaptionUxContractError, match="source_sha256"):
        CaptionTechnicalDetails(timing_source="SOURCE", cue_count=1, status="READY", source_sha256="stale")
    with pytest.raises(CaptionUxContractError, match="timing_source"):
        CaptionTechnicalDetails(timing_source="", cue_count=1, status="READY")


def test_mapping_adapter_accepts_timing_type_aliases_but_not_raw_cue_data() -> None:
    details = CaptionTechnicalDetails.from_mapping(
        {
            "timing_source_type": "TRUSTED_PHRASE_TIMING",
            "cue_count": 2,
            "caption_status": "READY",
            "timing_source_sha256": "c" * 64,
            "cues": [{"start": 0, "end": 1, "text": "لا تعرض"}],
        }
    )
    assert details.timing_source == "TRUSTED_PHRASE_TIMING"
    assert details.status == "READY"
    assert details.cue_count == 2
    assert "cues" not in details.to_dict()


def test_longform_model_has_no_caption_control() -> None:
    model = build_longform_caption_ux_view_model()
    assert isinstance(model, LongformCaptionUxViewModel)
    assert model.surface == SURFACE_LONGFORM
    assert model.caption_control_visible is False
    public = model.to_public_dict()
    assert public["caption_control_visible"] is False
    assert "captions_enabled" not in public
    assert "technical_details" not in public
    with pytest.raises(CaptionUxContractError, match="longform_technical_details"):
        build_caption_ux_view_model(SURFACE_LONGFORM, _details())


def test_generic_dispatch_keeps_longform_separate_from_shorts() -> None:
    shorts = build_caption_ux_view_model(SURFACE_SHORTS_PRODUCTION, _details())
    longform = build_caption_ux_view_model(SURFACE_LONGFORM)
    assert shorts.surface == SURFACE_SHORTS_PRODUCTION
    assert longform.surface == SURFACE_LONGFORM
    assert longform.to_public_dict()["caption_control_visible"] is False


def test_visual_fixture_manifest_covers_dimensions_and_all_required_scenarios() -> None:
    manifest = load_visual_fixture_manifest(FIXTURE_PATH)
    assert manifest.width == CAPTION_FRAME_WIDTH == 1080
    assert manifest.height == CAPTION_FRAME_HEIGHT == 1920
    assert manifest.max_lines == CAPTION_MAX_LINES == 2
    assert {scenario.scenario_id for scenario in manifest.scenarios} >= set(REQUIRED_VISUAL_SCENARIOS)
    assert next(item for item in manifest.scenarios if item.scenario_id == "fallback_placement").expected_result == "FALLBACK_PLACEMENT"
    assert next(item for item in manifest.scenarios if item.scenario_id == "impossible_placement").expected_result == "CAPTION_PLACEMENT_BLOCKED"


def test_visual_fixture_manifest_rejects_wrong_frame_dimensions() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["width"] = 720
    with pytest.raises(CaptionVisualFixtureError, match="1080X1920"):
        parse_visual_fixture_manifest(payload)


def test_visual_fixture_manifest_rejects_missing_required_scenario() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["scenarios"] = [item for item in payload["scenarios"] if item["id"] != "arabic_numbers"]
    with pytest.raises(CaptionVisualFixtureError, match="arabic_numbers"):
        parse_visual_fixture_manifest(payload)


def test_visual_fixture_manifest_rejects_invalid_placement_contract() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for item in payload["scenarios"]:
        if item["id"] == "impossible_placement":
            item["expected_result"] = "PASS"
    with pytest.raises(CaptionVisualFixtureError, match="impossible_placement"):
        parse_visual_fixture_manifest(payload)
