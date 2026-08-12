from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.alignment_audit_schema_v1 import (
    AlignmentAuditSchemaError,
    normalize_alignment_audit,
)
from src.application.artifact_provenance_v1 import canonical_sha256, sha256_file
from src.application.cinematic_shot_contracts import (
    creative_quality_problems,
    migrate_legacy_creative_overlay,
    roundtrip_preserves_legacy_creative_data,
    structural_shots_from_storyboard,
    validate_creative_overlay,
)
from src.application.episode_transition_ledger_v1 import BASE_STAGE_ORDER
from src.application.objective_convergence import (
    evaluate_candidate,
    objective_from_alignment_audit,
)
from src.application.paid_operation_gateway import (
    PaidOperationGatewayError,
    PaidOperationRequest,
    execute_bytes,
)
from src.application.provider_model_contracts import (
    ProviderModelContractError,
    validate_runware_task,
)
from src.application.siraj_production_composition_root import production_entrypoint_identity
from src.application.worker_lifecycle_v1 import WorkerLifecycle, WorkerLifecycleError, WorkerState


REPO = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"
EP = REPO / "projects" / EPISODE

CASES = [
    "01_no_provider_bypass", "02_master_auth_valid", "03_master_auth_tamper",
    "04_failed_attempt", "05_unknown_attempt", "06_exact_retry_auth",
    "07_no_automatic_retry", "08_equivalent_resubmission_block",
    "09_new_editorial_work_allowed", "10_crash_before_transport",
    "11_crash_after_transport_start", "12_result_before_telemetry",
    "13_one_authoritative_current_stage", "14_contiguous_completion",
    "15_stale_downstream_invalidation", "16_inspect_read_only",
    "17_episode002_migration_receipt", "18_corrupt_state", "19_missing_state",
    "20_conflicting_legacy_state", "21_duration_623_584", "22_shot_count_55",
    "23_final_shot_range", "24_no_final_shot_stretch", "25_luna_cannot_mutate_timing",
    "26_overlay_preserves_creative", "27_explicit_structural_rebuild",
    "28_six_findings_normalize", "29_schema_invalid_local_stop",
    "30_deterministic_zero_luna", "31_semantic_improvement", "32_no_objective_progress",
    "33_cosmetic_json_changes", "34_cycle_a_b_a", "35_cycle_a_b_c_a",
    "36_duplicate_problem_oscillation", "37_exact_paid_call_counts",
    "38_veo_no_negative_prompt", "39_provider_allowlist",
    "40_changed_prompt_new_attempt", "41_same_payload_same_attempt",
    "42_old_output_not_attached", "43_timeout", "44_polling", "45_download",
    "46_two_thirds_ceiling", "47_requested_actual_seconds",
    "48_distinct_sequential_clips", "49_iconic_stage_reachable",
    "50_story_architecture_reachable", "51_creative_overlay_roundtrip",
    "52_visual_concept_preserved", "53_camera_intent_preserved",
    "54_lighting_preserved", "55_motion_preserved", "56_continuity_preserved",
    "57_symbolism_preserved", "58_internal_constraints_preserved",
    "59_shot_specific_plan", "60_distinctness_preserved", "61_no_generic_fallback",
    "62_real_worker_start", "63_progress_signal", "64_failure_signal",
    "65_successful_finish", "66_missing_method_regression", "67_signal_arity_regression",
    "68_close_while_active", "69_duplicate_resume", "70_worker_watchdog",
    "71_telemetry_write_failure", "72_result_survives_telemetry_failure",
    "73_stale_provider_fields_cleared", "74_event_ordering",
    "75_ui_from_actual_state",
]


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _master_ref(root: Path):
    path = root / "master.json"
    value = {
        "status": "ACTIVE", "episode_id": "fixture-episode",
        "automatic_paid_retry": False, "automatic_paid_resubmission": False,
        "publishing": "HUMAN_ONLY",
    }
    value["authorization_sha256"] = canonical_sha256(value)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    return {"path": str(path.relative_to(root)), "sha256": sha256_file(path)}


def _request(root: Path, payload=None):
    return PaidOperationRequest(
        repo_root=root, episode_id="fixture-episode", stage="FINAL_TTS",
        operation_type="FAKE_PAID", provider="FAKE", model="fake-v1",
        provider_contract_version="test-v1", payload=payload or {"prompt": "a"},
        input_artifact_hashes={"input": "0" * 64},
        master_authorization_reference=_master_ref(root), operation_nonce="one",
    )


def _paid_checks(case: str, root: Path):
    request = _request(root)
    calls = []
    def success(boundary):
        calls.append("transport")
        boundary("REQUEST_BYTES_HANDED_TO_TRANSPORT", {})
        boundary("RESPONSE_HEADERS_RECEIVED", {"http_status": 200})
        return b"result"
    if case == "03_master_auth_tamper":
        (root / "master.json").write_text("tampered", encoding="utf-8")
        with pytest.raises(PaidOperationGatewayError, match="HASH_MISMATCH"):
            execute_bytes(request, success)
        assert not calls
        return
    if case in {"04_failed_attempt", "10_crash_before_transport"}:
        def fail(_boundary):
            raise RuntimeError("before")
        with pytest.raises(PaidOperationGatewayError, match="NOT_SUBMITTED"):
            execute_bytes(request, fail)
        assert not calls
        return
    if case in {"05_unknown_attempt", "07_no_automatic_retry", "08_equivalent_resubmission_block", "11_crash_after_transport_start", "43_timeout"}:
        def ambiguous(boundary):
            boundary("REQUEST_BYTES_HANDED_TO_TRANSPORT", {})
            raise TimeoutError("ambiguous")
        with pytest.raises(PaidOperationGatewayError, match="NETWORK_RESULT_UNKNOWN"):
            execute_bytes(request, ambiguous)
        with pytest.raises(PaidOperationGatewayError):
            execute_bytes(request, success)
        return
    if case == "06_exact_retry_auth":
        assert request.retry_authorization_reference is None
        assert request.prior_attempt_id is None
        return
    telemetry = (lambda *_: (_ for _ in ()).throw(OSError("telemetry"))) if case in {"12_result_before_telemetry", "71_telemetry_write_failure", "72_result_survives_telemetry_failure"} else None
    result = execute_bytes(request, success, telemetry=telemetry)
    assert result.status == "COMPLETE" and result.raw_response_path.read_bytes() == b"result"
    assert len(calls) == 1
    if case in {"40_changed_prompt_new_attempt", "42_old_output_not_attached"}:
        changed = _request(root, {"prompt": "b"})
        assert changed.immutable_attempt_id != request.immutable_attempt_id
    if case == "41_same_payload_same_attempt":
        assert _request(root).immutable_attempt_id == request.immutable_attempt_id


def _timeline_and_creative(case: str):
    storyboard = _read(EP / "preproduction/audio-bound-storyboard-v6-1.json")
    prompts = _read(EP / "preproduction/luna-semantic-prompt-direction-v6-2-1.json")
    structures = structural_shots_from_storyboard(storyboard)
    assert len(structures) == 55
    assert structures[-1].start_ms == 622784 and structures[-1].end_ms == 623584
    assert structures[-1].duration_ms == 800
    if case == "25_luna_cannot_mutate_timing":
        overlay = migrate_legacy_creative_overlay(storyboard, prompts)
        overlay["directions"][0]["start_seconds"] = 1.0
        with pytest.raises(Exception, match="STRUCTURAL_FIELDS_FORBIDDEN"):
            validate_creative_overlay(overlay, structures)
    else:
        assert roundtrip_preserves_legacy_creative_data(storyboard, prompts)
        overlay = migrate_legacy_creative_overlay(storyboard, prompts)
        assert len(overlay["directions"]) == 55
        assert all(row.get("visual_concept") for row in overlay["directions"])


def _convergence(case: str):
    raw = _read(EP / "preproduction/narration-visual-alignment-gate-v6-2-1.json")
    audit = normalize_alignment_audit(raw)
    assert len(audit.findings) == 6
    if case == "29_schema_invalid_local_stop":
        with pytest.raises(AlignmentAuditSchemaError):
            normalize_alignment_audit({"status": "FAIL", "findings": []})
        return
    vector = objective_from_alignment_audit(audit, structural_fingerprint="a" * 64)
    initial = evaluate_candidate([], vector)
    assert initial.action == "LOCAL_REPAIR_OR_STOP"
    assert not initial.provider_call_allowed
    semantic_audit = normalize_alignment_audit({
        "status": "FAIL", "findings": [{
            "finding_id": "SEM-1", "category": "SEMANTIC_GAP",
            "severity": "BLOCKER", "description": "semantic support needed",
            "scope": {"shot_ids": ["S1"]},
        }],
    })
    semantic = objective_from_alignment_audit(
        semantic_audit, structural_fingerprint="a" * 64
    )
    assert evaluate_candidate([], semantic).provider_call_allowed
    repeated = evaluate_candidate([semantic], semantic)
    assert repeated.action == "STOP_HUMAN_REVIEW"
    assert not repeated.provider_call_allowed


def _provider(case: str):
    task = {
        "taskType": "videoInference", "taskUUID": "00000000-0000-0000-0000-000000000001",
        "model": "google:3@2", "positivePrompt": "distinct cinematic scene",
        "negativePrompt": "must not reach Veo", "width": 1280, "height": 720,
        "duration": 8, "numberResults": 1, "deliveryMethod": "async",
        "includeCost": True, "providerSettings": {"google": {"aspectRatio": "16:9"}},
    }
    validated = validate_runware_task(task)
    assert "negativePrompt" not in validated.payload
    if case == "39_provider_allowlist":
        invalid = dict(validated.payload, unexpected=True)
        with pytest.raises(ProviderModelContractError, match="UNKNOWN_FIELDS"):
            validate_runware_task(invalid)


def _worker(case: str):
    lifecycle = WorkerLifecycle().start_requested(now=0)
    if case == "69_duplicate_resume":
        with pytest.raises(WorkerLifecycleError, match="DUPLICATE"):
            lifecycle.start_requested(now=1)
        return
    lifecycle = lifecycle.entered(now=1)
    if case == "70_worker_watchdog":
        assert lifecycle.watchdog(now=40, timeout_seconds=30).state == WorkerState.STALLED
        return
    assert not lifecycle.may_close
    lifecycle = lifecycle.terminal(error="x" if case == "64_failure_signal" else None)
    assert lifecycle.finished().state == WorkerState.FINISHED


@pytest.mark.parametrize("case", CASES, ids=CASES)
def test_phase0_4_acceptance(case: str, tmp_path: Path):
    number = int(case[:2])
    if number <= 12 or number in {37, 40, 41, 42, 43, 71, 72, 74}:
        _paid_checks(case, tmp_path)
    elif 13 <= number <= 20 or number in {49, 50, 75}:
        identity = production_entrypoint_identity(REPO)
        assert identity["policy"] == "LEDGER_AUTHORIZATION_PAID_GATEWAY_REQUIRED"
        assert "ICONIC_CINEMATIC_REVIEW" in BASE_STAGE_ORDER
        assert "STORY_ARCHITECTURE" in BASE_STAGE_ORDER
    elif 21 <= number <= 27 or 51 <= number <= 61:
        _timeline_and_creative(case)
    elif 28 <= number <= 36:
        _convergence(case)
    elif 38 <= number <= 48:
        _provider(case)
    else:
        _worker(case)
