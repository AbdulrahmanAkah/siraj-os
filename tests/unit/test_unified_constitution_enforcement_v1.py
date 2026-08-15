from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from src.application.unified_constitution_enforcement_v1 import (
    ApprovalReceipt,
    ApprovalValidationError,
    ConstitutionLoadError,
    FakePaidExecutor,
    InvalidationEngine,
    PaidExecutionEnvelope,
    RuleRegistry,
    ValidatorRegistry,
    analyze_face_semantics,
    artifact_sha256,
    build_rule_test_artifact,
    compile_policy,
    evaluate_paid_execution_envelope,
    load_unified_constitution,
    verify_approval_receipt,
)


REPO = Path(__file__).resolve().parents[2]
BUNDLE_RELATIVE = Path("config/constitution/siraj-unified-production-constitution/1.2.0")


@pytest.fixture(scope="module")
def constitution():
    return load_unified_constitution(REPO)


@pytest.fixture(scope="module")
def registry(constitution):
    return RuleRegistry.build(constitution)


def _copy_bundle(tmp_path: Path) -> Path:
    target = tmp_path / BUNDLE_RELATIVE
    target.parent.mkdir(parents=True)
    shutil.copytree(REPO / BUNDLE_RELATIVE, target)
    return target


def _rewrite_manifest_entry(bundle: Path, filename: str) -> None:
    manifest_path = bundle / "bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target = bundle / filename
    import hashlib

    for entry in manifest["files"]:
        if entry["path"] == filename:
            payload = target.read_bytes()
            entry["bytes"] = len(payload)
            entry["sha256"] = hashlib.sha256(payload).hexdigest()
            break
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_mutated_bundle(tmp_path: Path, mutate) -> None:
    bundle = _copy_bundle(tmp_path)
    mutate(bundle)
    load_unified_constitution(tmp_path)


def test_e0_full_draft_2020_12_schema_validation_runs(constitution) -> None:
    assert constitution.schema_validator_version
    assert constitution.schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_e0_canonical_metadata_and_counts(constitution) -> None:
    metadata = constitution.constitution
    assert metadata == {
        "id": "SIRAJ_UNIFIED_PRODUCTION_CONSTITUTION",
        "version": "1.2.0",
        "bundle_id": "SIRAJ-CONSTITUTION-1.2.0-20260815",
        "authority": "SYSTEM_ROOT",
        "scope": "SERIES_WIDE",
        "fail_closed": True,
        "consolidation_status": "COMPLETE",
        "implementation_status": "NOT_STARTED",
        "production_authorized": False,
    }
    assert len(constitution.rules) == 51
    assert len({rule["id"] for rule in constitution.rules}) == 51
    assert {rule["section"] for rule in constitution.rules} == set(range(1, 11))
    assert len(constitution.rules_document["invalidation_events"]) == 14


def test_loaded_constitution_is_deeply_read_only(constitution) -> None:
    with pytest.raises(TypeError):
        constitution.rules_document["constitution"]["production_authorized"] = True
    with pytest.raises(TypeError):
        constitution.rules[0]["value"] = True


def test_e0_missing_constitution_blocks(tmp_path: Path) -> None:
    with pytest.raises(ConstitutionLoadError, match="CONSTITUTION_MISSING"):
        load_unified_constitution(tmp_path)


def test_e0_corrupt_json_blocks(tmp_path: Path) -> None:
    def mutate(bundle: Path) -> None:
        (bundle / "siraj_unified_constitution_v1.rules.json").write_text("{", encoding="utf-8")
        _rewrite_manifest_entry(bundle, "siraj_unified_constitution_v1.rules.json")

    with pytest.raises(ConstitutionLoadError, match="CONSTITUTION_JSON_INVALID"):
        _load_mutated_bundle(tmp_path, mutate)


def test_e0_schema_invalid_rule_blocks(tmp_path: Path) -> None:
    def mutate(bundle: Path) -> None:
        path = bundle / "siraj_unified_constitution_v1.rules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["rules"][0]["runtime_gates"]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _rewrite_manifest_entry(bundle, path.name)

    with pytest.raises(ConstitutionLoadError, match="SCHEMA_INVALID"):
        _load_mutated_bundle(tmp_path, mutate)


def test_e0_bad_manifest_hash_blocks(tmp_path: Path) -> None:
    def mutate(bundle: Path) -> None:
        path = bundle / "README.md"
        path.write_text(path.read_text(encoding="utf-8") + "changed", encoding="utf-8")

    with pytest.raises(ConstitutionLoadError, match="MANIFEST_SIZE_MISMATCH|HASH_MISMATCH"):
        _load_mutated_bundle(tmp_path, mutate)


def test_e0_manifest_missing_file_blocks(tmp_path: Path) -> None:
    def mutate(bundle: Path) -> None:
        (bundle / "README.md").unlink()

    with pytest.raises(ConstitutionLoadError, match="MANIFEST_FILE_MISSING"):
        _load_mutated_bundle(tmp_path, mutate)


def test_e0_wrong_version_blocks(tmp_path: Path) -> None:
    def mutate(bundle: Path) -> None:
        path = bundle / "siraj_unified_constitution_v1.rules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["constitution"]["version"] = "9.9.9"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _rewrite_manifest_entry(bundle, path.name)

    with pytest.raises(ConstitutionLoadError, match="CONSTITUTION_VERSION_INVALID|MANIFEST_VERSION_MISMATCH"):
        _load_mutated_bundle(tmp_path, mutate)


def test_e0_duplicate_rule_blocks(tmp_path: Path) -> None:
    def mutate(bundle: Path) -> None:
        path = bundle / "siraj_unified_constitution_v1.rules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["rules"][1]["id"] = data["rules"][0]["id"]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _rewrite_manifest_entry(bundle, path.name)

    with pytest.raises(ConstitutionLoadError, match="DUPLICATE_RULE|RULE_SECTION_MISMATCH"):
        _load_mutated_bundle(tmp_path, mutate)


def test_e0_missing_section_blocks(tmp_path: Path) -> None:
    def mutate(bundle: Path) -> None:
        path = bundle / "siraj_unified_constitution_v1.rules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for rule in data["rules"]:
            if rule["section"] == 10:
                rule["section"] = 9
                rule["id"] = rule["id"].replace("S10", "S09")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _rewrite_manifest_entry(bundle, path.name)

    with pytest.raises(ConstitutionLoadError, match="SECTION_COVERAGE_INVALID|DUPLICATE_RULE"):
        _load_mutated_bundle(tmp_path, mutate)


def test_e0_lower_layer_authority_insertion_blocks(tmp_path: Path) -> None:
    def mutate(bundle: Path) -> None:
        path = bundle / "siraj_unified_constitution_v1.rules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["precedence"].insert(0, "EPISODE_OVERRIDE")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _rewrite_manifest_entry(bundle, path.name)

    with pytest.raises(ConstitutionLoadError, match="PRECEDENCE_INVALID"):
        _load_mutated_bundle(tmp_path, mutate)


def test_e0_duplicate_machine_policy_authority_blocks(tmp_path: Path) -> None:
    bundle = _copy_bundle(tmp_path)
    duplicate = tmp_path / "config/constitution/duplicate/1.0.0"
    duplicate.mkdir(parents=True)
    shutil.copy2(
        bundle / "siraj_unified_constitution_v1.rules.json",
        duplicate / "siraj_unified_constitution_v1.rules.json",
    )
    with pytest.raises(ConstitutionLoadError, match="DUPLICATE_POLICY_AUTHORITY"):
        load_unified_constitution(tmp_path)


def test_e0_invalid_failure_code_blocks(tmp_path: Path) -> None:
    def mutate(bundle: Path) -> None:
        path = bundle / "siraj_unified_constitution_v1.rules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["rules"][0]["failure_codes"] = ["ALLOW_FACE"]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _rewrite_manifest_entry(bundle, path.name)

    with pytest.raises(ConstitutionLoadError, match="SCHEMA_INVALID|FAILURE_CODE_INVALID"):
        _load_mutated_bundle(tmp_path, mutate)


def test_e0_unknown_sensitive_value_blocks(tmp_path: Path) -> None:
    def mutate(bundle: Path) -> None:
        path = bundle / "siraj_unified_constitution_v1.rules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["rules"][0]["value"] = "UNKNOWN"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _rewrite_manifest_entry(bundle, path.name)

    with pytest.raises(ConstitutionLoadError, match="SENSITIVE_VALUE_UNKNOWN"):
        _load_mutated_bundle(tmp_path, mutate)


FACE_ATTACKS = (
    "visible face",
    "visible mouth",
    "visible lips",
    "his lips can be seen",
    "her eyes are visible",
    "eye visible through veil",
    "lower face visible",
    "partial face",
    "face partly visible",
    "partially obscured face",
    "profile clearly visible",
    "frontal close-up",
    "three-quarter facial view",
    "reflected face in water",
    "face visible in mirror",
    "painted human portrait with visible facial features",
    "face visible on screen",
    "face visible in photograph",
    "statue with readable facial features",
    "background bystanders with visible faces",
    "crowd with visible faces",
    "distant readable face",
    "silhouette revealing facial details",
    "stable faces and anatomy",
    "front-facing close-up while hood does not cover the lower face; no visible face",
    "no visible face; camera reveals the mouth",
)


@pytest.mark.parametrize("text", FACE_ATTACKS)
def test_face_adversarial_corpus_blocks(text: str) -> None:
    assert analyze_face_semantics(text) == ("FAIL_GLOBAL_FACE_POLICY",)


@pytest.mark.parametrize(
    "text",
    (
        "safe back-view composition with the face fully excluded",
        "head outside frame and no visible human face",
        "rear view with opaque physical concealment persistent in every frame",
        "non-face silhouette with no readable facial geometry",
        "stable body anatomy and concealed head geometry",
    ),
)
def test_face_positive_corpus_passes(text: str) -> None:
    assert analyze_face_semantics(text) == ()


def _base_contract(text: str) -> dict:
    return {
        "artifact_id": "SHOT-001",
        "stage": "PROMPT_COMPILATION",
        "text": text,
        "sensitive_domains": ["FACE", "MODESTY", "PERIOD", "CHARACTER", "SOURCE", "AUDIO", "PROMPT"],
        "bindings": {
            "wardrobe_contract_id": "WARDROBE-1",
            "period_dossier_id": "PERIOD-1",
            "canonical_reference_sha256": "a" * 64,
            "source_certainty": "HIGH",
            "narration_master_sha256": "b" * 64,
        },
    }


def test_policy_compiler_is_deterministic_and_offline(registry) -> None:
    contract = _base_contract("safe back-view composition, face fully excluded")
    profile = {"provider": "VEO_3_1_LITE", "network": False}
    first = compile_policy(registry, contract, profile)
    second = compile_policy(registry, deepcopy(contract), deepcopy(profile))
    assert first == second
    assert first["status"] == "PASS"
    assert first["provider_call_allowed"] is False
    assert first["network_allowed"] is False
    assert first["paid_execution_allowed"] is False


def test_policy_compiler_rejects_semantic_contradiction(registry) -> None:
    result = compile_policy(
        registry,
        _base_contract("no visible face; front-facing close-up while hood does not cover the lower face"),
        {"provider": "VEO_3_1_LITE"},
    )
    assert result["status"] == "BLOCKED"
    assert "FAIL_GLOBAL_FACE_POLICY" in result["errors"]


def test_policy_compiler_has_no_silent_sensitive_default(registry) -> None:
    contract = _base_contract("safe rear view")
    contract["bindings"]["canonical_reference_sha256"] = "UNKNOWN"
    result = compile_policy(registry, contract, {})
    assert result["status"] == "BLOCKED"
    assert "FAIL_REQUIRED_BINDING:canonical_reference_sha256" in result["errors"]


def test_policy_compiler_blocks_longform_caption_flags_and_unbound_short_exception(registry) -> None:
    longform = _base_contract("safe rear view")
    longform["burned_captions"] = True
    result = compile_policy(registry, longform, {})
    assert result["status"] == "BLOCKED"
    assert "FAIL_LONGFORM_BURNED_CAPTIONS" in result["errors"]

    short = _base_contract("safe rear view")
    short["artifact_scope"] = "SHORT_DERIVATIVE"
    short["burned_captions"] = True
    result = compile_policy(registry, short, {})
    assert result["status"] == "BLOCKED"
    assert "FAIL_SHORT_CAPTION_SCOPE_CONTRACT" in result["errors"]


def _short_caption_artifact(registry) -> dict:
    rule = registry.require("SIRAJ.S06.EXTERNAL_CLOSED_CAPTIONS")
    artifact = build_rule_test_artifact(rule, registry.constitution)
    artifact["artifact_scope"] = "SHORT_DERIVATIVE"
    artifact["burned_captions"] = True
    artifact["on_screen_subtitles"] = False
    artifact["graphics_contract"]["burned_captions"] = True
    artifact["caption_contract"] = {
        "mode": "BURNED_NARRATION_CAPTIONS",
        "enabled": True,
        "synced_to_narration": True,
        "narration_only": True,
        "text_is_verbatim": True,
        "text_authority": "CANONICAL_TIMED_TRANSCRIPT",
        "transcript_sha256": "a" * 64,
        "timing_source_sha256": "b" * 64,
        "invented_text": False,
        "hook_text": False,
        "title_card_text": False,
        "cta_text": False,
        "subscribe_text": False,
        "decorative_prose": False,
        "fact_overlay_text": False,
        "unrelated_text": False,
        "banner_text": False,
        "promotional_text": False,
    }
    return artifact


def test_longform_burned_captions_remain_blocked(registry) -> None:
    rule = registry.require("SIRAJ.S06.EXTERNAL_CLOSED_CAPTIONS")
    artifact = build_rule_test_artifact(rule, registry.constitution)
    artifact["burned_captions"] = True
    finding = ValidatorRegistry(registry).validate("caption_separation_validator", artifact)
    assert finding.status == "BLOCKED"
    assert finding.failure_code == "FAIL_BURNED_IN_CAPTIONS"


def test_longform_on_screen_subtitles_remain_blocked(registry) -> None:
    rule = registry.require("SIRAJ.S06.EXTERNAL_CLOSED_CAPTIONS")
    artifact = build_rule_test_artifact(rule, registry.constitution)
    artifact["on_screen_subtitles"] = True
    finding = ValidatorRegistry(registry).validate("caption_separation_validator", artifact)
    assert finding.status == "BLOCKED"
    assert finding.failure_code == "FAIL_BURNED_IN_CAPTIONS"


def test_short_derivative_allows_only_hash_bound_narration_captions(registry) -> None:
    validators = ValidatorRegistry(registry)
    artifact = _short_caption_artifact(registry)
    caption = validators.validate("caption_separation_validator", artifact)
    graphics = validators.validate("render_graphics_validator", artifact)
    assert caption.status == "PASS"
    assert graphics.status == "PASS"


def test_short_derivative_caption_invented_text_or_missing_hash_blocks(registry) -> None:
    artifact = _short_caption_artifact(registry)
    artifact["caption_contract"]["cta_text"] = True
    assert ValidatorRegistry(registry).validate("caption_separation_validator", artifact).status == "BLOCKED"
    artifact = _short_caption_artifact(registry)
    artifact["caption_contract"]["timing_source_sha256"] = "UNKNOWN"
    assert ValidatorRegistry(registry).validate("caption_separation_validator", artifact).status == "BLOCKED"


def _approval_mapping(constitution, subject: object) -> dict:
    return {
        "approval_id": "APPROVAL-1",
        "approval_type": "PROMPT_APPROVAL",
        "human_actor": "HUMAN-OWNER",
        "decision": "PASS",
        "decision_time": "2026-08-13T12:00:00+03:00",
        "constitution_bundle_manifest_sha256": constitution.bundle_manifest_sha256,
        "input_artifact_ids": ["PROMPT-1"],
        "input_sha256s": [artifact_sha256(subject)],
        "scope": "PROMPT-1",
        "expires_or_stales_on": ["PROMPT_OR_PROVIDER_PAYLOAD_CHANGED"],
        "consumed_by_transaction_id_if_any": None,
    }


def test_hash_bound_approval_accepts_exact_bytes(constitution) -> None:
    subject = {"prompt": "safe rear view"}
    receipt = ApprovalReceipt.from_mapping(_approval_mapping(constitution, subject))
    verify_approval_receipt(
        receipt,
        constitution,
        {"PROMPT-1": artifact_sha256(subject)},
        required_scope="PROMPT-1",
    )


def test_same_filename_different_bytes_is_stale(constitution) -> None:
    old = {"prompt": "safe rear view"}
    new = {"prompt": "visible mouth"}
    receipt = ApprovalReceipt.from_mapping(_approval_mapping(constitution, old))
    with pytest.raises(ApprovalValidationError, match="APPROVAL_INPUT_HASH_STALE"):
        verify_approval_receipt(
            receipt,
            constitution,
            {"PROMPT-1": artifact_sha256(new)},
            required_scope="PROMPT-1",
        )


@pytest.mark.parametrize(
    "event",
    (
        "CONSTITUTION_BUNDLE_CHANGED",
        "SOURCE_OR_CLAIM_CHANGED",
        "CANONICAL_SCRIPT_CHANGED",
        "NARRATION_MASTER_CHANGED",
        "CHARACTER_OR_PERIOD_CONTRACT_CHANGED",
        "CANONICAL_REFERENCE_CHANGED",
        "STORYBOARD_CHANGED",
        "PROMPT_OR_PROVIDER_PAYLOAD_CHANGED",
        "PROVIDER_MODEL_OR_RATE_CHANGED",
        "BATCH_SCOPE_OR_REQUEST_COUNT_CHANGED",
        "NEW_UNPILOTED_RISK_CLASS",
        "RENDER_BYTES_CHANGED",
        "INTRO_OR_OUTRO_CHANGED",
        "MONTAGE_CHANGED",
    ),
)
def test_all_14_invalidation_events_are_implemented_and_tested(constitution, event: str) -> None:
    invalidated = InvalidationEngine(constitution).invalidate(event)
    assert invalidated


def test_script_change_propagates_transitively(constitution) -> None:
    invalidated = InvalidationEngine(constitution).invalidate("CANONICAL_SCRIPT_CHANGED")
    assert {"PROMPT_APPROVAL", "PILOT_APPROVAL", "PAID_AUTHORIZATION", "MONTAGE_APPROVAL", "FINAL_CERTIFICATION"} <= invalidated


def test_irrelevant_nonmaterial_change_does_not_invalidate(constitution) -> None:
    assert InvalidationEngine(constitution).invalidate("STORYBOARD_CHANGED", material=False) == frozenset()


def test_unknown_sensitive_materiality_blocks(constitution) -> None:
    invalidated = InvalidationEngine(constitution).invalidate("STORYBOARD_CHANGED", material=None)
    assert "SENSITIVE_MATERIALITY_REAPPROVAL_BLOCK" in invalidated


def _bad_artifact_for_validator(validators: ValidatorRegistry, name: str, artifact: dict) -> dict:
    candidate = deepcopy(artifact)
    family = validators.binding_kind(name).removeprefix("AUTOMATED:")
    if family == "HUMAN_HASH_BOUND_EVIDENCE_RECEIPT":
        candidate["validation_receipts"].pop(name, None)
    elif family in {"FACE", "SEMANTIC"}:
        candidate["text"] = "visible mouth"
    elif family == "MODESTY":
        candidate["wardrobe_contract"]["female_maximum_modesty"] = False
    elif family == "UNSEEN":
        candidate["unseen_contract"]["invented_form_or_mechanism"] = True
    elif family == "PERIOD":
        candidate["period_contract"]["modern_elements"] = ["smartphone"]
    elif family == "CHARACTER":
        candidate["character_contract"]["identity_drift"] = True
    elif family == "SOURCE":
        candidate["claims"][0]["certainty_out"] = "CERTAIN"
    elif family == "GRAPHICS":
        candidate["graphics_contract"]["arbitrary_graphics"] = True
    elif family == "NARRATIVE":
        candidate["narrative_contract"]["false_hook"] = True
    elif family == "DURATION":
        candidate["episode_duration_contract"]["minutes"] = 5
    elif family == "APPROVAL":
        candidate["approval_contract"]["stale"] = True
    elif family == "TTS":
        candidate["tts_contract"]["semantic_equivalence"] = False
    elif family == "VISUAL":
        candidate["visual_contract"]["action_inverted"] = True
    elif family == "VIDEO_SHARE":
        candidate["media_share_contract"]["video_seconds"] = 100
    elif family == "REUSE":
        candidate["reuse_contract"]["repetitive_padding"] = True
    elif family == "PILOT":
        candidate["pilot_contract"]["approved"] = False
    elif family == "PROMPT":
        candidate["prompt_contract"]["structured"] = False
    elif family == "PROVIDER":
        candidate["provider_profile"]["automatic_switching"] = True
    elif family == "BATCH":
        candidate["batch_contract"]["bounded_request_count"] = False
    elif family == "RETRY":
        candidate["retry_contract"].update({"requested": True, "automatic": True})
    elif family == "NARRATOR":
        candidate["narrator_contract"]["replacement"] = True
    elif family == "QURAN":
        candidate["quran_contract"]["llm_reconstruction"] = True
    elif family == "MUSIC":
        candidate["audio_tracks"] = [{"kind": "MUSIC", "contains_music": True}]
    elif family == "SFX":
        candidate["sfx_contract"]["false_factual_presentation"] = True
    elif family == "TIMELINE":
        candidate["timeline"]["duration_ticks"] += 1
    elif family == "CAPTIONS":
        candidate["burned_captions"] = True
    elif family == "MONTAGE":
        candidate["montage_contract"]["render_hashes_match"] = False
    elif family == "BRAND":
        candidate["brand_contract"]["intro_count"] = 2
    elif family == "PLACEMENT":
        candidate["placement_contract"]["outro_after_core_end"] = False
    elif family == "FINAL_QA":
        candidate["final_qa_contract"]["technical_qa_pass"] = False
    elif family == "PUBLICATION":
        candidate["publication_contract"]["siraj_generates_thumbnail"] = True
    elif family == "PAID":
        candidate["paid_contract"]["origin"] = "CLI"
    elif family == "COST":
        candidate["cost_authorization"]["estimated_cost"] = 3.0
    elif family == "UNKNOWN":
        candidate["submission_state"] = "SUBMISSION_UNKNOWN"
        candidate["resubmit"] = True
    elif family == "HISTORICAL_UNKNOWN":
        candidate["historical_unknown_contract"]["status"] = "FAILED"
    elif family == "IDEMPOTENCY":
        candidate["transaction_contract"]["duplicate"] = True
    elif family == "RECOVERY":
        candidate["recovery_contract"]["paid_capability"] = True
    elif family == "GOVERNANCE":
        candidate["governance_contract"]["machine_rule_source_count"] = 2
    elif family == "COVERAGE":
        candidate["coverage_contract"]["covered_rules"] = 50
    elif family == "CAPABILITY":
        candidate["capability_contract"]["tests_production_network"] = True
    elif family == "APPEND_ONLY":
        candidate["ledger_contract"]["historical_mutation"] = True
    else:
        raise AssertionError(f"unhandled validator binding: {name}={family}")
    return candidate


def _validator_can_be_forced_to_block(validators: ValidatorRegistry, name: str, artifact: dict) -> bool:
    return validators.validate(name, _bad_artifact_for_validator(validators, name, artifact)).status == "BLOCKED"


@pytest.mark.parametrize("rule_index", range(51))
def test_all_rules_have_positive_enforcement(registry, rule_index: int) -> None:
    rule = list(registry.by_id.values())[rule_index]
    validators = ValidatorRegistry(registry)
    artifact = build_rule_test_artifact(rule, registry.constitution)
    findings = validators.validate_rule(rule["id"], artifact)
    assert findings
    assert all(finding.status == "PASS" for finding in findings)


def test_all_declared_validators_have_real_bindings(registry) -> None:
    validators = ValidatorRegistry(registry)
    assert validators.declared
    assert {name for name in validators.declared if validators.binding_kind(name) == "MISSING"} == set()


@pytest.mark.parametrize("rule_index", range(51))
def test_all_rules_fail_closed_without_required_evidence(registry, rule_index: int) -> None:
    rule = list(registry.by_id.values())[rule_index]
    validators = ValidatorRegistry(registry)
    artifact = build_rule_test_artifact(rule, registry.constitution)
    assert any(_validator_can_be_forced_to_block(validators, name, artifact) for name in rule["validators"])


def _valid_paid_envelope(**changes) -> PaidExecutionEnvelope:
    values = {
        "origin": "DESKTOP",
        "desktop_click_nonce": "CLICK-1",
        "authorization_id": "AUTH-1",
        "authorization_consumed": False,
        "payload_sha256": "a" * 64,
        "approved_payload_sha256": "a" * 64,
        "reference_sha256s": ("b" * 64,),
        "approved_reference_sha256s": ("b" * 64,),
        "provider": "VEO_3_1_LITE",
        "model": "UNBOUND_OFFLINE_PROFILE",
        "provider_profile_approved": True,
        "pilot_coverage_approved": True,
        "estimated_cost": 1.0,
        "authorized_max_cost": 2.0,
        "approvals_stale": False,
        "submission_state": "REQUEST_NOT_SENT",
        "transaction_id": "TX-1",
    }
    values.update(changes)
    return PaidExecutionEnvelope(**values)


@pytest.mark.parametrize("origin", ["TERMINAL", "CLI", "RECOVERY", "TEST"])
def test_non_desktop_paid_origins_block(origin: str) -> None:
    assert evaluate_paid_execution_envelope(_valid_paid_envelope(origin=origin)).status == "BLOCKED"


@pytest.mark.parametrize(
    "changes",
    (
        {"desktop_click_nonce": ""},
        {"authorization_consumed": True},
        {"approved_payload_sha256": "c" * 64},
        {"approved_reference_sha256s": ("c" * 64,)},
        {"provider_profile_approved": False},
        {"pilot_coverage_approved": False},
        {"estimated_cost": 3.0},
        {"approvals_stale": True},
        {"submission_state": "SUBMISSION_UNKNOWN"},
        {"transaction_id": ""},
    ),
)
def test_paid_envelope_adversarial_cases_block(changes: dict) -> None:
    assert evaluate_paid_execution_envelope(_valid_paid_envelope(**changes)).status == "BLOCKED"


def test_exact_approved_fake_desktop_transaction_is_gate_only() -> None:
    executor = FakePaidExecutor()
    result = executor.execute(_valid_paid_envelope())
    assert result["status"] == "FAKE_ACCEPTED_BY_GATE_ONLY"
    assert result["provider_calls"] == result["paid_calls"] == result["network_calls"] == 0
    assert result["production_authorized"] is False
    with pytest.raises(Exception, match="FAIL_DUPLICATE_PAID_TRANSACTION"):
        executor.execute(_valid_paid_envelope())


def test_duplicate_desktop_click_nonce_is_rejected() -> None:
    executor = FakePaidExecutor()
    executor.execute(_valid_paid_envelope())
    with pytest.raises(Exception, match="FAIL_DUPLICATE_DESKTOP_CLICK"):
        executor.execute(
            _valid_paid_envelope(transaction_id="TX-2", authorization_id="AUTH-2")
        )


def test_reused_authorization_id_is_rejected() -> None:
    executor = FakePaidExecutor()
    executor.execute(_valid_paid_envelope())
    with pytest.raises(Exception, match="FAIL_AUTHORIZATION_REUSED"):
        executor.execute(
            _valid_paid_envelope(transaction_id="TX-2", desktop_click_nonce="CLICK-2")
        )
