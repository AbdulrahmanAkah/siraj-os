from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import shutil

import pytest

from src.application.artifact_provenance_v1 import read_jsonl, sha256_file
from src.application.desktop_cost_envelope_reack_v1 import (
    DesktopCostEnvelopeReackService,
    REACK_RECEIPT_LEDGER,
    reack_receipt_path,
)
from src.application.desktop_media_cost_preflight_v1 import (
    read_persisted_media_cost_preflight,
)
from src.application.desktop_provider_execution_v1 import (
    CanonicalDesktopProviderExecutionExecutor,
    DesktopProviderExecutionError,
    FakeAsyncPaidProviderGateway,
    FakePaidProviderGateway,
    reconcile_unknown_attempt,
)
from src.application.provider_attempt_reconciliation_v1 import RECONCILIATION_LEDGER
from src.application.desktop_resume_readiness_v1 import (
    DESKTOP_SOURCE,
    EPISODE_002,
    DesktopProductionResumeController,
    DesktopResumePolicyError,
    read_desktop_episode_state,
)
from src.application.episode_transition_ledger_v1 import project_state


REPO = Path(__file__).resolve().parents[1]


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "siraj-provider-fixture"
    shutil.copytree(
        REPO / "projects" / EPISODE_002,
        root / "projects" / EPISODE_002,
        ignore=shutil.ignore_patterns(
            REACK_RECEIPT_LEDGER,
            RECONCILIATION_LEDGER,
            "provider-execution-v1",
        ),
    )
    return root


def _ack(fixture: Path) -> None:
    review = read_persisted_media_cost_preflight(fixture, EPISODE_002)
    snapshot = review.as_dict()
    snapshot["reviewed_at_utc"] = "2026-08-10T00:00:00Z"
    DesktopCostEnvelopeReackService(fixture, EPISODE_002).confirm(
        snapshot,
        source=DESKTOP_SOURCE,
    )


def test_fake_desktop_provider_execution_consumes_exact_plan(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    before_real = sha256_file(
        REPO / "projects" / EPISODE_002 / "orchestration" / "episode-transition-ledger-v1.jsonl"
    )
    _ack(fixture)
    controller = DesktopProductionResumeController(fixture, EPISODE_002)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    gateway = FakePaidProviderGateway()
    progress: list[dict[str, object]] = []
    outcome = controller.execute_confirmed_resume(
        intent,
        authorization=controller.execution_authorization(intent),
        provider_gateway=gateway,
        progress_callback=progress.append,
    )
    assert outcome.status == "COMPLETED"
    assert outcome.completed_requests == 95
    assert outcome.video_requests == 73
    assert outcome.still_requests == 22
    assert outcome.local_units == 4
    assert outcome.next_stage == "LOCAL_ASSEMBLY_AND_MONTAGE"
    assert gateway.provider_calls == 95
    assert len({row["attempt_id"] for row in gateway.calls}) == 95
    assert progress
    assert progress[-1]["status"] == "PROVIDER_EXECUTION_COMPLETED"
    assert progress[-1]["completed_requests"] == 95
    assert project_state(fixture, EPISODE_002).current_stage == "LOCAL_ASSEMBLY_AND_MONTAGE"
    assert read_desktop_episode_state(fixture, EPISODE_002).current_stage == "LOCAL_ASSEMBLY_AND_MONTAGE"
    # The real production ledger is never touched by the isolated fake run.
    assert sha256_file(
        REPO / "projects" / EPISODE_002 / "orchestration" / "episode-transition-ledger-v1.jsonl"
    ) == before_real


def test_provider_stage_requires_desktop_capability_context(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _ack(fixture)
    controller = DesktopProductionResumeController(fixture, EPISODE_002)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    with pytest.raises(DesktopResumePolicyError, match="DESKTOP_EXECUTION_CONTEXT_REQUIRED"):
        controller.execute_confirmed_resume(
            intent,
            authorization={"source": DESKTOP_SOURCE},
            provider_gateway=FakePaidProviderGateway(),
        )


def test_provider_stage_rejects_stale_plan_binding_before_gateway(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _ack(fixture)
    controller = DesktopProductionResumeController(fixture, EPISODE_002)
    intent = replace(
        controller.prepare_resume(source=DESKTOP_SOURCE),
        media_plan_sha256="0" * 64,
    )
    gateway = FakePaidProviderGateway()
    with pytest.raises(DesktopResumePolicyError, match="STALE_STATE_REVIEW_REQUIRED"):
        controller.execute_confirmed_resume(
            intent,
            authorization=controller.execution_authorization(intent),
            provider_gateway=gateway,
        )
    assert gateway.provider_calls == 0


def test_failure_is_terminal_and_never_automatically_resubmitted(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _ack(fixture)
    controller = DesktopProductionResumeController(fixture, EPISODE_002)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    gateway = FakePaidProviderGateway(fail_at=2)
    with pytest.raises(DesktopProviderExecutionError, match="FAILED_NO_AUTOMATIC_RETRY"):
        controller.execute_confirmed_resume(
            intent,
            authorization=controller.execution_authorization(intent),
            provider_gateway=gateway,
        )
    assert gateway.provider_calls == 2
    with pytest.raises(DesktopProviderExecutionError, match="RECOVERY_REQUIRED"):
        CanonicalDesktopProviderExecutionExecutor(
            fixture,
            EPISODE_002,
            gateway=FakePaidProviderGateway(),
        ).execute(
            intent,
            authorization=controller.execution_authorization(intent),
        )
    assert len(read_jsonl(reack_receipt_path(fixture, EPISODE_002))) == 1


def test_unknown_response_is_preserved_without_retry(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _ack(fixture)
    controller = DesktopProductionResumeController(fixture, EPISODE_002)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    gateway = FakePaidProviderGateway(unknown_at=1)
    with pytest.raises(DesktopProviderExecutionError, match="UNKNOWN_NO_AUTOMATIC_RETRY"):
        controller.execute_confirmed_resume(
            intent,
            authorization=controller.execution_authorization(intent),
            provider_gateway=gateway,
        )
    assert gateway.provider_calls == 1
    progress = json.loads(
        (
            fixture
            / "projects"
            / EPISODE_002
            / "orchestration"
            / "provider-execution-v1"
            / "provider-execution-progress-v1.json"
        ).read_text(encoding="utf-8")
    )
    assert progress["unknown_requests"] == 1
    assert progress["automatic_paid_retry"] is False
    assert progress["automatic_paid_resubmission"] is False


def test_async_provider_id_is_durable_before_completion(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _ack(fixture)
    controller = DesktopProductionResumeController(fixture, EPISODE_002)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    gateway = FakeAsyncPaidProviderGateway(polls_before_complete=2)
    outcome = controller.execute_confirmed_resume(
        intent,
        authorization=controller.execution_authorization(intent),
        provider_gateway=gateway,
    )
    assert outcome.status == "COMPLETED"
    assert gateway.provider_calls == 95
    assert gateway.poll_calls == 190
    rows = read_jsonl(
        fixture
        / "projects"
        / EPISODE_002
        / "orchestration"
        / "provider-execution-v1"
        / "provider-execution-attempt-receipts-v1.jsonl"
    )
    pending = [row for row in rows if row.get("status") == "SUBMITTED_PENDING"]
    assert len(pending) == 95
    assert all(row.get("provider_operation_id") for row in pending)
    assert all(row.get("automatic_paid_resubmission") is False for row in pending)


def test_async_poll_timeout_keeps_original_operation_pending(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _ack(fixture)
    controller = DesktopProductionResumeController(fixture, EPISODE_002)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    gateway = FakeAsyncPaidProviderGateway(polling_timeout=True)
    with pytest.raises(DesktopProviderExecutionError, match="SUBMITTED_PENDING_NO_AUTOMATIC_RETRY"):
        controller.execute_confirmed_resume(
            intent,
            authorization=controller.execution_authorization(intent),
            provider_gateway=gateway,
        )
    assert gateway.provider_calls == 1
    assert gateway.poll_calls == 1
    reconciliation = CanonicalDesktopProviderExecutionExecutor(
        fixture, EPISODE_002, gateway=FakeAsyncPaidProviderGateway()
    ).reconcile()
    assert len(reconciliation["provider_operation_ids"]) == 1
    assert reconciliation["pending_attempts"]
    assert reconciliation["blocked_requests"]
    assert not reconciliation["success_requests_skipped_on_resume"]
    assert gateway.provider_calls == 1


def test_unknown_attempt_without_provider_id_remains_blocked(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _ack(fixture)
    controller = DesktopProductionResumeController(fixture, EPISODE_002)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    gateway = FakePaidProviderGateway(unknown_at=1)
    with pytest.raises(DesktopProviderExecutionError, match="UNKNOWN_NO_AUTOMATIC_RETRY"):
        controller.execute_confirmed_resume(
            intent,
            authorization=controller.execution_authorization(intent),
            provider_gateway=gateway,
        )
    attempts = read_jsonl(
        fixture
        / "projects"
        / EPISODE_002
        / "orchestration"
        / "provider-execution-v1"
        / "provider-execution-attempt-receipts-v1.jsonl"
    )
    unknown = next(row for row in reversed(attempts) if row.get("status") == "UNKNOWN")
    result = reconcile_unknown_attempt(
        fixture, EPISODE_002, str(unknown["attempt_id"])
    )
    assert result["status"] == "SUBMISSION_STATUS_UNKNOWN"
    assert result["provider_operation_id"] is None
    assert result["lookup_performed"] is False


def test_results_persisted_before_transition_failure_is_recoverable(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _ack(fixture)
    controller = DesktopProductionResumeController(fixture, EPISODE_002)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)

    def inject(point: str) -> None:
        if point == "before_transition_commit":
            raise RuntimeError("INJECTED_LEDGER_APPEND_FAILURE")

    with pytest.raises(DesktopProviderExecutionError, match="RESULT_PERSISTED_BUT_TRANSITION_NOT_COMMITTED"):
        controller.execute_confirmed_resume(
            intent,
            authorization=controller.execution_authorization(intent),
            provider_gateway=FakePaidProviderGateway(),
            fault_injector=inject,
        )
    reconciliation = CanonicalDesktopProviderExecutionExecutor(
        fixture,
        EPISODE_002,
        gateway=FakePaidProviderGateway(),
    ).reconcile()
    assert reconciliation["state"] == "RESULT_PERSISTED_BUT_TRANSITION_NOT_COMMITTED"
    assert reconciliation["provider_resubmission"] is False


def _real_execution_receipt_manifest(path: Path) -> dict[str, str]:
    import hashlib

    result: dict[str, str] = {}
    if not path.exists():
        return result
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        h = hashlib.sha256()
        with item.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(block)
        result[str(item.relative_to(path)).replace("\\", "/")] = h.hexdigest()
    return result


_REAL_PROVIDER_EXECUTION_PATH = (
    REPO / "projects" / EPISODE_002 / "orchestration" / "provider-execution-v1"
)
_REAL_PROVIDER_EXECUTION_BASELINE = _real_execution_receipt_manifest(
    _REAL_PROVIDER_EXECUTION_PATH
)


def test_real_episode_execution_receipts_unchanged_by_tests() -> None:
    # Real production receipts may legitimately pre-exist.
    # The invariant is that tests must not create/delete/mutate them.
    assert (
        _real_execution_receipt_manifest(_REAL_PROVIDER_EXECUTION_PATH)
        == _REAL_PROVIDER_EXECUTION_BASELINE
    )


def test_legacy_autopilot_provider_resume_is_explicitly_blocked() -> None:
    v64 = (REPO / "src" / "application" / "siraj_one_click_autopilot_v6_4.py").read_text(
        encoding="utf-8"
    )
    v66 = (REPO / "src" / "application" / "siraj_autopilot_v6_6.py").read_text(
        encoding="utf-8"
    )
    legacy_provider = (
        REPO / "src" / "application" / "siraj_provider_execution_v6_2_1.py"
    ).read_text(encoding="utf-8")
    assert "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY" in v64
    assert "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY" in v66
    assert "LEGACY_PROVIDER_EXECUTION_BLOCKED" in legacy_provider
