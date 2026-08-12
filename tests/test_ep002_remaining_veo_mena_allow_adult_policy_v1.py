from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"
TARGET = "EP002-SH-022-V02"
THIRD_ATTEMPT = "5c34cca2-fd73-54ee-9c96-5e0e677bdab5"
AUTH_ID = "1bffdc5b-4263-4de4-a724-f56303f53850"


def _pg(task):
    return (
        task["providerSettings"]["google"]["personGeneration"]
    )


def test_actual_remaining_plan_is_56_with_33_dont_allow_and_10_allow_adult():
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from src.application.desktop_media_cost_preflight_v1 import (
        read_persisted_media_cost_preflight,
    )
    from src.application.desktop_provider_execution_v1 import (
        CanonicalDesktopProviderExecutionExecutor,
        _siraj_durable_completed_provider_units_v2,
    )

    preflight = json.loads(
        (
            REPO
            / "projects"
            / EPISODE
            / "orchestration"
            / "media-cost-preflight-v2.json"
        ).read_text(encoding="utf-8-sig")
    )
    provider_units = [
        dict(row)
        for row in preflight["units"]
        if str(row.get("provider") or "").upper() == "RUNWARE"
    ]
    assert len(provider_units) == 95

    executor = CanonicalDesktopProviderExecutionExecutor(REPO, EPISODE)
    review = read_persisted_media_cost_preflight(REPO, EPISODE)
    binding = executor._binding(review)
    prompt_items = executor._prompt_items(review)
    durable = _siraj_durable_completed_provider_units_v2(
        REPO, EPISODE, provider_units, binding
    )
    assert len(durable) == 39
    assert durable[TARGET] == THIRD_ATTEMPT

    remaining = [
        unit
        for unit in provider_units
        if str(unit.get("request_id") or unit.get("unit_id") or "")
        not in durable
    ]
    assert len(remaining) == 56

    veo = [
        unit
        for unit in remaining
        if str(unit.get("model") or "") == "google:veo@3.1-lite"
    ]
    assert len(veo) == 43

    counts = {"dont_allow": 0, "allow_adult": 0}
    for unit in veo:
        task = executor._task_for_unit(unit, prompt_items)
        counts[_pg(task)] += 1
    assert counts == {"dont_allow": 33, "allow_adult": 10}


def test_runtime_policy_normalizes_all_43_remaining_veo_without_mutating_input():
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from src.application.desktop_media_cost_preflight_v1 import (
        read_persisted_media_cost_preflight,
    )
    from src.application.desktop_provider_execution_v1 import (
        CanonicalDesktopProviderExecutionExecutor,
        _siraj_durable_completed_provider_units_v2,
        _siraj_ep002_veo_mena_allow_adult_runtime_policy_v1,
    )

    preflight = json.loads(
        (
            REPO
            / "projects"
            / EPISODE
            / "orchestration"
            / "media-cost-preflight-v2.json"
        ).read_text(encoding="utf-8-sig")
    )
    provider_units = [
        dict(row)
        for row in preflight["units"]
        if str(row.get("provider") or "").upper() == "RUNWARE"
    ]
    executor = CanonicalDesktopProviderExecutionExecutor(REPO, EPISODE)
    review = read_persisted_media_cost_preflight(REPO, EPISODE)
    binding = executor._binding(review)
    prompt_items = executor._prompt_items(review)
    durable = _siraj_durable_completed_provider_units_v2(
        REPO, EPISODE, provider_units, binding
    )

    changed = 0
    noop = 0
    for unit in provider_units:
        uid = str(unit.get("request_id") or unit.get("unit_id") or "")
        if uid in durable:
            continue
        if str(unit.get("model") or "") != "google:veo@3.1-lite":
            continue
        original = executor._task_for_unit(unit, prompt_items)
        before = _pg(original)
        revised, metadata = (
            _siraj_ep002_veo_mena_allow_adult_runtime_policy_v1(
                EPISODE, unit, original
            )
        )
        assert _pg(revised) == "allow_adult"
        assert _pg(original) == before
        assert metadata["preflight_artifact_mutated"] is False
        assert metadata["automatic_paid_retry"] is False
        assert metadata["automatic_paid_resubmission"] is False
        if before == "dont_allow":
            assert revised is not original
            assert metadata["applied"] is True
            changed += 1
        else:
            assert revised is original
            assert metadata["applied"] is False
            noop += 1

    assert changed == 33
    assert noop == 10


def test_runtime_policy_does_not_change_non_veo_task():
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from src.application.desktop_provider_execution_v1 import (
        _siraj_ep002_veo_mena_allow_adult_runtime_policy_v1,
    )
    unit = {
        "unit_id": "X",
        "provider": "RUNWARE",
        "model": "bytedance:seedream@5.0-pro",
    }
    task = {"taskType": "imageInference"}
    revised, metadata = (
        _siraj_ep002_veo_mena_allow_adult_runtime_policy_v1(
            EPISODE, unit, task
        )
    )
    assert revised is task
    assert metadata is None


def test_source_applies_policy_after_replacement_override_and_before_paid_request():
    source = (
        REPO / "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    marker = source.index(
        "SIRAJ_EP002_VEO_MENA_ALLOW_ADULT_RUNTIME_POLICY_V1"
    )
    replacement = source.index(
        "task = apply_terminal_replacement_prompt(",
        marker,
    )
    policy = source.index(
        "_siraj_ep002_veo_mena_allow_adult_runtime_policy_v1(",
        replacement,
    )
    paid = source.index("request = PaidOperationRequest(", policy)
    consume = source.index(
        "consume_terminal_replacement_authorization(",
        paid,
    )
    submit = source.index("gateway_result = self.gateway.submit(", consume)
    assert replacement < policy < paid < consume < submit


def test_intent_receipt_records_runtime_policy_metadata():
    source = (
        REPO / "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    assert '"runtime_person_generation_policy": (' in source
    assert "_siraj_ep002_veo_mena_policy_v1" in source


def test_current_scope_pause_remains_and_no_new_authorization_is_created():
    stage = (
        REPO
        / "projects"
        / EPISODE
        / "orchestration"
        / "provider-execution-v1"
        / "provider-execution-stage-receipts-v1.jsonl"
    )
    if not stage.is_file():
        stage = stage.with_name("stage-receipts-v1.jsonl")
    rows = [
        json.loads(raw)
        for raw in stage.read_text(encoding="utf-8-sig").splitlines()
        if raw.strip()
    ]
    pauses = [
        row
        for row in rows
        if row.get("status") == "STAGE_PAUSED_AUTHORIZATION_SCOPE"
        and row.get("scope_authorization_id") == AUTH_ID
    ]
    assert len(pauses) == 1
    assert pauses[0]["remaining_stage_not_authorized"] is True
