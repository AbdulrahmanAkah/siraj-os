from __future__ import annotations

from pathlib import Path

import pytest

from src.application.unified_constitution_enforcement_v1 import (
    RuleRegistry,
    analyze_face_semantics,
    compile_policy,
    load_unified_constitution,
)


REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def registry():
    return RuleRegistry.build(load_unified_constitution(REPO))


@pytest.mark.parametrize(
    "legacy_failure",
    (
        "Adam has a visible mouth",
        "stable faces and anatomy",
        "the woman has visible hands and body-defining clothing",
        "Adam has a gratuitous bare torso",
        "a magical light beam depicts the unseen mechanism",
        "a modern object appears in the ancient environment",
        "a third unapproved character enters the shot",
        "the visible action is the reverse of the narrated action",
    ),
)
def test_global_regression_contract_requires_blocking_evidence(registry, legacy_failure: str) -> None:
    contract = {
        "artifact_id": "GLOBAL-REGRESSION",
        "stage": "PROMPT_COMPILATION",
        "text": legacy_failure,
        "sensitive_domains": ["FACE", "MODESTY", "UNSEEN", "PERIOD", "CHARACTER", "VISUAL", "PROMPT"],
        "bindings": {
            "wardrobe_contract_id": "WARDROBE-1",
            "period_dossier_id": "PERIOD-1",
            "canonical_reference_sha256": "a" * 64,
        },
    }
    result = compile_policy(registry, contract, {"provider": "VEO_3_1_LITE"})
    assert result["status"] == "BLOCKED"
    assert result["errors"]


def test_duration_authority_conflict_is_global_not_episode_specific(registry) -> None:
    rule = registry.require("SIRAJ.S06.NARRATION_TIMELINE_AUTHORITY")
    assert rule["scope"] == "EPISODE"
    assert "EP002" not in str(rule)
    assert "reject_duration_cache_drift" in rule["tests"]


def test_no_global_enforcement_rule_is_episode_002_hardcoded(registry) -> None:
    for rule in registry.by_id.values():
        if rule["id"] != "SIRAJ.S09.HISTORICAL_UNKNOWN_ATTEMPT":
            assert "EP002" not in str(rule)


def test_safe_body_anatomy_phrase_remains_accepted() -> None:
    assert analyze_face_semantics("stable body anatomy and concealed head geometry") == ()
