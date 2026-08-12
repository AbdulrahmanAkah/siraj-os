from __future__ import annotations

import uuid
from pathlib import Path

from src.application.desktop_provider_execution_v1 import (
    CanonicalDesktopProviderExecutionExecutor,
    CanonicalRunwarePaidGateway,
    FakePaidProviderGateway,
)


def _unit():
    return {
        "unit_id": "EP002-SH-001-V01",
        "request_id": "EP002-SH-001-V01",
        "shot_id": "EP002-SH-001",
        "provider": "RUNWARE",
        "model": "google:veo@3.1-lite",
        "payload_sha256": "a" * 64,
    }


def test_runtime_uuid_is_valid_v4_stable_for_same_attempt_and_distinct_for_new_attempt(tmp_path: Path):
    executor = CanonicalDesktopProviderExecutionExecutor(
        tmp_path,
        gateway=CanonicalRunwarePaidGateway(
            read_only_transport=lambda _payload: {"data": []}
        ),
    )
    unit = _unit()
    a = executor._runtime_runware_task_uuid(
        "11111111-1111-5111-8111-111111111111", unit
    )
    b = executor._runtime_runware_task_uuid(
        "11111111-1111-5111-8111-111111111111", unit
    )
    c = executor._runtime_runware_task_uuid(
        "22222222-2222-5222-8222-222222222222", unit
    )
    assert uuid.UUID(a).version == 4
    assert uuid.UUID(c).version == 4
    assert a == b
    assert a != c


def test_planning_payload_remains_permissive_until_runtime_identity_materialization():
    source = Path(
        "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    method_start = source.index("    def _task_for_unit(")
    method_end = source.index("\n    def ", method_start + 10)
    method = source[method_start:method_end]
    assert "require_uuid_v4=False" in method
    assert '"taskUUID": planning_identity' in method


def test_runtime_materialization_occurs_after_attempt_identity_and_before_paid_request():
    source = Path(
        "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    attempt_pos = source.index("attempt_id = _attempt_id(")
    runtime_pos = source.index(
        "provider_task_uuid = self._runtime_runware_task_uuid(",
        attempt_pos,
    )
    request_pos = source.index("PaidOperationRequest(", runtime_pos)
    assert attempt_pos < runtime_pos < request_pos


def test_fake_gateway_still_does_not_require_runtime_uuid(tmp_path: Path):
    executor = CanonicalDesktopProviderExecutionExecutor(
        tmp_path,
        gateway=FakePaidProviderGateway(),
    )
    assert bool(getattr(executor.gateway, "requires_uuid4", False)) is False
