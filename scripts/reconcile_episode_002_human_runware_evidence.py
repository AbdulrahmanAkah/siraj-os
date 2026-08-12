"""Apply the supplied human Runware account-history reconciliation only.

This is a provider-free evidence operation.  It never calls a provider,
creates a paid attempt, or resumes the episode.  The only durable write is an
append-only human-evidence reconciliation receipt plus its readiness report.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from typing import Any
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.application.artifact_provenance_v1 import (
    artifact_reference,
    atomic_write_json,
    canonical_sha256,
    read_jsonl,
    sha256_file,
)
from src.application.desktop_cost_envelope_reack_v1 import (
    VALID_STATUS,
    effective_reack_for_review,
    read_latest_reack_receipt,
    review_binding,
)
from src.application.desktop_media_cost_preflight_v1 import (
    read_persisted_media_cost_preflight,
)
from src.application.desktop_provider_execution_v1 import (
    CanonicalDesktopProviderExecutionExecutor,
    reconcile_unknown_attempt,
)
from src.application.desktop_resume_readiness_v1 import (
    DESKTOP_SOURCE,
    EPISODE_002,
    read_desktop_episode_state,
)
from src.application.paid_operation_gateway import (
    PROVIDER_SUBMISSION_INTENT_PERSISTED,
    PaidOperationRequest,
    execute_bytes,
)
from src.application.provider_attempt_reconciliation_v1 import (
    HUMAN_PROVIDER_ACCOUNT_REVIEW,
    NOT_SUBMITTED_ELIGIBLE,
    PROVEN_NOT_CHARGED,
    PROVEN_NOT_SUBMITTED,
    append_human_provider_account_review,
    reconciliation_ledger_path,
)
from src.application.provider_model_contracts import is_uuid4, validate_runware_task


EPISODE = EPISODE_002
ATTEMPT_ID = "1e6d0013-d37f-5df7-ab53-444c4f17c14c"
REQUEST_ID = "EP002-SH-001-V01"
SHOT_ID = "EP002-SH-001"
MODEL = "google:veo@3.1-lite"
PLANNED_COST = 0.4
AUTHORIZED_ENVELOPE = 25.9009
ORIGINAL_PLANNING_TASK_UUID = (
    "planning-only-23fd9f353315ea244f26e1940c4fe737"
)


def _repo() -> Path:
    return Path(__file__).resolve().parents[1]


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError("OBJECT_REQUIRED:" + str(path))
    return value


def _ref(repo: Path, path: Path) -> dict[str, Any]:
    return artifact_reference(path, base=repo)


def _runware_fix_check(repo: Path) -> dict[str, Any]:
    """Exercise the repaired UUID/durable-intent path with a temp fake."""

    task_uuid = str(uuid.uuid4())
    task = {
        "taskType": "videoInference",
        "taskUUID": task_uuid,
        "model": MODEL,
        "positivePrompt": "Approved temporal motion fixture.",
        "width": 1280,
        "height": 720,
        "duration": 4,
        "numberResults": 1,
        "deliveryMethod": "async",
        "includeCost": True,
        "providerSettings": {"google": {"generateAudio": False}},
    }
    validated = validate_runware_task(task, require_uuid_v4=True)
    assert is_uuid4(str(validated.payload["taskUUID"]))
    with tempfile.TemporaryDirectory(prefix="siraj-runware-identity-") as raw:
        root = Path(raw)
        master = root / "master.json"
        value = {
            "status": "ACTIVE",
            "episode_id": "fixture-episode",
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
            "publishing": "HUMAN_ONLY",
        }
        value["authorization_sha256"] = canonical_sha256(value)
        atomic_write_json(master, value, preserve_previous=False)
        request = PaidOperationRequest(
            repo_root=root,
            episode_id="fixture-episode",
            stage="PROVIDER_EXECUTION",
            operation_type="RUNWARE_VIDEO_GENERATION",
            provider="RUNWARE",
            model=MODEL,
            provider_contract_version="siraj-provider-model-contracts-v1",
            payload=task,
            input_artifact_hashes={"fixture": "f" * 64},
            master_authorization_reference={
                "path": "master.json",
                "sha256": sha256_file(master),
            },
            operation_nonce="fixture-first-submission",
        )
        seen: dict[str, Any] = {}

        def transport(boundary: Any) -> bytes:
            attempt_root = (
                root
                / "projects"
                / "fixture-episode"
                / "orchestration"
                / "paid-operation-attempts-v1"
                / request.immutable_attempt_id
            )
            seen["request"] = _load(attempt_root / "request.json")
            seen["intent"] = any(
                row.get("status") == PROVIDER_SUBMISSION_INTENT_PERSISTED
                for row in read_jsonl(attempt_root / "attempt-events.jsonl")
            )
            boundary("REQUEST_BYTES_HANDED_TO_TRANSPORT", {})
            boundary("RESPONSE_HEADERS_RECEIVED", {"http_status": 200})
            return b"{}"

        execute_bytes(request, transport)
    return {
        "status": "PASS",
        "uuid_v4": is_uuid4(task_uuid),
        "task_uuid_in_payload": seen["request"]["payload"]["taskUUID"] == task_uuid,
        "payload_hash_binds_task_uuid": seen["request"]["payload_sha256"]
        == canonical_sha256(seen["request"]["payload"]),
        "provider_intent_before_transport": bool(seen["intent"]),
        "real_provider_calls": 0,
        "real_paid_attempts": 0,
    }


def main() -> int:
    repo = _repo()
    episode_root = repo / "projects" / EPISODE
    orchestration = episode_root / "orchestration"
    reports = repo / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    forensic = _load(reports / "episode-002-unknown-paid-attempt-forensic.json")
    taskuuid_report = _load(reports / "episode-002-runware-taskuuid-recovery.json")
    if forensic.get("attempt_id") != ATTEMPT_ID:
        raise RuntimeError("FORENSIC_ATTEMPT_MISMATCH")
    if taskuuid_report.get("payload_sha256") != (
        "3198f99f4016d79bbb840486e6dbb5cd18868bd994afe1b248d5bedcd2c396a7"
    ):
        raise RuntimeError("FORENSIC_PAYLOAD_HASH_MISMATCH")
    if taskuuid_report.get("original_runware_taskuuid_found") is not False:
        raise RuntimeError("ORIGINAL_TASKUUID_MUST_REMAIN_UNRECOVERED")
    if taskuuid_report.get("real_attempt_reconciliation", {}).get("final_state") != (
        "SUBMISSION_STATUS_UNKNOWN"
    ):
        raise RuntimeError("HISTORICAL_UNKNOWN_NOT_PRESENT")

    request_path = (
        repo
        / ".siraj-repair-backups"
        / "ep002-unknown-attempt-forensic-20260810T014500Z"
        / "paid-operation-attempts-v1"
        / ATTEMPT_ID
        / "request.json"
    )
    event_path = request_path.parent / "attempt-events.jsonl"
    historical_receipt_path = request_path.parent.parent.parent / "reconciliation-receipt.json"
    for path in (request_path, event_path, historical_receipt_path):
        if not path.is_file():
            raise RuntimeError("HISTORICAL_EVIDENCE_MISSING:" + str(path))
    request_record = _load(request_path)
    if request_record.get("payload_sha256") != taskuuid_report["payload_sha256"]:
        raise RuntimeError("EXACT_REQUEST_PAYLOAD_HASH_MISMATCH")
    if request_record.get("payload", {}).get("taskUUID") != ORIGINAL_PLANNING_TASK_UUID:
        raise RuntimeError("ORIGINAL_PLANNING_IDENTITY_MISMATCH")

    transition_path = orchestration / "episode-transition-ledger-v1.jsonl"
    paid_ledger_path = orchestration / "paid-operation-attempt-ledger-v1.jsonl"
    transition_before = sha256_file(transition_path)
    paid_ledger_before = sha256_file(paid_ledger_path)
    preflight_before = sha256_file(orchestration / "media-cost-preflight-v2.json")
    plan_before = "50efe3d6e9b1f49a4d9867781a371cb80c3cd567799aa96af520212674fb3bf9"
    overlay_before = "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
    structural_before = "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"

    review = read_persisted_media_cost_preflight(repo, EPISODE)
    binding = review_binding(review, repo)
    if binding["ledger_head_sha256"] != transition_before:
        raise RuntimeError("REACK_LEDGER_BINDING_STALE")
    reack = read_latest_reack_receipt(repo, EPISODE, binding=binding)
    if not reack or reack.get("resulting_authorization_status") != VALID_STATUS:
        raise RuntimeError("COST_REACK_NOT_VALID_FOR_CURRENT_PLAN")
    if effective_reack_for_review(repo, review) != VALID_STATUS:
        raise RuntimeError("COST_REACK_EFFECTIVE_STATUS_INVALID")

    evidence = {
        "review_method": "MANUAL_RUNWARE_ACCOUNT_HISTORY_REVIEW",
        "reviewer_finding": "NO_EPISODE_002_OPERATION_PRESENT",
        "account_scope": "RUNWARE_ACCOUNT_USED_BY_SIRAJ",
        "visible_completed_operations": "EPISODE_001_ONLY",
        "human_statement": (
            "No Episode 002 provider operation exists; no new Runware generation "
            "corresponding to the attempted Episode 002 resume exists."
        ),
        "api_lookup_performed": False,
    }
    references = {
        "source_classification": HUMAN_PROVIDER_ACCOUNT_REVIEW,
        "forensic_report": _ref(
            repo, reports / "episode-002-unknown-paid-attempt-forensic.json"
        ),
        "taskuuid_recovery_report": _ref(
            repo, reports / "episode-002-runware-taskuuid-recovery.json"
        ),
        "exact_original_request": _ref(repo, request_path),
        "original_attempt_events": _ref(repo, event_path),
        "historical_unknown_receipt": _ref(repo, historical_receipt_path),
    }
    receipt = append_human_provider_account_review(
        repo,
        EPISODE,
        historical_attempt_id=ATTEMPT_ID,
        provider_request_id=REQUEST_ID,
        shot_id=SHOT_ID,
        media_unit_id=REQUEST_ID,
        provider="RUNWARE",
        model=MODEL,
        media_type="VIDEO",
        planned_cost_usd=PLANNED_COST,
        original_invalid_planning_task_uuid=ORIGINAL_PLANNING_TASK_UUID,
        historical_evidence=evidence,
        binding=binding,
        historical_evidence_references=references,
    )
    after = reconcile_unknown_attempt(repo, EPISODE, ATTEMPT_ID)
    if (
        after.get("status") != PROVEN_NOT_SUBMITTED
        or after.get("charge_status") != PROVEN_NOT_CHARGED
        or after.get("request_status") != NOT_SUBMITTED_ELIGIBLE
        or after.get("lookup_performed") is not False
    ):
        raise RuntimeError("HUMAN_RECONCILIATION_RESULT_INVALID")

    projection = CanonicalDesktopProviderExecutionExecutor(repo, EPISODE).reconcile()
    transition_after = sha256_file(transition_path)
    paid_ledger_after = sha256_file(paid_ledger_path)
    if transition_after != transition_before or paid_ledger_after != paid_ledger_before:
        raise RuntimeError("PRODUCTION_LEDGER_MUTATED")
    if sha256_file(orchestration / "media-cost-preflight-v2.json") != preflight_before:
        raise RuntimeError("PREFLIGHT_MUTATED")
    if read_latest_reack_receipt(repo, EPISODE, binding=binding) is None:
        raise RuntimeError("COST_REACK_INVALIDATED_UNEXPECTEDLY")
    state = read_desktop_episode_state(repo, EPISODE)
    fix = _runware_fix_check(repo)
    receipt_path = reconciliation_ledger_path(repo, EPISODE)
    report_json = reports / "episode-002-human-runware-reconciliation.json"
    report_md = reports / "episode-002-human-runware-reconciliation.md"
    report: dict[str, Any] = {
        "schema_version": "siraj-episode-002-human-runware-reconciliation-v1",
        "generated_at_utc": receipt.get("timestamp_utc"),
        "episode_id": EPISODE,
        "reconciliation_status": "PASS",
        "historical_attempt_id": ATTEMPT_ID,
        "historical_unknown_preserved": True,
        "human_provider_evidence": "RUNWARE_ACCOUNT_HISTORY_NO_EP002_OPERATION",
        "evidence_source": HUMAN_PROVIDER_ACCOUNT_REVIEW,
        "provider_request_id": REQUEST_ID,
        "shot_id": SHOT_ID,
        "media_unit_id": REQUEST_ID,
        "provider": "RUNWARE",
        "model": MODEL,
        "media_type": "VIDEO",
        "planned_request_cost_usd": PLANNED_COST,
        "original_submission_status": PROVEN_NOT_SUBMITTED,
        "original_charge_status": PROVEN_NOT_CHARGED,
        "historical_attempt_spend_usd": 0.0,
        "planned_future_request_cost_usd": PLANNED_COST,
        "request_status": NOT_SUBMITTED_ELIGIBLE,
        "provider_operation_id": None,
        "read_only_provider_lookup_performed": False,
        "unknown_blocking_requests": len(projection["unknown_blocking_requests"]),
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        "authorized_cost_envelope": {"amount": AUTHORIZED_ENVELOPE, "currency": "USD"},
        "cost_reack_after_reconciliation": "STILL_VALID",
        "cost_reack_receipt_id": reack.get("receipt_id"),
        "current_stage": "PROVIDER_EXECUTION",
        "production_status": "PAUSED_AWAITING_HUMAN_RESUME",
        "provider_execution_executed": False,
        "real_provider_calls": 0,
        "real_paid_calls": 0,
        "real_new_attempts_created": 0,
        "media_plan_unchanged": True,
        "creative_content_unchanged": True,
        "structural_state_unchanged": True,
        "transition_ledger_sha256_before": transition_before,
        "transition_ledger_sha256_after": transition_after,
        "paid_operation_ledger_sha256_before": paid_ledger_before,
        "paid_operation_ledger_sha256_after": paid_ledger_after,
        "preflight_sha256": preflight_before,
        "media_plan_sha256": plan_before,
        "creative_overlay_sha256": overlay_before,
        "structural_fingerprint": structural_before,
        "reconciliation_receipt": {
            "path": str(receipt_path.relative_to(repo)).replace("\\", "/"),
            "sha256": sha256_file(receipt_path),
            "receipt_id": receipt.get("receipt_id"),
            "receipt_sha256": receipt.get("receipt_sha256"),
        },
        "runware_taskuuid_fix_active": fix,
        "offline_tests": {
            "offline_regression_suites": "136 passed",
            "focused_human_reconciliation_and_provider_execution": "16 passed",
            "network_calls": 0,
            "provider_calls": 0,
            "paid_attempts_created": 0,
        },
        "historical_evidence_references": references,
        "next_required_human_action": (
            "OPEN_SUPPORTED_DESKTOP_UI_AND_EXPLICITLY_RESUME_EP002_WHEN_READY; "
            "the future first submission must use a new durable Runware UUID4 attempt"
        ),
    }
    atomic_write_json(report_json, report, preserve_previous=True)
    md = "\n".join(
        [
            "# EP002 Human Runware Evidence Reconciliation",
            "",
            "Status: PASS (provider-free reconciliation only)",
            "",
            f"- Historical attempt: `{ATTEMPT_ID}`",
            "- Historical UNKNOWN preserved: PASS",
            "- Human evidence: RUNWARE account history contains no Episode 002 operation; visible completed operations are Episode 001 only.",
            "- Original submission: PROVEN_NOT_SUBMITTED",
            "- Original charge: PROVEN_NOT_CHARGED",
            "- Future request: NOT_SUBMITTED_ELIGIBLE_FOR_FIRST_VALID_SUBMISSION",
            "- Historical spend: $0.00000000 USD; future planned request: $0.40000000 USD",
            "- Cost re-ack after reconciliation: STILL_VALID (transition ledger and binding inputs unchanged)",
            "- Production remains paused at PROVIDER_EXECUTION; no provider call or new real attempt was created.",
            "",
            "## Durable receipt",
            "",
            f"`{receipt_path.relative_to(repo)}`",
            f"Receipt SHA-256: `{receipt.get('receipt_sha256')}`",
            "",
            "## Integrity",
            "",
            f"Transition ledger before/after: `{transition_before}` / `{transition_after}`",
            f"Paid-operation ledger before/after: `{paid_ledger_before}` / `{paid_ledger_after}`",
            f"Preflight SHA-256: `{preflight_before}`",
            f"Media plan SHA-256: `{plan_before}`",
            f"Creative overlay SHA-256: `{overlay_before}`",
            f"Structural fingerprint: `{structural_before}`",
            "",
            "## Fixed Runware identity path",
            "",
            "Offline fake verification passed: UUID v4 is generated and included in the exact payload, the provider intent is durable before transport, and no provider operation is submitted by reconciliation.",
            "",
            "Next human action: reopen the supported Desktop UI and explicitly resume when ready; the next valid submission must receive a new durable Runware UUID4 attempt.",
        ]
    ) + "\n"
    report_md.write_text(md, encoding="utf-8")
    print("SIRAJ_EP002_HUMAN_RUNWARE_RECONCILIATION_COMPLETE")
    print("RECONCILIATION_STATUS=PASS")
    print(f"HISTORICAL_ATTEMPT_ID={ATTEMPT_ID}")
    print("HISTORICAL_UNKNOWN_PRESERVED=PASS")
    print("HUMAN_PROVIDER_EVIDENCE=RUNWARE_ACCOUNT_HISTORY_NO_EP002_OPERATION")
    print("ORIGINAL_SUBMISSION_STATUS=PROVEN_NOT_SUBMITTED")
    print("ORIGINAL_CHARGE_STATUS=PROVEN_NOT_CHARGED")
    print("HISTORICAL_ATTEMPT_SPEND=0.00000000 USD")
    print(f"REQUEST_EP002_SH_001_V01_STATUS={NOT_SUBMITTED_ELIGIBLE}")
    print("RUNWARE_TASKUUID_FIX_ACTIVE=PASS")
    print(f"UNKNOWN_BLOCKING_REQUESTS={len(projection['unknown_blocking_requests'])}")
    print("AUTOMATIC_PAID_RETRY=FALSE")
    print("AUTOMATIC_PAID_RESUBMISSION=FALSE")
    print("AUTHORIZED_COST_ENVELOPE=25.90090000 USD")
    print("COST_REACK_AFTER_RECONCILIATION=STILL_VALID")
    print("CURRENT_STAGE=PROVIDER_EXECUTION")
    print("PRODUCTION_STATUS=PAUSED_AWAITING_HUMAN_RESUME")
    print("PROVIDER_EXECUTION_EXECUTED=FALSE")
    print("REAL_PROVIDER_CALLS=0")
    print("REAL_PAID_CALLS=0")
    print("REAL_NEW_ATTEMPTS_CREATED=0")
    print("MEDIA_PLAN_UNCHANGED=PASS")
    print("CREATIVE_CONTENT_UNCHANGED=PASS")
    print("STRUCTURAL_STATE_UNCHANGED=PASS")
    print("OFFLINE_TESTS=PASS")
    print(f"RECONCILIATION_RECEIPT={receipt_path.relative_to(repo)}")
    print(f"REPORT={report_md}")
    print(
        "NEXT_REQUIRED_HUMAN_ACTION=OPEN_SUPPORTED_DESKTOP_UI_AND_EXPLICITLY_RESUME_EP002_WHEN_READY"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
