from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"
UNIT = "EP002-SH-022-V02"
AUTH_ID = '1bffdc5b-4263-4de4-a724-f56303f53850'
NEW_ATTEMPT = '5c34cca2-fd73-54ee-9c96-5e0e677bdab5'
NEW_TASK_UUID = '3ec98f35-0a6b-49ab-bae7-c81f50ecd23c'
LATEST_RECON = "d71aec21-e772-42e0-9dd5-65c45c8ba8ec"


def test_live_auth_matches_second_reconciliation_and_is_unconsumed():
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from src.application.provider_attempt_reconciliation_v1 import (
        reconciliation_for_request,
    )
    from src.application.provider_terminal_replacement_authorization_v1 import (
        consumption_for_authorization,
        terminal_replacement_authorization_for_request,
        terminal_replacement_authorization_matches_reconciliation,
    )

    auth = terminal_replacement_authorization_for_request(
        REPO, EPISODE, UNIT
    )
    assert auth is not None
    assert auth["authorization_id"] == AUTH_ID
    assert auth["historical_attempt_id"] == (
        "77b24dfc-e910-5dee-8c94-fd3cae6d20f1"
    )
    assert auth["reconciliation_receipt_id"] == LATEST_RECON
    assert auth["replacement_attempt_id"] == NEW_ATTEMPT
    assert auth["replacement_provider_task_uuid"] == NEW_TASK_UUID
    assert auth["historical_person_generation"] == "dont_allow"
    assert auth["replacement_person_generation"] == "allow_adult"
    assert float(auth["planned_cost_usd"]) == 0.3
    assert float(auth["maximum_cost_usd"]) == 0.5
    assert int(auth["maximum_provider_requests"]) == 1
    assert auth["automatic_paid_retry"] is False
    assert auth["automatic_paid_resubmission"] is False

    latest = reconciliation_for_request(REPO, EPISODE, UNIT)
    assert latest is not None
    assert latest["receipt_id"] == LATEST_RECON
    assert terminal_replacement_authorization_matches_reconciliation(
        auth, latest
    )
    assert consumption_for_authorization(
        REPO, EPISODE, AUTH_ID
    ) is None


def test_planned_task_uses_nested_dont_allow_and_override_uses_nested_allow_adult():
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from src.application.desktop_media_cost_preflight_v1 import (
        read_persisted_media_cost_preflight,
    )
    from src.application.desktop_provider_execution_v1 import (
        CanonicalDesktopProviderExecutionExecutor,
    )
    from src.application.provider_terminal_replacement_authorization_v1 import (
        apply_terminal_replacement_prompt,
        terminal_replacement_authorization_for_request,
    )

    auth = terminal_replacement_authorization_for_request(
        REPO, EPISODE, UNIT
    )
    executor = CanonicalDesktopProviderExecutionExecutor(REPO, EPISODE)
    review = read_persisted_media_cost_preflight(REPO, EPISODE)
    prompt_items = executor._prompt_items(review)
    preflight = json.loads(
        (
            REPO
            / "projects"
            / EPISODE
            / "orchestration"
            / "media-cost-preflight-v2.json"
        ).read_text(encoding="utf-8-sig")
    )
    unit = next(row for row in preflight["units"] if row["unit_id"] == UNIT)
    task = dict(executor._task_for_unit(unit, prompt_items))

    assert task.get("personGeneration") is None
    assert (
        task["providerSettings"]["google"]["personGeneration"]
        == "dont_allow"
    )
    assert task["providerSettings"]["google"]["generateAudio"] is False

    task["taskUUID"] = NEW_TASK_UUID
    revised = apply_terminal_replacement_prompt(task, auth)

    assert revised["taskUUID"] == NEW_TASK_UUID
    assert revised["positivePrompt"] == auth["replacement_positive_prompt"]
    assert (
        revised["providerSettings"]["google"]["personGeneration"]
        == "allow_adult"
    )
    assert revised["providerSettings"]["google"]["generateAudio"] is False
    assert (
        task["providerSettings"]["google"]["personGeneration"]
        == "dont_allow"
    )


def test_old_consumed_authorization_remains_in_consumption_history():
    consumption = (
        REPO
        / "projects"
        / EPISODE
        / "orchestration"
        / "provider-execution-v1"
        / "terminal-provider-replacement-consumption-v1.jsonl"
    )
    rows = [
        json.loads(raw)
        for raw in consumption.read_text(
            encoding="utf-8-sig"
        ).splitlines()
        if raw.strip()
    ]
    old = [
        row
        for row in rows
        if row.get("authorization_id")
        == "c4c0be90-9c36-4753-9ef7-c4ff32495c09"
    ]
    assert len(old) == 1
    assert old[0]["replacement_attempt_id"] == (
        "77b24dfc-e910-5dee-8c94-fd3cae6d20f1"
    )


def test_fresh_process_projection_is_eligible():
    code = r"""
import json
import sys
from pathlib import Path
REPO = Path(r"C:\SIRAJ\Repositories\siraj-os")
EPISODE = "episode-002-adam-temptation-fall-repentance"
UNIT = "EP002-SH-022-V02"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from src.application.desktop_provider_execution_v1 import (
    CanonicalDesktopProviderExecutionExecutor,
    _siraj_provider_execution_recovery_session_v2,
)
from src.application.provider_attempt_reconciliation_v1 import (
    NOT_SUBMITTED_ELIGIBLE,
)
executor = CanonicalDesktopProviderExecutionExecutor(REPO, EPISODE)
state = executor.reconcile()
observed = (state.get("request_states") or {}).get(UNIT)
session = _siraj_provider_execution_recovery_session_v2(
    REPO, EPISODE, state
)
result = {
    "request_state": observed,
    "blocked": UNIT in (state.get("blocked_requests") or []),
    "eligible": UNIT in (
        state.get("not_submitted_requests_eligible") or []
    ),
    "session": session,
}
if observed != NOT_SUBMITTED_ELIGIBLE:
    raise RuntimeError(json.dumps(result))
if result["blocked"] or not result["eligible"] or not session:
    raise RuntimeError(json.dumps(result))
print(json.dumps(result))
"""
    cp = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", code],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert cp.returncode == 0, cp.stdout + "\n" + cp.stderr
