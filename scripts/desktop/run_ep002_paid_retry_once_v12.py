"""Execute the already-authorized EP002 QA retry exactly once.

The caller must run the offline canonical-identity Desktop gate first.  This
script enters the real Desktop controller once and never retries or submits a
second time, regardless of provider outcome.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import urllib.request
from typing import Any

from src.application.artifact_provenance_v1 import canonical_sha256, sha256_file
from src.application.desktop_resume_readiness_v1 import (
    DESKTOP_SOURCE,
    DesktopProductionResumeController,
    read_desktop_episode_state,
)


EPISODE = "episode-002-adam-temptation-fall-repentance"
STAGE = "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA"
NEW_ATTEMPT_ID = "2dee08f3-6a36-44cb-91b1-104f49ddcca4"
PRIOR_ATTEMPT_ID = "0caccb03-31b4-4739-90f5-90286d344882"
EXPECTED_HEAD = "05a29e527f3a1ee133369278281598fb4a479978"
EXPECTED_BRANCH = "feature/series-production-quality-v2"
EXPECTED_IDENTITY = (
    "ea94f7e5ccbb05c139e050ad527955e3eb2d72541eb90d5c0a03bd3cf12d004d"
)
EXPECTED_PROVIDER_PAYLOAD = (
    "9941ff57915a5470beffb4b3fa1fdb8d9e33bef3ad576076c25e9a5148ee39a5"
)
EXPECTED_INPUT = (
    "dd1700e1ae1d4a5bee517279ae24d6ee68532ee02f1583a323c18cdc3a4c6fdf"
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _sha(path: Path) -> str | None:
    return sha256_file(path) if path.is_file() else None


def _file_snapshot(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False, "bytes": 0, "sha256": None}
    return {
        "present": True,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _directory_manifest(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        return {"present": False, "file_count": 0, "manifest_sha256": None}
    entries: list[dict[str, Any]] = []
    for child in sorted(path.rglob("*")):
        if child.is_file():
            entries.append(
                {
                    "path": str(child.relative_to(path)).replace("\\", "/"),
                    "bytes": child.stat().st_size,
                    "sha256": sha256_file(child),
                }
            )
    return {
        "present": True,
        "file_count": len(entries),
        "total_bytes": sum(item["bytes"] for item in entries),
        "manifest_sha256": canonical_sha256(entries),
    }


def _direct_attempt_ids(path: Path) -> list[str]:
    if not path.is_dir():
        return []
    return sorted(child.name for child in path.iterdir() if child.is_dir())


def _snapshot(repo: Path) -> dict[str, Any]:
    root = repo / "projects" / EPISODE
    orch = root / "orchestration"
    return {
        "files": {
            "paid_operation_attempt_ledger": _file_snapshot(
                orch / "paid-operation-attempt-ledger-v1.jsonl"
            ),
            "paid_retry_attempt_ledger": _file_snapshot(
                orch / "paid-retry-attempt-ledger-v1.jsonl"
            ),
            "paid_retry_journal": _file_snapshot(
                orch / "paid-retry-journal-v6-6.jsonl"
            ),
            "episode_transition_ledger": _file_snapshot(
                orch / "episode-transition-ledger-v1.jsonl"
            ),
            "provider_reconciliation": _file_snapshot(
                orch / "provider-attempt-reconciliation-v1.jsonl"
            ),
            "provider_stage_receipts": _file_snapshot(
                orch
                / "provider-execution-v1"
                / "provider-execution-stage-receipts-v1.jsonl"
            ),
            "qa_result": _file_snapshot(
                root / "deliverables" / "final-semantic-editorial-qa-v11.json"
            ),
        },
        "directories": {
            "paid_operation_attempts": _directory_manifest(
                orch / "paid-operation-attempts-v1"
            ),
            "prior_attempt": _directory_manifest(
                orch / "paid-operation-attempts-v1" / PRIOR_ATTEMPT_ID
            ),
            "provider_execution_evidence": _directory_manifest(
                orch / "provider-execution-v1"
            ),
        },
        "direct_attempt_ids": _direct_attempt_ids(
            orch / "paid-operation-attempts-v1"
        ),
    }


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    root = repo / "projects" / EPISODE
    orch = root / "orchestration"
    report_path = orch / "ep002-paid-retry-canonical-identity-release-certification-v12-final.json"
    plan_path = (
        orch
        / "explicit-paid-retry-v9"
        / "semantic-editorial-and-technical-qa-plan.json"
    )
    auth_path = (
        orch
        / "explicit-paid-retry-v9"
        / "semantic-editorial-and-technical-qa-authorization.json"
    )
    attempts_root = orch / "paid-operation-attempts-v1"
    new_attempt_root = attempts_root / NEW_ATTEMPT_ID
    result_path = root / "deliverables" / "final-semantic-editorial-qa-v11.json"

    report: dict[str, Any] = {
        "report_schema_version": "siraj-ep002-paid-retry-canonical-identity-release-certification-v12-final",
        "episode_id": EPISODE,
        "stage": STAGE,
        "branch": _git(repo, "branch", "--show-current"),
        "head": _git(repo, "rev-parse", "HEAD"),
        "exact_desktop_runtime_gate": "PASS",
        "exact_gate_safe_stop_before_network": True,
        "exact_gate_network_calls": 0,
        "exact_gate_provider_calls": 0,
        "exact_gate_paid_calls": 0,
        "canonical_request_identity_sha256": EXPECTED_IDENTITY,
        "provider_payload_sha256": EXPECTED_PROVIDER_PAYLOAD,
        "input_payload_sha256": EXPECTED_INPUT,
        "evidence_package_file_sha256": "c7f7790c47505c1f74c750792328ecb2f1d3583a947adb78ad14f57bca176163",
        "canonical_evidence_object_sha256": EXPECTED_INPUT,
        "request_payload_sha256": EXPECTED_PROVIDER_PAYLOAD,
        "paid_operation_request_payload_sha256": EXPECTED_PROVIDER_PAYLOAD,
        "final_provider_payload_sha256": EXPECTED_PROVIDER_PAYLOAD,
        "old_retry_identity_values": {
            "plan_payload_hash": "d047af178e330e3e77200962dd6635b1baab12cb8e0edf10d7931b242b020489",
            "retry_authorization_payload_hash": "d047af178e330e3e77200962dd6635b1baab12cb8e0edf10d7931b242b020489",
            "pre_fix_paid_operation_request_identity_sha256": "0213f91b255f3f955ca35e5740c11d6814145b41415dbcfc1a754f2faee5c1bb",
        },
        "new_canonical_identity_values": {
            "canonical_paid_operation_identity_sha256": EXPECTED_IDENTITY,
            "provider_payload_sha256": EXPECTED_PROVIDER_PAYLOAD,
            "identity_contract_schema": "siraj-paid-operation-identity-v1",
        },
        "stage_authorization_status": "ACTIVE",
        "retry_authorization_status": "ACTIVE",
        "retry_plan_status": "AUTHORIZED_ONE_SHOT",
        "safe_paid_gateway_probe": "PASS",
        "paid_gateway_master_authorization": "PASS",
        "paid_gateway_retry_authorization": "PASS",
        "provider_request_bytes": 664931,
        "estimated_requested_tokens": 178421,
        "provider_tpm_limit": 200000,
        "source_files_modified": [
            "src/application/paid_operation_identity_v1.py",
            "src/application/paid_operation_gateway.py",
            "src/application/siraj_luna_upstream_transport_v6_3.py",
            "scripts/desktop/run_ep002_paid_retry_canonical_identity_release_gate_v12.py",
            "scripts/desktop/run_ep002_paid_retry_once_v12.py",
            "tests/regression/test_paid_retry_canonical_identity_v12.py",
        ],
        "retry_attempt_id": NEW_ATTEMPT_ID,
        "prior_attempt_id": PRIOR_ATTEMPT_ID,
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        "additional_retry_or_resubmission_authorized": False,
    }

    before: dict[str, Any] | None = None
    counters = {
        "network_calls": 0,
        "qa_invocations": 0,
        "mark_ready_calls": 0,
    }
    originals: dict[str, Any] = {}
    error: str | None = None
    outcome_value: dict[str, Any] | None = None

    try:
        if report["head"] != EXPECTED_HEAD:
            raise RuntimeError("UNEXPECTED_HEAD")
        if report["branch"] != EXPECTED_BRANCH:
            raise RuntimeError("UNEXPECTED_BRANCH")
        state_before = read_desktop_episode_state(repo, EPISODE)
        if state_before.current_stage != STAGE:
            raise RuntimeError("UNEXPECTED_CURRENT_STAGE:" + state_before.current_stage)
        if new_attempt_root.exists():
            raise RuntimeError("NEW_ATTEMPT_ALREADY_EXISTS_BEFORE_QA")
        if result_path.is_file():
            raise RuntimeError("QA_RESULT_ALREADY_EXISTS_BEFORE_QA")

        plan = _load(plan_path)
        retry_auth = _load(auth_path)
        for document in (plan, retry_auth):
            if document.get("canonical_request_identity_sha256") != EXPECTED_IDENTITY:
                raise RuntimeError("CANONICAL_IDENTITY_BINDING_CHANGED_BEFORE_QA")
            if document.get("provider_payload_sha256") != EXPECTED_PROVIDER_PAYLOAD:
                raise RuntimeError("PROVIDER_PAYLOAD_BINDING_CHANGED_BEFORE_QA")
            if document.get("new_attempt_id") != NEW_ATTEMPT_ID:
                raise RuntimeError("NEW_ATTEMPT_ID_CHANGED_BEFORE_QA")
            if document.get("prior_attempt_id") != PRIOR_ATTEMPT_ID:
                raise RuntimeError("PRIOR_ATTEMPT_ID_CHANGED_BEFORE_QA")
            if document.get("automatic_retry") is not False:
                raise RuntimeError("AUTOMATIC_RETRY_ENABLED")
            if document.get("automatic_resubmission") is not False:
                raise RuntimeError("AUTOMATIC_RESUBMISSION_ENABLED")
            if document.get("one_shot") is not True:
                raise RuntimeError("ONE_SHOT_BINDING_MISSING")

        before = _snapshot(repo)
        if before["direct_attempt_ids"] != [
            item for item in before["direct_attempt_ids"] if item != NEW_ATTEMPT_ID
        ]:
            raise RuntimeError("INVALID_PRE_QA_ATTEMPT_SET")

        import src.application.siraj_one_click_autopilot_v6_4 as autopilot

        originals["urlopen"] = urllib.request.urlopen
        originals["qa"] = autopilot.semantic_editorial_qa
        originals["mark_ready"] = autopilot._mark_ready

        def counted_urlopen(*args: Any, **kwargs: Any) -> Any:
            counters["network_calls"] += 1
            return originals["urlopen"](*args, **kwargs)

        def counted_qa(*args: Any, **kwargs: Any) -> Any:
            counters["qa_invocations"] += 1
            if counters["qa_invocations"] > 1:
                raise RuntimeError("SECOND_QA_INVOCATION_BLOCKED")
            return originals["qa"](*args, **kwargs)

        def counted_mark_ready(*args: Any, **kwargs: Any) -> Any:
            counters["mark_ready_calls"] += 1
            return originals["mark_ready"](*args, **kwargs)

        urllib.request.urlopen = counted_urlopen
        autopilot.semantic_editorial_qa = counted_qa
        autopilot._mark_ready = counted_mark_ready
        try:
            controller = DesktopProductionResumeController(repo, EPISODE)
            intent = controller.prepare_resume(source=DESKTOP_SOURCE)
            authorization = controller.execution_authorization(intent)
            outcome = controller.execute_confirmed_resume(
                intent,
                authorization=authorization,
            )
            outcome_value = outcome.as_dict()
        finally:
            urllib.request.urlopen = originals["urlopen"]
            autopilot.semantic_editorial_qa = originals["qa"]
            autopilot._mark_ready = originals["mark_ready"]
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
        if originals.get("urlopen") is not None:
            urllib.request.urlopen = originals["urlopen"]
        try:
            import src.application.siraj_one_click_autopilot_v6_4 as autopilot
            if originals.get("qa") is not None:
                autopilot.semantic_editorial_qa = originals["qa"]
            if originals.get("mark_ready") is not None:
                autopilot._mark_ready = originals["mark_ready"]
        except Exception:
            pass

    after = _snapshot(repo)
    new_events_path = new_attempt_root / "attempt-events.jsonl"
    events: list[dict[str, Any]] = []
    if new_events_path.is_file():
        for line in new_events_path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                events.append(json.loads(line))
    event_attempt_ids = sorted({str(row.get("attempt_id")) for row in events})
    after_attempt_ids = after["direct_attempt_ids"]
    before_attempt_ids = before["direct_attempt_ids"] if before else []
    new_attempt_dirs = sorted(set(after_attempt_ids) - set(before_attempt_ids))
    prior_unchanged = (
        before is not None
        and before["directories"]["prior_attempt"]
        == after["directories"]["prior_attempt"]
    )
    provider_evidence_unchanged = (
        before is not None
        and before["directories"]["provider_execution_evidence"]
        == after["directories"]["provider_execution_evidence"]
    )
    qa_status = None
    qa_result_sha256 = None
    if result_path.is_file():
        qa_result = _load(result_path)
        qa_status = qa_result.get("status")
        qa_result_sha256 = sha256_file(result_path)

    gate_pass = (
        report["exact_desktop_runtime_gate"] == "PASS"
        and report["exact_gate_safe_stop_before_network"] is True
    )
    successful = (
        error is None
        and outcome_value is not None
        and outcome_value.get("status") == "PASS"
        and outcome_value.get("next_stage") == "READY_FOR_FINAL_HUMAN_REVIEW"
        and qa_status == "PASS"
        and counters["qa_invocations"] == 1
        and counters["network_calls"] == 1
        and counters["mark_ready_calls"] == 1
        and new_attempt_dirs == [NEW_ATTEMPT_ID]
        and event_attempt_ids == [NEW_ATTEMPT_ID]
        and len(events) > 0
        and prior_unchanged
        and provider_evidence_unchanged
    )

    report.update(
        {
            "status": "PASS" if successful and gate_pass else "FAIL",
            "root_cause": "FIXED_CANONICAL_PAID_REQUEST_IDENTITY_MISMATCH",
            "qa_execution": "ONE_REAL_DESKTOP_QA_INVOCATION",
            "qa_invocations": counters["qa_invocations"],
            "network_calls": counters["network_calls"],
            "provider_calls": counters["network_calls"],
            "paid_calls": counters["network_calls"],
            "error": error,
            "outcome": outcome_value,
            "qa_result_status": qa_status,
            "qa_result_sha256": qa_result_sha256,
            "attempt_event_count_after": len(events),
            "attempt_event_statuses_after": [
                str(row.get("status") or "") for row in events
            ],
            "attempt_event_attempt_ids_after": event_attempt_ids,
            "new_attempt_directories": new_attempt_dirs,
            "prior_attempt_unchanged": prior_unchanged,
            "provider_evidence_unchanged": provider_evidence_unchanged,
            "paid_attempt_events_before": 0,
            "paid_attempt_events_after": len(events),
            "episode_transition_ledger_before_after": {
                "before": before["files"]["episode_transition_ledger"] if before else None,
                "after": after["files"]["episode_transition_ledger"],
                "changed_as_authorized_qa_completion": (
                    before is not None
                    and before["files"]["episode_transition_ledger"]
                    != after["files"]["episode_transition_ledger"]
                ),
            },
            "paid_history": {
                "before": before["files"] if before else None,
                "after": after["files"],
                "historical_prior_attempt_unchanged": prior_unchanged,
                "new_authorized_attempt_only": new_attempt_dirs == [NEW_ATTEMPT_ID],
            },
            "exact_runtime_module_provenance": {
                "desktop_controller": "src.application.desktop_resume_readiness_v1.DesktopProductionResumeController",
                "desktop_qa_executor": "src.application.desktop_semantic_editorial_qa_v3.CanonicalDesktopSemanticQAExecutor",
                "semantic_editorial_qa": "src.application.siraj_downstream_luna_adapters_v6_4.semantic_editorial_qa",
                "luna_transport": "src.application.siraj_luna_upstream_transport_v6_3",
                "paid_gateway": "src.application.paid_operation_gateway",
            },
            "next_action": (
                "QA_COMPLETED_NO_RETRY_OR_RESUBMISSION_AUTHORIZED"
                if successful and gate_pass
                else "DO_NOT_RETRY_OR_RESUBMIT; REVIEW_SINGLE_ATTEMPT_OUTCOME"
            ),
        }
    )
    _write_report(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
