from __future__ import annotations

import ast
import json
from pathlib import Path

from src.application.desktop_media_cost_preflight_v1 import (
    read_persisted_media_cost_preflight,
)
from src.application.desktop_provider_execution_v1 import (
    CanonicalDesktopProviderExecutionExecutor,
    _siraj_durable_completed_provider_units_v2,
)
from src.application.provider_terminal_replacement_authorization_v1 import (
    consumption_for_authorization,
    terminal_replacement_authorization_for_request,
)

REPO = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"
TARGET = "EP002-SH-022-V02"
SH001 = "EP002-SH-001-V01"
AUTH_ID = "1bffdc5b-4263-4de4-a724-f56303f53850"
REPLACEMENT_ATTEMPT = "5c34cca2-fd73-54ee-9c96-5e0e677bdab5"
REPLACEMENT_TASK_UUID = "3ec98f35-0a6b-49ab-bae7-c81f50ecd23c"


def _provider_units():
    preflight = json.loads(
        (
            REPO
            / "projects"
            / EPISODE
            / "orchestration"
            / "media-cost-preflight-v2.json"
        ).read_text(encoding="utf-8-sig")
    )
    return sorted(
        [
            row
            for row in preflight["units"]
            if str(row.get("provider") or "").upper() == "RUNWARE"
        ],
        key=lambda row: int(row.get("queue_index") or 0),
    )


def test_actual_ep002_durable_completion_chain_is_38_and_target_is_next():
    executor = CanonicalDesktopProviderExecutionExecutor(REPO, EPISODE)
    review = read_persisted_media_cost_preflight(REPO, EPISODE)
    binding = executor._binding(review)
    units = _provider_units()
    assert len(units) == 95

    proven = _siraj_durable_completed_provider_units_v2(
        REPO,
        EPISODE,
        units,
        binding,
    )
    assert len(proven) == 38
    assert SH001 in proven
    assert TARGET not in proven

    first_remaining = next(
        str(row.get("request_id") or row.get("unit_id") or "")
        for row in units
        if str(row.get("request_id") or row.get("unit_id") or "")
        not in proven
    )
    assert first_remaining == TARGET


def test_live_replacement_authorization_is_unconsumed_exact_one_request():
    auth = terminal_replacement_authorization_for_request(
        REPO,
        EPISODE,
        TARGET,
    )
    assert auth is not None
    assert auth["authorization_id"] == AUTH_ID
    assert auth["replacement_attempt_id"] == REPLACEMENT_ATTEMPT
    assert auth["replacement_provider_task_uuid"] == REPLACEMENT_TASK_UUID
    assert int(auth["maximum_provider_requests"]) == 1
    assert float(auth["planned_cost_usd"]) == 0.3
    assert float(auth["maximum_cost_usd"]) == 0.5
    assert auth["automatic_paid_retry"] is False
    assert auth["automatic_paid_resubmission"] is False
    assert consumption_for_authorization(
        REPO,
        EPISODE,
        AUTH_ID,
    ) is None


def test_source_scope_gate_precedes_provider_boundary_and_skips_only_proven():
    source = (
        REPO / "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    assert "SIRAJ_EP002_ONE_UNIT_PAID_SCOPE_PAUSE_GUARD_V2" in source
    prelude = source.index("_siraj_paid_scope_guard_active_v2 = False")
    loop = source.index("for ordinal, unit in enumerate(", prelude)
    gate = source.index(
        "RECOVERY_NEXT_PAID_UNIT_OUTSIDE_EXPLICIT_AUTHORIZATION",
        loop,
    )
    request = source.index("request = PaidOperationRequest(", gate)
    consume = source.index(
        "consume_terminal_replacement_authorization(",
        request,
    )
    submit = source.index("gateway_result = self.gateway.submit(", consume)
    assert prelude < loop < gate < request < consume < submit
    region = source[loop:request]
    assert "_siraj_durable_completed_units_v2" in region
    assert "continue" in region


def test_source_success_pause_is_after_durable_success_and_before_next_stage():
    source = (
        REPO / "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    completed = source.index('"status": "ATTEMPT_COMPLETED"')
    pause = source.index(
        '"status": "STAGE_PAUSED_AUTHORIZATION_SCOPE"',
        completed,
    )
    results = source.index('"status": "RESULTS_PERSISTED"', pause)
    assert completed < pause < results
    scoped = source[pause:results]
    assert "remaining_stage_not_authorized" in scoped
    assert (
        "EXPLICIT_REPLACEMENT_COMPLETED_"
        in scoped
    )
    assert (
        "REMAINING_STAGE_REQUIRES_SEPARATE_AUTHORIZATION"
        in scoped
    )


def test_prior_scope_pause_blocks_later_resume_before_provider_loop():
    source = (
        REPO / "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    prelude = source.index("_siraj_prior_scope_pauses_v2")
    loop = source.index("for ordinal, unit in enumerate(", prelude)
    blocker = source.index(
        '"REMAINING_STAGE_REQUIRES_SEPARATE_AUTHORIZATION"',
        prelude,
    )
    assert prelude < blocker < loop


def test_execute_ast_has_single_paid_submit_site():
    source = (
        REPO / "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    execute = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == (
            "CanonicalDesktopProviderExecutionExecutor"
        ):
            execute = next(
                child
                for child in node.body
                if isinstance(child, ast.FunctionDef)
                and child.name == "execute"
            )
            break
    assert execute is not None
    text = ast.unparse(execute)
    assert text.count("gateway_result = self.gateway.submit") == 1
    assert "STAGE_PAUSED_AUTHORIZATION_SCOPE" in text
    assert "RECOVERY_NEXT_PAID_UNIT_OUTSIDE_EXPLICIT_AUTHORIZATION" in text
