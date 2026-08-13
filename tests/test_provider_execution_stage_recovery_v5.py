from __future__ import annotations

import ast
import json
import shutil
import socket
from pathlib import Path

import pytest

from historical_append_only_state_v1 import (
    materialize_ep002_provider_execution_ready,
)

from src.application.artifact_provenance_v1 import read_jsonl
from src.application.desktop_provider_execution_v1 import (
    CanonicalDesktopProviderExecutionExecutor,
    STAGE_RECEIPT_LEDGER,
    _siraj_provider_execution_recovery_session_v2,
    append_jsonl,
)
from src.application.desktop_resume_readiness_v1 import (
    DESKTOP_SOURCE,
    EPISODE_002,
    DesktopProductionResumeController,
)

REPO = Path(__file__).resolve().parents[1]


def _copy(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _actual_state_clone(tmp_path: Path) -> Path:
    root = tmp_path / "siraj-ep002-actual-accumulated-state-v5"
    _copy(
        REPO / "projects" / EPISODE_002,
        root / "projects" / EPISODE_002,
    )
    for rel in ("projects/_series", "projects/_orchestrator"):
        _copy(REPO / rel, root / rel)
    materialize_ep002_provider_execution_ready(
        root,
        retain_unfinished_provider_session=True,
    )
    return root


def _deny_network(*args, **kwargs):
    raise AssertionError("NETWORK_FORBIDDEN_IN_ACTUAL_STATE_CLONE_TEST")


def _newest_unfinished_session(rows: list[dict]) -> str | None:
    starts = [
        row
        for row in rows
        if str(row.get("stage") or "") == "PROVIDER_EXECUTION"
        and str(row.get("status") or "") == "STAGE_STARTED"
        and str(row.get("session_id") or "").strip()
    ]
    completed = {"STAGE_COMPLETED", "COMPLETED", "COMPLETE"}
    for start in reversed(starts):
        session_id = str(start.get("session_id") or "").strip()
        if not any(
            str(row.get("session_id") or "") == session_id
            and str(row.get("status") or "") in completed
            for row in rows
        ):
            return session_id
    return None


def test_actual_ep002_accumulated_state_selects_existing_session_and_suppresses_duplicate_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(socket.socket, "connect", _deny_network)

    fixture = _actual_state_clone(tmp_path)
    controller = DesktopProductionResumeController(fixture, EPISODE_002)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    assert intent is not None

    preflight_path = (
        fixture
        / "projects"
        / EPISODE_002
        / "orchestration"
        / "media-cost-preflight-v2.json"
    )
    preflight = json.loads(preflight_path.read_text(encoding="utf-8-sig"))
    runware_units = [
        unit
        for unit in (preflight.get("units") or [])
        if str(unit.get("provider") or "").upper() == "RUNWARE"
    ]
    assert len(runware_units) == 95

    execution_root = (
        fixture
        / "projects"
        / EPISODE_002
        / "orchestration"
        / "provider-execution-v1"
    )
    stage_path = execution_root / STAGE_RECEIPT_LEDGER
    before_rows = read_jsonl(stage_path)
    expected_session = _newest_unfinished_session(before_rows)
    assert expected_session, "actual EP002 clone must contain an unfinished session"

    executor = CanonicalDesktopProviderExecutionExecutor(fixture, EPISODE_002)
    reconciliation = executor.reconcile()
    recovered_session = _siraj_provider_execution_recovery_session_v2(
        fixture,
        EPISODE_002,
        reconciliation,
    )
    assert recovered_session == expected_session

    start_row = next(
        row
        for row in reversed(before_rows)
        if str(row.get("status") or "") == "STAGE_STARTED"
        and str(row.get("session_id") or "") == recovered_session
    )
    append_jsonl(stage_path, dict(start_row))
    after_rows = read_jsonl(stage_path)
    assert after_rows == before_rows


def test_recovery_helper_is_fail_closed_for_unsafe_reconciliation(
    tmp_path: Path,
) -> None:
    fixture = _actual_state_clone(tmp_path)
    executor = CanonicalDesktopProviderExecutionExecutor(fixture, EPISODE_002)
    safe = dict(executor.reconcile())

    assert _siraj_provider_execution_recovery_session_v2(
        fixture,
        EPISODE_002,
        {**safe, "unknown_blocking_requests": ["unsafe"]},
    ) is None

    assert _siraj_provider_execution_recovery_session_v2(
        fixture,
        EPISODE_002,
        {
            **safe,
            "pending_attempts": [],
            "blocked_requests": [{"request_id": "UNRELATED-BLOCK"}],
        },
    ) is None

    assert _siraj_provider_execution_recovery_session_v2(
        fixture,
        EPISODE_002,
        {
            **safe,
            "pending_attempts": [{"request_id": "PENDING-NO-OP-ID"}],
            "blocked_requests": [{"request_id": "PENDING-NO-OP-ID"}],
        },
    ) is None

    assert _siraj_provider_execution_recovery_session_v2(
        fixture,
        EPISODE_002,
        {
            **safe,
            "pending_attempts": ["PENDING-NO-OP-ID"],
            "provider_operation_ids": {},
            "request_attempts": {"PENDING-REQUEST": "PENDING-NO-OP-ID"},
            "blocked_requests": ["PENDING-REQUEST"],
        },
    ) is None


def test_patched_execute_control_flow_reuses_recovered_session() -> None:
    path = REPO / "src/application/desktop_provider_execution_v1.py"
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    execute = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "CanonicalDesktopProviderExecutionExecutor":
            execute = next(
                (
                    child
                    for child in node.body
                    if isinstance(child, ast.FunctionDef) and child.name == "execute"
                ),
                None,
            )
            break
    assert execute is not None
    text = ast.unparse(execute)
    assert "recovery_snapshot = self.reconcile()" in text
    assert "_siraj_provider_execution_recovery_session_v2" in text
    assert "session_id = recovered_session_id" in text
    assert "recovery_mode = True" in text
    assert "if not recovery_mode:" in text
    assert "EXECUTION_ALREADY_STARTED_RECOVERY_REQUIRED" in text


def test_recovery_contract_markers_are_present() -> None:
    source = (
        REPO / "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    assert "SIRAJ_PROVIDER_EXECUTION_STAGE_RECOVERY_V3" in source
    assert "unknown_blocking_requests" in source
    assert "unsafe_blocked" in source
    assert "_siraj_base_append_jsonl_v2" in source
    assert "DESKTOP_EXECUTION_CONTEXT_REQUIRED" in source
