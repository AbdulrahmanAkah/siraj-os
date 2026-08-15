from pathlib import Path
import json

from src.application.unified_constitution_enforcement_v1 import (
    RuleRegistry,
    ValidatorRegistry,
    build_rule_test_artifact,
    load_unified_constitution,
)

REPO = Path(__file__).resolve().parents[2]


def _rule(doc, rule_id):
    matches = [r for r in doc["rules"] if r["id"] == rule_id]
    assert len(matches) == 1
    return matches[0]


def test_v1_2_identity_and_path():
    loaded = load_unified_constitution(REPO)
    assert loaded.constitution["id"] == "SIRAJ_UNIFIED_PRODUCTION_CONSTITUTION"
    assert loaded.constitution["version"] == "1.2.0"
    assert loaded.manifest["version"] == "1.2.0"
    assert Path(loaded.bundle_directory).name == "1.2.0"
    assert len(loaded.rules) == 51


def test_c2_uses_existing_machine_enforced_scoped_authorization_stack():
    loaded = load_unified_constitution(REPO)
    registry = RuleRegistry.build(loaded)
    assert loaded.constitution["production_authorized"] is False
    assert "SIRAJ.S09.SCOPED_PRODUCTION_AUTHORIZATION" not in registry.by_id
    assert "authorization_envelope_validator" in registry.require(
        "SIRAJ.S09.PAID_EXECUTION_BOUNDARY"
    )["validators"]
    assert "authorization_hash_validator" in registry.require(
        "SIRAJ.S09.COST_AUTHORIZATION"
    )["validators"]
    assert "stale_state_validator" in registry.require(
        "SIRAJ.S10.APPROVAL_HASH_BINDING"
    )["validators"]


def test_c3_has_no_ep002_specific_identity_and_generic_validator_passes():
    loaded = load_unified_constitution(REPO)
    registry = RuleRegistry.build(loaded)
    rule = registry.require("SIRAJ.S09.HISTORICAL_UNKNOWN_ATTEMPT")
    serialized = json.dumps(dict(rule), ensure_ascii=False, default=str)
    assert "EP002-SH-001-V01" not in serialized
    assert "1e6d0013-d37f-5df7-ab53-444c4f17c14c" not in serialized
    assert "ANY_HISTORICAL_SUBMISSION_UNKNOWN" in serialized
    validators = ValidatorRegistry(registry)
    artifact = build_rule_test_artifact(rule, loaded)
    findings = validators.validate_rule(rule["id"], artifact)
    assert findings
    assert all(f.status == "PASS" for f in findings)


def test_c6_short_only_burned_captions():
    loaded = load_unified_constitution(REPO)
    rule = _rule(
        loaded.rules_document, "SIRAJ.S06.EXTERNAL_CLOSED_CAPTIONS"
    )
    value = rule["value"]
    assert value["longform"]["burned_in"] is False
    assert value["longform"]["on_screen_subtitles"] is False
    short = value["short_derivative"]
    assert short["burned_narration_captions"] is True
    assert short["requires_narration_sync"] is True
    assert short["narration_only"] is True
    assert short["invented_text"] is False
    assert tuple(rule["validators"]) == (
        "caption_separation_validator",
        "render_text_overlay_validator",
    )


def test_h3_material_anachronism_only_is_hard_fail():
    loaded = load_unified_constitution(REPO)
    rule = _rule(loaded.rules_document, "SIRAJ.S01.PERIOD_AUTHENTICITY")
    value = rule["value"]
    assert value["material_demonstrable_anachronism"] == "HARD_FAIL"
    assert value["unknown_policy"] == "NEUTRAL_DO_NOT_INVENT"
    assert value["minor_uncertain_detail"] == "WEIGHTED_REVIEW"


def test_h4_pilot_is_risk_conditional_with_bound_validators():
    loaded = load_unified_constitution(REPO)
    registry = RuleRegistry.build(loaded)
    rule = registry.require("SIRAJ.S04.HARD_SHOT_PILOT")
    value = rule["value"]
    assert value["not_blanket_required_for_every_episode"] is True
    assert {
        "NEW_PROVIDER",
        "NEW_MODEL",
        "NEW_RISK_CLASS",
        "HIGH_RISK_PAID_BATCH",
    } <= set(value["required_when_any"])
    validators = ValidatorRegistry(registry)
    assert all(
        validators.binding_kind(name) != "MISSING"
        for name in rule["validators"]
    )
