"""Offline exact Desktop release gate for the EP002 one-shot QA retry.

This gate enters the same Desktop controller and QA executor used by Resume,
then stops at the paid gateway's request-record boundary.  It never writes a
paid-attempt event and never invokes a provider transport.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any

from src.application.artifact_provenance_v1 import (
    canonical_json_bytes,
    canonical_sha256,
    sha256_file,
)
from src.application.desktop_resume_readiness_v1 import (
    DESKTOP_SOURCE,
    DesktopEpisodeState,
    DesktopProductionResumeController,
    DesktopResumeIntent,
    SEMANTIC_EDITORIAL_AND_TECHNICAL_QA,
    read_desktop_episode_state,
)
from src.application.desktop_semantic_editorial_qa_v3 import (
    CanonicalDesktopSemanticQAExecutor,
)
from src.application.paid_operation_identity_v1 import (
    provider_payload_sha256,
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
EXPECTED_PROVIDER_BYTES = 664931
KNOWN_PROVIDER_TPM_LIMIT = 200000


class SafeStop(RuntimeError):
    """Expected local stop immediately before paid-attempt persistence."""


def _file_snapshot(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False, "bytes": 0, "sha256": None}
    return {
        "present": True,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _directory_snapshot(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        return {
            "present": False,
            "file_count": 0,
            "total_bytes": 0,
            "manifest_sha256": None,
        }
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        relative = str(child.relative_to(path)).replace("\\", "/")
        size = child.stat().st_size
        total_bytes += size
        entries.append(
            {
                "path": relative,
                "bytes": size,
                "sha256": sha256_file(child),
            }
        )
    return {
        "present": True,
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "manifest_sha256": canonical_sha256(entries),
    }


def _repo_snapshot(repo: Path) -> dict[str, Any]:
    episode_root = repo / "projects" / EPISODE
    orchestration = episode_root / "orchestration"
    files = {
        "paid_operation_attempt_ledger": orchestration
        / "paid-operation-attempt-ledger-v1.jsonl",
        "paid_retry_attempt_ledger": orchestration
        / "paid-retry-attempt-ledger-v1.jsonl",
        "paid_retry_journal": orchestration / "paid-retry-journal-v6-6.jsonl",
        "episode_transition_ledger": orchestration
        / "episode-transition-ledger-v1.jsonl",
        "provider_reconciliation": orchestration
        / "provider-attempt-reconciliation-v1.jsonl",
        "provider_stage_receipts": orchestration
        / "provider-execution-v1"
        / "provider-execution-stage-receipts-v1.jsonl",
        "luna_stage_ledger": orchestration
        / "luna-v6-3"
        / "semantic-editorial-and-technical-qa"
        / "attempt-ledger.jsonl",
        "qa_result": episode_root
        / "deliverables"
        / "final-semantic-editorial-qa-v11.json",
    }
    directories = {
        "paid_operation_attempts": orchestration / "paid-operation-attempts-v1",
        "provider_execution_evidence": orchestration / "provider-execution-v1",
        "luna_stage_evidence": orchestration / "luna-v6-3",
    }
    return {
        "files": {name: _file_snapshot(path) for name, path in files.items()},
        "directories": {
            name: _directory_snapshot(path)
            for name, path in directories.items()
        },
    }


def _git_value(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=repo,
        text=True,
    ).strip()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _offline_final_review_route_probe() -> dict[str, Any]:
    """Prove the durable-PASS projection without touching the real episode."""

    with TemporaryDirectory(prefix="siraj-ep002-final-review-probe-") as raw:
        root = Path(raw)
        episode_root = root / "projects" / EPISODE
        result_path = (
            episode_root
            / "deliverables"
            / "final-semantic-editorial-qa-v11.json"
        )
        transition_path = (
            episode_root
            / "orchestration"
            / "episode-transition-ledger-v1.jsonl"
        )
        result_path.parent.mkdir(parents=True, exist_ok=True)
        transition_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "episode_id": EPISODE,
                    "qa_contract_version": "FINAL_QA_EVIDENCE_V11_COMPACT",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        transition_path.write_text("", encoding="utf-8")

        state = DesktopEpisodeState(
            episode_id=EPISODE,
            current_stage=STAGE,
            status="READY",
            completed_stages=("LOCAL_ASSEMBLY_AND_MONTAGE",),
            alignment_gate="PASS",
            duplicate_gate="PASS",
            promoted_overlay_sha256="",
            authoritative_structural_fingerprint="",
            provider_plan_contract_fingerprint="",
            duration_seconds=0.0,
            shot_count=0,
            timeline_discontinuities=0,
            ledger_path=str(transition_path),
            ledger_head_sha256="OFFLINE_PROBE_HEAD",
            ledger_entry_count=0,
        )

        def state_reader(_repo: Path, _episode: str) -> DesktopEpisodeState:
            return state

        def ledger_appender(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {"transition_id": "offline-final-review-probe"}

        intent = DesktopResumeIntent(
            episode_id=EPISODE,
            first_stage=STAGE,
            source=DESKTOP_SOURCE,
            requires_explicit_human_action=True,
            ledger_head_sha256="OFFLINE_PROBE_HEAD",
            execution_token="offline-final-review-token",
        )
        authorization = {
            "authorization_id": "offline-final-review-authorization",
            "source": DESKTOP_SOURCE,
            "scope": "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA_DESKTOP_RESUME",
            "episode_id": EPISODE,
            "stage": STAGE,
            "execution_token": "offline-final-review-token",
        }
        outcome = CanonicalDesktopSemanticQAExecutor(
            root,
            EPISODE,
            state_reader=state_reader,
            ledger_appender=ledger_appender,
        ).execute(intent, authorization=authorization)
        if outcome.status != "PASS":
            raise RuntimeError("FINAL_REVIEW_ROUTE_PROBE_NOT_PASS")
        if outcome.next_stage != "READY_FOR_FINAL_HUMAN_REVIEW":
            raise RuntimeError("FINAL_REVIEW_ROUTE_NEXT_STAGE_INVALID")
        if outcome.next_stage_executed:
            raise RuntimeError("FINAL_REVIEW_ROUTE_EXECUTED_DOWNSTREAM_STAGE")
        if not outcome.recovered_existing_result:
            raise RuntimeError("FINAL_REVIEW_ROUTE_DID_NOT_RECOVER_DURABLE_PASS")
        return outcome.as_dict()


def run_gate(repo: Path) -> dict[str, Any]:
    if _git_value(repo, "rev-parse", "HEAD") != EXPECTED_HEAD:
        raise RuntimeError("UNEXPECTED_HEAD")
    if _git_value(repo, "branch", "--show-current") != EXPECTED_BRANCH:
        raise RuntimeError("UNEXPECTED_BRANCH")

    state = read_desktop_episode_state(repo, EPISODE)
    if state.current_stage != STAGE:
        raise RuntimeError(f"UNEXPECTED_CURRENT_STAGE:{state.current_stage}")

    episode_root = repo / "projects" / EPISODE
    orchestration = episode_root / "orchestration"
    attempts_root = orchestration / "paid-operation-attempts-v1"
    new_attempt_root = attempts_root / NEW_ATTEMPT_ID
    main_attempt_ledger = orchestration / "paid-operation-attempt-ledger-v1.jsonl"
    if new_attempt_root.exists():
        raise RuntimeError("NEW_ATTEMPT_ALREADY_EXISTS")
    if NEW_ATTEMPT_ID in main_attempt_ledger.read_text(encoding="utf-8-sig"):
        raise RuntimeError("NEW_ATTEMPT_ALREADY_IN_LEDGER")

    result_path = episode_root / "deliverables" / "final-semantic-editorial-qa-v11.json"
    if result_path.is_file():
        existing_result = _load_json(result_path)
        if existing_result.get("status") == "PASS":
            raise RuntimeError("DURABLE_QA_PASS_ALREADY_EXISTS_GATE_WOULD_BYPASS_RUNTIME")

    plan = _load_json(
        orchestration
        / "explicit-paid-retry-v9"
        / "semantic-editorial-and-technical-qa-plan.json"
    )
    retry_auth = _load_json(
        orchestration
        / "explicit-paid-retry-v9"
        / "semantic-editorial-and-technical-qa-authorization.json"
    )
    if plan.get("canonical_request_identity_sha256") != EXPECTED_IDENTITY:
        raise RuntimeError("PLAN_CANONICAL_IDENTITY_NOT_REBOUND")
    if retry_auth.get("canonical_request_identity_sha256") != EXPECTED_IDENTITY:
        raise RuntimeError("AUTH_CANONICAL_IDENTITY_NOT_REBOUND")
    if plan.get("provider_payload_sha256") != EXPECTED_PROVIDER_PAYLOAD:
        raise RuntimeError("PLAN_PROVIDER_PAYLOAD_NOT_REBOUND")
    if retry_auth.get("provider_payload_sha256") != EXPECTED_PROVIDER_PAYLOAD:
        raise RuntimeError("AUTH_PROVIDER_PAYLOAD_NOT_REBOUND")
    for value, expected in (
        (plan.get("new_attempt_id"), NEW_ATTEMPT_ID),
        (retry_auth.get("new_attempt_id"), NEW_ATTEMPT_ID),
        (plan.get("prior_attempt_id"), PRIOR_ATTEMPT_ID),
        (retry_auth.get("prior_attempt_id"), PRIOR_ATTEMPT_ID),
    ):
        if value != expected:
            raise RuntimeError("RETRY_LINEAGE_CHANGED")
    for document in (plan, retry_auth):
        if (
            document.get("automatic_retry") is not False
            or document.get("automatic_resubmission") is not False
            or document.get("one_shot") is not True
        ):
            raise RuntimeError("RETRY_SEMANTICS_CHANGED")

    release_report = _load_json(
        orchestration / "ep002-adaptive-luna-tpm-release-gate-v11-1.json"
    )
    final_request = release_report["adaptive_packaging"]["final_request"]
    tpm_limit = int(
        release_report["adaptive_packaging"]["provider_external_tpm_limit"]
    )
    old_attempt_request = _load_json(
        attempts_root / PRIOR_ATTEMPT_ID / "request.json"
    )
    old_provider_bytes = len(canonical_json_bytes(old_attempt_request["payload"]))
    old_requested_tokens = int(
        release_report["root_cause"]["attempts"][1]["requested_tokens"]
    )
    if tpm_limit != KNOWN_PROVIDER_TPM_LIMIT:
        raise RuntimeError("KNOWN_PROVIDER_TPM_LIMIT_CHANGED")

    before = _repo_snapshot(repo)
    captured: dict[str, Any] = {
        "network_calls": 0,
        "provider_calls": 0,
        "paid_calls": 0,
        "provider_transport_factory_calls": 0,
        "provider_transport_invocations": 0,
        "emit_event_calls": 0,
        "mark_ready_calls": 0,
        "paid_write_calls": 0,
    }

    import src.application.paid_operation_gateway as gateway
    import src.application.siraj_luna_upstream_transport_v6_3 as luna
    import src.application.siraj_one_click_autopilot_v6_4 as autopilot

    originals = {
        "write": gateway._write_request_once,
        "transport": luna.http_json_transport,
        "emit_event": luna.emit_event,
        "paid_input": autopilot._paid_luna_input,
        "qa_runner": autopilot.semantic_editorial_qa,
        "mark_ready": autopilot._mark_ready,
    }

    def safe_write(request: Any) -> None:
        captured["paid_write_calls"] += 1
        captured["paid_request"] = request
        raise SafeStop("SAFE_STOP_BEFORE_PAID_ATTEMPT_PERSISTENCE")

    def safe_transport(**kwargs: Any) -> Any:
        captured["provider_transport_factory_calls"] += 1
        captured["provider_payload"] = kwargs["payload"]

        def never_called(_boundary: Any) -> bytes:
            captured["provider_transport_invocations"] += 1
            captured["network_calls"] += 1
            raise AssertionError("NETWORK_TRANSPORT_INVOKED")

        return never_called

    def safe_emit_event(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        captured["emit_event_calls"] += 1
        return {"telemetry_persisted": True}

    def capture_paid_input(*args: Any, **kwargs: Any) -> dict[str, Any]:
        value = originals["paid_input"](*args, **kwargs)
        captured["input_payload"] = value
        captured["input_payload_sha256"] = canonical_sha256(value)
        return value

    def capture_qa_runner(*args: Any, **kwargs: Any) -> Any:
        if len(args) >= 3:
            captured["qa_runner_input_sha256"] = canonical_sha256(args[2])
        elif "master_manifest" in kwargs:
            captured["qa_runner_input_sha256"] = canonical_sha256(
                kwargs["master_manifest"]
            )
        return originals["qa_runner"](*args, **kwargs)

    def unexpected_mark_ready(*_args: Any, **_kwargs: Any) -> Any:
        captured["mark_ready_calls"] += 1
        raise AssertionError("DOWNSTREAM_MARK_READY_INVOKED")

    gateway._write_request_once = safe_write
    luna.http_json_transport = safe_transport
    luna.emit_event = safe_emit_event
    autopilot._paid_luna_input = capture_paid_input
    autopilot.semantic_editorial_qa = capture_qa_runner
    autopilot._mark_ready = unexpected_mark_ready

    safe_stop = None
    unexpected_error = None
    try:
        controller = DesktopProductionResumeController(repo, EPISODE)
        intent = controller.prepare_resume(source=DESKTOP_SOURCE)
        authorization = controller.execution_authorization(intent)
        try:
            controller.execute_confirmed_resume(
                intent,
                authorization=authorization,
            )
        except SafeStop as exc:
            safe_stop = str(exc)
        except Exception as exc:  # pragma: no cover - gate failure report
            unexpected_error = f"{type(exc).__name__}:{exc}"
    finally:
        gateway._write_request_once = originals["write"]
        luna.http_json_transport = originals["transport"]
        luna.emit_event = originals["emit_event"]
        autopilot._paid_luna_input = originals["paid_input"]
        autopilot.semantic_editorial_qa = originals["qa_runner"]
        autopilot._mark_ready = originals["mark_ready"]

    if unexpected_error:
        raise RuntimeError("DESKTOP_EXACT_ROUTE_FAILED:" + unexpected_error)
    if safe_stop != "SAFE_STOP_BEFORE_PAID_ATTEMPT_PERSISTENCE":
        raise RuntimeError(f"EXPECTED_SAFE_STOP_NOT_REACHED:{safe_stop}")
    if captured["paid_write_calls"] != 1:
        raise RuntimeError("PAID_GATEWAY_REQUEST_BOUNDARY_NOT_REACHED_ONCE")
    if captured["provider_transport_invocations"] != 0:
        raise RuntimeError("PROVIDER_TRANSPORT_INVOKED")
    if captured["mark_ready_calls"] != 0:
        raise RuntimeError("DOWNSTREAM_STAGE_EXECUTED")

    request = captured["paid_request"]
    provider_payload = captured["provider_payload"]
    request_payload_hash = provider_payload_sha256(provider_payload)
    provider_bytes = len(canonical_json_bytes(provider_payload))
    estimated_tokens = round(provider_bytes * old_requested_tokens / old_provider_bytes)

    if captured.get("input_payload_sha256") != EXPECTED_INPUT:
        raise RuntimeError("DESKTOP_INPUT_PAYLOAD_IDENTITY_CHANGED")
    if request.canonical_request_identity_sha256 != EXPECTED_IDENTITY:
        raise RuntimeError("PAID_REQUEST_CANONICAL_IDENTITY_MISMATCH")
    if request.payload_sha256 != EXPECTED_PROVIDER_PAYLOAD:
        raise RuntimeError("PAID_REQUEST_PROVIDER_PAYLOAD_MISMATCH")
    if request_payload_hash != EXPECTED_PROVIDER_PAYLOAD:
        raise RuntimeError("FINAL_PROVIDER_PAYLOAD_MISMATCH")
    if request.immutable_attempt_id != NEW_ATTEMPT_ID:
        raise RuntimeError("PAID_REQUEST_ATTEMPT_ID_MISMATCH")
    if request.prior_attempt_id != PRIOR_ATTEMPT_ID:
        raise RuntimeError("PAID_REQUEST_PRIOR_ATTEMPT_ID_MISMATCH")
    if provider_bytes != EXPECTED_PROVIDER_BYTES:
        raise RuntimeError("PROVIDER_REQUEST_BYTES_CHANGED")
    if estimated_tokens >= tpm_limit:
        raise RuntimeError("PROVIDER_TPM_PREFLIGHT_FAILED")
    if request.retry_authorization_reference is None:
        raise RuntimeError("RETRY_AUTHORIZATION_NOT_ATTACHED")
    if (
        request.retry_authorization_reference.get(
            "canonical_request_identity_sha256"
        )
        != request.canonical_request_identity_sha256
    ):
        raise RuntimeError("GATEWAY_RETRY_IDENTITY_BINDING_NOT_VALIDATED")
    if (
        request.retry_authorization_reference.get("provider_payload_sha256")
        != request.payload_sha256
    ):
        raise RuntimeError("GATEWAY_RETRY_PROVIDER_BINDING_NOT_VALIDATED")

    after = _repo_snapshot(repo)
    if before != after:
        raise RuntimeError("DURABLE_HISTORY_CHANGED_DURING_SAFE_GATE")

    review_route = _offline_final_review_route_probe()
    return {
        "status": "PASS",
        "root_cause": "FIXED_CANONICAL_PAID_REQUEST_IDENTITY_MISMATCH",
        "desktop_exact_runtime_gate": "PASS",
        "explicit_paid_retry_plan_binding": "PASS",
        "stage_authorization": "PASS",
        "retry_authorization": "PASS",
        "paid_gateway_master_authorization": "PASS",
        "paid_gateway_retry_authorization": "PASS",
        "safe_stop_before_network": True,
        "new_paid_attempt_created": False,
        "network_calls": captured["network_calls"],
        "provider_calls": captured["provider_transport_invocations"],
        "paid_calls": captured["paid_calls"],
        "retry_attempt_id": NEW_ATTEMPT_ID,
        "prior_attempt_id": PRIOR_ATTEMPT_ID,
        "input_payload_sha256": captured["input_payload_sha256"],
        "request_payload_sha256": request_payload_hash,
        "paid_operation_request_payload_sha256": request.payload_sha256,
        "canonical_paid_operation_identity_sha256": request.canonical_request_identity_sha256,
        "retry_plan_canonical_identity_sha256": plan[
            "canonical_request_identity_sha256"
        ],
        "retry_authorization_canonical_identity_sha256": retry_auth[
            "canonical_request_identity_sha256"
        ],
        "provider_request_bytes": provider_bytes,
        "estimated_requested_tokens": estimated_tokens,
        "provider_tpm_limit": tpm_limit,
        "token_estimation_method": "PROVEN_PRIOR_429_RATIO_USING_CANONICAL_PAYLOAD_BYTES",
        "gateway_request_boundary_calls": captured["paid_write_calls"],
        "provider_transport_factory_calls": captured["provider_transport_factory_calls"],
        "provider_transport_invocations": captured["provider_transport_invocations"],
        "downstream_stage_executions": captured["mark_ready_calls"],
        "paid_attempt_events_before": 0,
        "paid_attempt_events_after": 0,
        "paid_history_unchanged": True,
        "provider_evidence_unchanged": True,
        "episode_transition_ledger_unchanged": True,
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        "qa_to_final_human_review_route": "PASS",
        "final_human_review_route_probe": review_route,
        "snapshots_before_after_equal": True,
        "runtime_module_provenance": {
            "desktop_controller": "src.application.desktop_resume_readiness_v1.DesktopProductionResumeController",
            "desktop_qa_executor": "src.application.desktop_semantic_editorial_qa_v3.CanonicalDesktopSemanticQAExecutor",
            "semantic_editorial_qa": "src.application.siraj_downstream_luna_adapters_v6_4.semantic_editorial_qa",
            "luna_transport": "src.application.siraj_luna_upstream_transport_v6_3",
            "paid_gateway": "src.application.paid_operation_gateway",
        },
        "source_head": _git_value(repo, "rev-parse", "HEAD"),
        "source_branch": _git_value(repo, "branch", "--show-current"),
    }


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    try:
        result = run_gate(repo)
    except Exception as exc:  # pragma: no cover - command-line failure output
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "failure": f"{type(exc).__name__}:{exc}",
                    "network_calls": 0,
                    "provider_calls": 0,
                    "paid_calls": 0,
                    "safe_stop_before_network": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
