from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.visual_context_research_v1 import (
    VisualContextResearchError,
    build_research_request,
    load_series_policy,
    render_visual_context_prompt,
    select_body_framing,
    validate_visual_context_dossier,
)


def _policy(tmp_path: Path) -> dict:
    path = (
        tmp_path
        / "projects"
        / "_series"
        / "visual-context-research-policy-v1.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "schema_version": "siraj-visual-context-research-policy-v1",
        "scope": "SERIES_WIDE",
        "constitution_precedence": True,
        "source_classes": [
            {"id": "PRIMARY", "required_to_check": True},
            {"id": "SCHOLARLY", "required_to_check": True},
        ],
        "face_policy": {
            "visible_face": "FORBIDDEN_WITHOUT_EXCEPTION",
            "head_required": False,
        },
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return load_series_policy(tmp_path)


def _dimension(text: str = "supported fact") -> dict:
    return {
        "status": "RESOLVED",
        "facts": [
            {
                "text": text,
                "certainty": "DIRECTLY_SUPPORTED",
                "source_ids": ["S1"],
                "assertive_visualization": True,
            }
        ],
    }


def _dossier() -> dict:
    names = (
        "environment",
        "character_physical_context",
        "wardrobe",
        "society_and_customs",
        "material_culture",
        "architecture_and_settlement",
        "era_and_chronology",
        "geography_and_climate",
        "flora_fauna_and_landscape",
        "motion_and_face_safety",
    )
    return {
        "schema_version": "siraj-visual-context-dossier-v1",
        "episode_id": "episode-x",
        "context_id": "CTX",
        "status": "COMPLETE",
        "constitution_precedence": True,
        "research_scope": {
            "purpose": "canonical recurring identity in a researched environment"
        },
        "sources": [
            {
                "source_id": "S1",
                "authority_class": "PRIMARY",
                "verified": True,
                "title": "source",
            }
        ],
        "research_exhaustion": {
            "search_complete": True,
            "source_classes_checked": ["PRIMARY", "SCHOLARLY"],
            "unavailable_source_classes": {},
        },
        "unresolved_conflicts": [],
        "dimensions": {name: _dimension(name + " evidence") for name in names},
        "face_and_body_policy": {
            "face_visibility": "FORBIDDEN_WITHOUT_EXCEPTION",
            "head_required": False,
            "motion_safe_face_exclusion": True,
        },
        "framing_preferences": [],
    }


def test_research_request_expands_beyond_narration():
    req = build_research_request(
        episode_id="episode-x",
        context_id="CTX",
        narration_text="A short narration sentence.",
        visual_brief={"purpose": "historical scene"},
    )
    assert len(req["required_dimensions"]) == 10
    assert req["search_strategy"]["search_all_configured_source_classes"] is True
    assert req["search_strategy"]["narration_absence_does_not_authorize_invention"] is True


def test_dossier_requires_source_exhaustion(tmp_path: Path):
    policy = _policy(tmp_path)
    dossier = _dossier()
    dossier["research_exhaustion"]["source_classes_checked"] = ["PRIMARY"]

    with pytest.raises(
        VisualContextResearchError,
        match="SOURCE_CLASSES_NOT_EXHAUSTED:SCHOLARLY",
    ):
        validate_visual_context_dossier(
            dossier=dossier,
            policy=policy,
            episode_id="episode-x",
            context_id="CTX",
        )


def test_assertive_fact_requires_strong_evidence(tmp_path: Path):
    policy = _policy(tmp_path)
    dossier = _dossier()
    dossier["dimensions"]["environment"]["facts"][0]["certainty"] = "UNCERTAIN"

    with pytest.raises(
        VisualContextResearchError,
        match="ASSERTIVE_FACT_CERTAINTY_TOO_LOW",
    ):
        validate_visual_context_dossier(
            dossier=dossier,
            policy=policy,
            episode_id="episode-x",
            context_id="CTX",
        )


def test_system_can_choose_full_body_without_head_for_identity():
    dossier = _dossier()
    framing = select_body_framing(
        dossier=dossier,
        visual_brief={
            "brief": {
                "purpose": "canonical recurring-character identity",
                "identity_lock": ["stable body proportions"],
            }
        },
    )
    assert framing["mode"] == "FULL_BODY_HEAD_EXCLUDED"
    assert framing["head_required"] is False
    assert framing["face_visibility"] == "FORBIDDEN_WITHOUT_EXCEPTION"


def test_system_can_choose_hands_only_when_hands_carry_action():
    dossier = _dossier()
    framing = select_body_framing(
        dossier=dossier,
        visual_brief={
            "brief": {
                "purpose": "show hands receiving an object",
            }
        },
    )
    assert framing["mode"] == "HANDS_ONLY"
    assert framing["system_selects_visible_body_element"] is True


def test_rendered_prompt_makes_face_rule_motion_safe():
    dossier = _dossier()
    framing = {
        "mode": "TORSO_HEAD_EXCLUDED",
        "description": "crop the entire head outside frame",
    }
    prompt = render_visual_context_prompt(
        dossier=dossier,
        framing=framing,
    )
    assert "A head is never required." in prompt
    assert "Visible human face is forbidden without exception." in prompt
    assert "plausible animation must not reveal" in prompt
    assert "narration silence is never permission to invent" in prompt
