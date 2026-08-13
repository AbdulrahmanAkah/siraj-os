from __future__ import annotations

from pathlib import Path

import pytest

from src.application.unified_constitution_enforcement_v1 import (
    RuleRegistry,
    RuntimeGateEngine,
    ValidatorRegistry,
    artifact_sha256,
    build_rule_test_artifact,
    capability_boundary_evidence,
    load_unified_constitution,
)


REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "src/application/unified_constitution_enforcement_v1.py"


@pytest.fixture(scope="module")
def runtime():
    constitution = load_unified_constitution(REPO)
    registry = RuleRegistry.build(constitution)
    validators = ValidatorRegistry(registry)
    return registry, validators, RuntimeGateEngine(registry, validators)


def _gate_artifact(registry: RuleRegistry, gate: str) -> dict:
    selected = [rule for rule in registry.by_id.values() if gate in rule["runtime_gates"]]
    subject = {"gate": gate, "candidate": "compliant"}
    artifact = build_rule_test_artifact(selected[0], registry.constitution)
    artifact["subject"] = subject
    artifact["validation_receipts"] = {}
    subject_hash = artifact_sha256(subject)
    validators = ValidatorRegistry(registry)
    for rule in selected:
        for name in rule["validators"]:
            if validators.binding_kind(name) == "HUMAN_HASH_BOUND_EVIDENCE_RECEIPT":
                artifact["validation_receipts"][name] = {
                    "status": "PASS",
                    "subject_sha256": subject_hash,
                    "constitution_bundle_manifest_sha256": registry.constitution.bundle_manifest_sha256,
                    "human_actor": "TEST-HUMAN-REVIEWER",
                    "decision_time": "2026-08-13T12:00:00+03:00",
                }
    return artifact


@pytest.mark.parametrize(
    "gate",
    (
        "process_boot_gate",
        "research_gate",
        "script_gate",
        "tts_preflight_gate",
        "narration_master_gate",
        "character_gate",
        "storyboard_gate",
        "prompt_compilation_gate",
        "human_prompt_review_gate",
        "pilot_gate",
        "pre_submit_gate",
        "cost_preflight_gate",
        "paid_execution_gate",
        "render_promotion_gate",
        "montage_admission_gate",
        "final_qa_gate",
        "publish_ready_gate",
    ),
)
def test_runtime_gate_accepts_only_complete_hash_bound_evidence(runtime, gate: str) -> None:
    registry, _, engine = runtime
    decision = engine.evaluate(gate, _gate_artifact(registry, gate))
    assert decision.status == "PASS"
    assert decision.rule_ids
    assert decision.findings


@pytest.mark.parametrize(
    "gate",
    (
        "research_gate",
        "script_gate",
        "tts_preflight_gate",
        "narration_master_gate",
        "character_gate",
        "storyboard_gate",
        "prompt_compilation_gate",
        "human_prompt_review_gate",
        "pilot_gate",
        "pre_submit_gate",
        "cost_preflight_gate",
        "paid_execution_gate",
        "render_promotion_gate",
        "montage_admission_gate",
        "final_qa_gate",
        "publish_ready_gate",
    ),
)
def test_runtime_gate_blocks_missing_evidence(runtime, gate: str) -> None:
    registry, _, engine = runtime
    artifact = {"subject": {"gate": gate}, "text": "visible mouth", "validation_receipts": {}}
    assert engine.evaluate(gate, artifact).status == "BLOCKED"


def test_validator_is_read_only(runtime) -> None:
    registry, validators, _ = runtime
    rule = registry.require("SIRAJ.S01.ALL_HUMAN_FACES_VISIBLE")
    artifact = build_rule_test_artifact(rule, registry.constitution)
    before = artifact_sha256(artifact)
    validators.validate_rule(rule["id"], artifact)
    assert artifact_sha256(artifact) == before


def test_capability_boundaries_have_no_provider_or_network_imports() -> None:
    evidence = capability_boundary_evidence(MODULE)
    assert evidence["status"] == "PASS"
    assert evidence["forbidden_imports"] == []
    assert evidence["compiler_provider_call"] is False
    assert evidence["validator_mutation"] is False
    assert evidence["recovery_paid_capability"] is False
    assert evidence["tests_production_transport"] is False


def test_production_authorization_remains_false(runtime) -> None:
    registry, _, _ = runtime
    assert registry.constitution.constitution["production_authorized"] is False
