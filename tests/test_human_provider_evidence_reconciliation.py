from __future__ import annotations

from pathlib import Path
import shutil

from src.application.artifact_provenance_v1 import (
    append_jsonl,
    canonical_sha256,
    read_jsonl,
    sha256_file,
)
from src.application.desktop_provider_execution_v1 import (
    CanonicalDesktopProviderExecutionExecutor,
    ProviderExecutionBinding,
    _attempt_id,
    reconcile_unknown_attempt,
)
from src.application.provider_attempt_reconciliation_v1 import (
    HUMAN_PROVIDER_ACCOUNT_REVIEW,
    NOT_SUBMITTED_ELIGIBLE,
    PROVEN_NOT_CHARGED,
    PROVEN_NOT_SUBMITTED,
    append_human_provider_account_review,
    reconciliation_ledger_path,
)


EPISODE = "fixture-episode"
ATTEMPT = "1e6d0013-d37f-5df7-ab53-444c4f17c14c"
REQUEST = "EP002-SH-001-V01"


def _paths(root: Path) -> tuple[Path, Path]:
    orchestration = root / "projects" / EPISODE / "orchestration"
    ledger = orchestration / "episode-transition-ledger-v1.jsonl"
    attempts = orchestration / "provider-execution-v1" / (
        "provider-execution-attempt-receipts-v1.jsonl"
    )
    ledger.parent.mkdir(parents=True, exist_ok=True)
    attempts.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text('{"stage":"PROVIDER_EXECUTION","status":"READY"}\n', encoding="utf-8")
    append_jsonl(
        attempts,
        {
            "schema_version": "siraj-desktop-provider-execution-v1",
            "status": "UNKNOWN",
            "episode_id": EPISODE,
            "stage": "PROVIDER_EXECUTION",
            "attempt_id": ATTEMPT,
            "unit_id": REQUEST,
            "request_id": REQUEST,
            "provider": "RUNWARE",
            "model": "google:veo@3.1-lite",
            "provider_operation_id": None,
        },
    )
    return ledger, attempts


def _append_evidence(root: Path) -> dict[str, object]:
    ledger = root / "projects" / EPISODE / "orchestration" / "episode-transition-ledger-v1.jsonl"
    if not ledger.is_file():
        ledger, _ = _paths(root)
    return append_human_provider_account_review(
        root,
        EPISODE,
        historical_attempt_id=ATTEMPT,
        provider_request_id=REQUEST,
        shot_id="EP002-SH-001",
        media_unit_id=REQUEST,
        provider="RUNWARE",
        model="google:veo@3.1-lite",
        media_type="VIDEO",
        planned_cost_usd=0.4,
        original_invalid_planning_task_uuid="planning-only-23fd9f353315ea244f26e1940c4fe737",
        historical_evidence={
            "review_type": "RUNWARE_ACCOUNT_HISTORY_REVIEW",
            "finding": "NO_EPISODE_002_OPERATION_PRESENT",
            "visible_completed_operations": "EPISODE_001_ONLY",
        },
        binding={"ledger_head_sha256": sha256_file(ledger), "cost_envelope_usd": 25.9009},
        historical_evidence_references={
            "classification": HUMAN_PROVIDER_ACCOUNT_REVIEW,
            "api_lookup_performed": False,
        },
    )


def test_human_evidence_clears_unknown_without_rewriting_history(tmp_path: Path) -> None:
    _, attempts = _paths(tmp_path)
    historical_hash = sha256_file(attempts)
    receipt = _append_evidence(tmp_path)
    result = reconcile_unknown_attempt(tmp_path, EPISODE, ATTEMPT)
    assert result["status"] == PROVEN_NOT_SUBMITTED
    assert result["charge_status"] == PROVEN_NOT_CHARGED
    assert result["request_status"] == NOT_SUBMITTED_ELIGIBLE
    assert result["lookup_performed"] is False
    assert result["historical_unknown_preserved"] is True
    assert result["historical_attempt_spend_usd"] == 0.0
    assert result["planned_future_request_cost_usd"] == 0.4
    assert result["reconciliation_receipt"]["receipt_id"] == receipt["receipt_id"]
    assert sha256_file(attempts) == historical_hash


def test_duplicate_human_evidence_is_idempotent_and_not_a_retry(tmp_path: Path) -> None:
    first = _append_evidence(tmp_path)
    second = _append_evidence(tmp_path)
    assert first["receipt_id"] == second["receipt_id"]
    rows = read_jsonl(reconciliation_ledger_path(tmp_path, EPISODE))
    assert len(rows) == 1
    assert rows[0]["attempt_ordinal_consumed"] is False
    assert rows[0]["paid_attempts_created"] == 0


def test_reconcile_projection_has_no_unknown_blocker(tmp_path: Path) -> None:
    _append_evidence(tmp_path)
    projection = CanonicalDesktopProviderExecutionExecutor(
        tmp_path,
        EPISODE,
    ).reconcile()
    assert projection["request_states"][REQUEST] == NOT_SUBMITTED_ELIGIBLE
    assert REQUEST in projection["not_submitted_requests_eligible"]
    assert REQUEST not in projection["blocked_requests"]
    assert REQUEST not in projection["request_attempts"]
    assert ATTEMPT not in projection["unknown_attempts"]
    assert projection["unknown_blocking_requests"] == []


def test_future_first_submission_identity_differs_from_historical_attempt() -> None:
    binding = ProviderExecutionBinding(
        episode_id=EPISODE,
        stage="PROVIDER_EXECUTION",
        preflight_file_sha256="a" * 64,
        preflight_payload_sha256="b" * 64,
        media_plan_sha256="c" * 64,
        provider_request_plan_sha256="d" * 64,
        pricing_registry_sha256="e" * 64,
        pricing_registry_version="v2",
        reack_receipt_id="reack",
        maximum_cost=25.9009,
        currency="USD",
        ledger_head_sha256="f" * 64,
        creative_overlay_sha256="1" * 64,
        structural_fingerprint="2" * 64,
        request_plan_hash="d" * 64,
    )
    unit = {
        "unit_id": REQUEST,
        "request_id": REQUEST,
        "provider": "RUNWARE",
        "model": "google:veo@3.1-lite",
        "payload_sha256": "3" * 64,
    }
    historical = _attempt_id(binding, unit)
    fresh = _attempt_id(binding, unit, first_submission_reconciliation_id="receipt-1")
    assert fresh != historical


def test_copied_receipt_with_stale_ledger_does_not_clear_unknown(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    _append_evidence(source)
    target_ledger, target_attempts = _paths(target)
    target_ledger.write_text(
        target_ledger.read_text(encoding="utf-8")
        + '{"stage":"OTHER","status":"CHANGED"}\n',
        encoding="utf-8",
    )
    source_receipt = reconciliation_ledger_path(source, EPISODE)
    target_receipt = reconciliation_ledger_path(target, EPISODE)
    target_receipt.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_receipt, target_receipt)
    assert sha256_file(target_attempts)
    result = reconcile_unknown_attempt(target, EPISODE, ATTEMPT)
    assert result["status"] == "SUBMISSION_STATUS_UNKNOWN"
    assert result["lookup_performed"] is False
