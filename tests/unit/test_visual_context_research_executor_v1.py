from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.visual_context_research_executor_v1 import (
    VisualContextResearchExecutorError,
    VisualResearchProviderResult,
    build_executor_request,
    execute_visual_context_research,
)


DIMENSIONS = (
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


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False),
        encoding="utf-8",
    )


def _seed(repo: Path) -> None:
    (repo / "projects/episode-x").mkdir(parents=True)
    _write(
        repo / "projects/_series/visual-context-research-policy-v1.json",
        {
            "schema_version": "siraj-visual-context-research-policy-v1",
            "scope": "SERIES_WIDE",
            "constitution_precedence": True,
            "source_classes": [
                {
                    "id": "PRIMARY_OR_CANONICAL_TEXT",
                    "required_to_check": True,
                },
                {
                    "id": "ACADEMIC_SCHOLARLY_CONTEXT",
                    "required_to_check": True,
                },
            ],
            "face_policy": {
                "visible_face": "FORBIDDEN_WITHOUT_EXCEPTION",
                "head_required": False,
            },
        },
    )
    _write(
        repo / "projects/episode-x/research/evidence-package-v1.json",
        {
            "source_register": [
                {
                    "source_id": "SRC-001",
                    "url": "https://example.org/primary",
                    "source_type": "REFERENCE_WORK",
                }
            ]
        },
    )


def _dossier(web: bool = False) -> dict:
    sources = [
        {
            "source_id": "VCSRC-001",
            "title": "existing evidence",
            "url": "https://example.org/primary",
            "authority_class": "PRIMARY_OR_CANONICAL_TEXT",
            "publisher_or_author": "Example",
            "date_or_edition": "",
            "verified": True,
            "verification_method": "EPISODE_EVIDENCE_PACKAGE",
            "relevance_dimensions": ["environment"],
        }
    ]
    if web:
        sources.append(
            {
                "source_id": "VCSRC-002",
                "title": "scholarly source",
                "url": "https://example.edu/scholar",
                "authority_class": "ACADEMIC_SCHOLARLY_CONTEXT",
                "publisher_or_author": "University",
                "date_or_edition": "2026",
                "verified": True,
                "verification_method": "WEB_SEARCH_TOOL",
                "relevance_dimensions": ["wardrobe"],
            }
        )

    dimensions = {}
    for name in DIMENSIONS:
        dimensions[name] = {
            "status": "RESOLVED",
            "summary": name,
            "facts": [
                {
                    "fact_id": "F-" + name,
                    "text": name + " supported fact",
                    "certainty": "DIRECTLY_SUPPORTED",
                    "source_ids": ["VCSRC-001"],
                    "assertive_visualization": True,
                    "visual_implication": "use evidence",
                    "conflict_notes": "",
                }
            ],
        }

    return {
        "schema_version": "siraj-visual-context-dossier-v1",
        "episode_id": "episode-x",
        "context_id": "CTX",
        "status": "COMPLETE",
        "constitution_precedence": True,
        "research_scope": {
            "domain_profile": "GENERAL_DOCUMENTARY",
            "summary": "test",
            "research_language": "AR+EN",
        },
        "sources": sources,
        "research_exhaustion": {
            "search_complete": True,
            "source_classes_checked": [
                "PRIMARY_OR_CANONICAL_TEXT",
                "ACADEMIC_SCHOLARLY_CONTEXT",
            ],
            "unavailable_source_classes": {},
            "web_search_performed": web,
            "cross_source_reconciliation_complete": True,
        },
        "unresolved_conflicts": [],
        "dimensions": dimensions,
        "face_and_body_policy": {
            "face_visibility": "FORBIDDEN_WITHOUT_EXCEPTION",
            "head_required": False,
            "motion_safe_face_exclusion": True,
        },
        "framing_preferences": ["TORSO_HEAD_EXCLUDED"],
    }


def test_executor_request_expands_visual_research(tmp_path: Path):
    _seed(tmp_path)
    req = build_executor_request(
        tmp_path,
        episode_id="episode-x",
        context_id="CTX",
        narration_text="short narration",
        visual_brief={"brief": {"purpose": "historical scene"}},
    )
    assert len(req["dossier_requirements"]["required_dimensions"]) == 10
    assert req["source_sweep"]["no_early_stop_after_first_plausible_source"] is True
    assert req["dossier_requirements"]["head_required"] is False


def test_executor_persists_provenance_valid_dossier(tmp_path: Path):
    _seed(tmp_path)
    calls = {"n": 0}

    def provider(_request):
        calls["n"] += 1
        return VisualResearchProviderResult(
            payload=_dossier(web=False),
            provider="FAKE",
            model="fake",
            provider_response_id="r1",
            web_search_calls=0,
            cited_urls=(),
        )

    result = execute_visual_context_research(
        tmp_path,
        episode_id="episode-x",
        context_id="CTX",
        narration_text="short narration",
        visual_brief={"brief": {"purpose": "scene"}},
        provider_call=provider,
    )
    assert calls["n"] == 1
    assert result.provider_calls == 1
    assert result.dossier_path.is_file()
    assert result.receipt_path.is_file()


def test_web_source_must_be_grounded_by_provider_citation(tmp_path: Path):
    _seed(tmp_path)

    def provider(_request):
        return VisualResearchProviderResult(
            payload=_dossier(web=True),
            provider="FAKE",
            model="fake",
            provider_response_id="r1",
            web_search_calls=1,
            cited_urls=(),
        )

    with pytest.raises(
        VisualContextResearchExecutorError,
        match="WEB_SOURCE_NOT_PROVIDER_CITED",
    ):
        execute_visual_context_research(
            tmp_path,
            episode_id="episode-x",
            context_id="CTX",
            narration_text="short narration",
            visual_brief={"brief": {"purpose": "scene"}},
            provider_call=provider,
        )


def test_no_automatic_retry_when_provider_fails(tmp_path: Path):
    _seed(tmp_path)
    calls = {"n": 0}

    def provider(_request):
        calls["n"] += 1
        raise RuntimeError("provider failed")

    with pytest.raises(RuntimeError, match="provider failed"):
        execute_visual_context_research(
            tmp_path,
            episode_id="episode-x",
            context_id="CTX",
            narration_text="short narration",
            visual_brief={"brief": {"purpose": "scene"}},
            provider_call=provider,
        )
    assert calls["n"] == 1


def test_existing_valid_dossier_is_reused_without_provider(tmp_path: Path):
    _seed(tmp_path)

    def first(_request):
        return VisualResearchProviderResult(
            payload=_dossier(web=False),
            provider="FAKE",
            model="fake",
            provider_response_id="r1",
            web_search_calls=0,
            cited_urls=(),
        )

    execute_visual_context_research(
        tmp_path,
        episode_id="episode-x",
        context_id="CTX",
        narration_text="short narration",
        visual_brief={"brief": {"purpose": "scene"}},
        provider_call=first,
    )

    calls = {"n": 0}

    def should_not_run(_request):
        calls["n"] += 1
        raise AssertionError("must not call provider")

    result = execute_visual_context_research(
        tmp_path,
        episode_id="episode-x",
        context_id="CTX",
        narration_text="short narration",
        visual_brief={"brief": {"purpose": "scene"}},
        provider_call=should_not_run,
    )
    assert result.reused_existing is True
    assert result.provider_calls == 0
    assert calls["n"] == 0


def test_refresh_requires_reason_and_archives_previous(tmp_path: Path):
    _seed(tmp_path)

    def provider(_request):
        return VisualResearchProviderResult(
            payload=_dossier(web=False),
            provider="FAKE",
            model="fake",
            provider_response_id="r1",
            web_search_calls=0,
            cited_urls=(),
        )

    execute_visual_context_research(
        tmp_path,
        episode_id="episode-x",
        context_id="CTX",
        narration_text="short narration",
        visual_brief={"brief": {"purpose": "scene"}},
        provider_call=provider,
    )

    with pytest.raises(
        VisualContextResearchExecutorError,
        match="REFRESH_REASON_REQUIRED",
    ):
        execute_visual_context_research(
            tmp_path,
            episode_id="episode-x",
            context_id="CTX",
            narration_text="short narration",
            visual_brief={"brief": {"purpose": "scene"}},
            provider_call=provider,
            refresh_existing=True,
        )

    refreshed = execute_visual_context_research(
        tmp_path,
        episode_id="episode-x",
        context_id="CTX",
        narration_text="short narration",
        visual_brief={"brief": {"purpose": "scene"}},
        provider_call=provider,
        refresh_existing=True,
        refresh_reason="visual context was incomplete",
    )
    assert refreshed.archived_previous_path is not None
    assert refreshed.archived_previous_path.is_file()
