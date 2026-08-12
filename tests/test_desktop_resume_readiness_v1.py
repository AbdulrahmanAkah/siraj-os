from dataclasses import replace
import json
from pathlib import Path
import shutil

import pytest

from src.application.desktop_resume_readiness_v1 import (
    DESKTOP_SOURCE,
    DesktopProductionResumeController,
    DesktopResumePolicyError,
    MEDIA_COST_PREFLIGHT,
    read_desktop_episode_state,
)
from src.application.desktop_media_cost_preflight_v1 import (
    CanonicalMediaCostPreflightExecutor,
    LOCAL_AUTH_SCOPE,
    MediaCostPreflightError,
)
from src.application.artifact_provenance_v1 import sha256_file
from src.application.episode_transition_ledger_v1 import project_state, read_entries
from src.application.worker_lifecycle_v1 import WorkerLifecycle, WorkerLifecycleError


REPO = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"


def _isolated_episode_repo(tmp_path: Path) -> Path:
    """Copy only the authoritative offline fixture inputs into a temp repo."""

    fixture = tmp_path / "siraj-fixture"
    relative_files = [
        f"projects/{EPISODE}/orchestration/episode-transition-ledger-v1.jsonl",
        f"projects/{EPISODE}/orchestration/episode-creative-promotion-state-v1.json",
        f"projects/{EPISODE}/orchestration/prompt-similarity-duplicate-gate-promoted-v1.json",
        f"projects/{EPISODE}/orchestration/luna-gate-001-local-closure-v1.json",
        f"projects/{EPISODE}/preproduction/audio-bound-storyboard-v6-1.json",
        f"projects/{EPISODE}/preproduction/audio-timestamps-and-beats-v6-1.json",
        f"projects/{EPISODE}/preproduction/siraj-creative-shot-direction-promoted-v1.json",
        f"projects/{EPISODE}/preproduction/siraj-promoted-provider-ready-prompt-plan-v1.json",
        "projects/_series/siraj-visual-mix-duplicate-policy-v6.2.1.json",
        "src/application/provider_model_contracts.py",
        "src/application/siraj_runware_provider_contract_v6_6_r9.py",
    ]
    for relative in relative_files:
        source = REPO / relative
        target = fixture / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # The real Episode 002 advances as the user exercises the pipeline.  The
    # transaction tests below need an isolated preflight-start fixture, so
    # remove only the two post-preflight receipts from the copied test ledger.
    # This never touches the repository artifact.
    ledger = fixture / f"projects/{EPISODE}/orchestration/episode-transition-ledger-v1.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [row for row in rows if row.get("stage") != MEDIA_COST_PREFLIGHT]
    ledger.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return fixture


def _offline_authorization() -> dict[str, object]:
    return {
        "authorization_id": "offline-desktop-preflight-test",
        "source": DESKTOP_SOURCE,
        "scope": LOCAL_AUTH_SCOPE,
        "episode_id": EPISODE,
        "provider_calls": 0,
        "paid_operation": False,
    }


def test_ep002_desktop_state_is_ledger_backed_and_paused() -> None:
    state = read_desktop_episode_state(REPO)
    assert state.current_stage == "PROVIDER_EXECUTION"
    assert state.alignment_gate == "PASS"
    assert state.duplicate_gate == "PASS"
    assert state.production_resume_authorized is False
    assert state.duration_seconds == 623.584
    assert state.shot_count == 55


def test_offline_desktop_resume_after_cost_envelope_reack_reaches_provider_stage() -> None:
    controller = DesktopProductionResumeController(REPO)
    observed: list[str] = []
    result = controller.simulate_offline_resume(
        source=DESKTOP_SOURCE,
        stage_runner=lambda stage: observed.append(stage) or {"fake": True},
    )
    assert result == {"fake": True}
    assert observed == ["PROVIDER_EXECUTION"]


def test_cli_and_direct_sources_are_rejected_before_a_runner_is_called() -> None:
    controller = DesktopProductionResumeController(REPO)
    with pytest.raises(DesktopResumePolicyError, match="DESKTOP_UI_ONLY"):
        controller.prepare_resume(source="CLI")


def test_network_deny_allows_only_the_read_only_desktop_flow(monkeypatch) -> None:
    import socket

    def denied(*args, **kwargs):
        raise AssertionError("NETWORK_ACCESS_FORBIDDEN")

    monkeypatch.setattr(socket, "create_connection", denied)
    controller = DesktopProductionResumeController(REPO)
    assert controller.inspect().current_stage == "PROVIDER_EXECUTION"
    assert controller.simulate_offline_resume(
        source=DESKTOP_SOURCE,
        stage_runner=lambda stage: stage,
    ) == "PROVIDER_EXECUTION"


def test_repeated_worker_start_and_watchdog_are_local_fail_closed() -> None:
    lifecycle = WorkerLifecycle().start_requested(now=0.0)
    with pytest.raises(WorkerLifecycleError, match="DUPLICATE_WORKER_START_BLOCKED"):
        lifecycle.start_requested(now=0.1)
    assert lifecycle.watchdog(now=31.0).error == "LOCAL_WORKER_HEARTBEAT_TIMEOUT"


def test_supported_launcher_uses_the_full_designed_window() -> None:
    app = (REPO / "src/presentation/desktop/app.py").read_text(encoding="utf-8")
    assert "SirajDesktopWindow" in app
    assert "CanonicalProductionDesktopWindow" not in app


def test_supported_full_window_opens_idle_and_reads_authoritative_state(monkeypatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from src.presentation.desktop.main_window import SirajDesktopWindow

    app = QApplication.instance() or QApplication([])
    ledger = REPO / "projects" / EPISODE / "orchestration" / "episode-transition-ledger-v1.jsonl"
    before = sha256_file(ledger)
    window = SirajDesktopWindow(REPO)
    try:
        assert window._canonical_state is not None
        assert window._canonical_state.current_stage == "PROVIDER_EXECUTION"
        assert window._canonical_state.alignment_gate == "PASS"
        assert window._canonical_state.duplicate_gate == "PASS"
        assert window.v6_command_center.primary.isEnabled()
        assert window.v6_command_center.request_metric.text().endswith("95")
        assert window._resume_worker is None
        assert window.windowTitle() != "SIRAJ Production Review"
        assert window.complete_workspace is not None
        assert sha256_file(ledger) == before
    finally:
        window.close()
        app.processEvents()


@pytest.mark.parametrize(
    "relative",
    [
        "scripts/desktop/run_end_to_end_production_v1.py",
        "scripts/desktop/run_consolidated_episode_production_controller_v2.py",
        "scripts/desktop/run_siraj_production_studio_v6_4.py",
        "scripts/desktop/run_siraj_production_studio_v6_0_1.py",
        "scripts/desktop/run_siraj_production_studio_v5_4_4.py",
    ],
)
def test_supported_legacy_resume_launchers_are_blocked(relative: str) -> None:
    assert "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY" in (REPO / relative).read_text(encoding="utf-8")


def test_isolated_media_cost_preflight_is_transactional_and_provider_free(tmp_path: Path) -> None:
    fixture = _isolated_episode_repo(tmp_path)
    ledger = fixture / "projects" / EPISODE / "orchestration" / "episode-transition-ledger-v1.jsonl"
    before = sha256_file(ledger)
    controller = DesktopProductionResumeController(fixture, EPISODE)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    outcome = CanonicalMediaCostPreflightExecutor(fixture, EPISODE).execute(
        intent,
        authorization=_offline_authorization(),
    )
    assert outcome.status == "PASS"
    assert outcome.next_stage == "PROVIDER_EXECUTION"
    assert outcome.next_stage_executed is False
    result_path = fixture / "projects" / EPISODE / "orchestration" / "media-cost-preflight-v1.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["provider_calls"] == 0
    assert result["paid_attempts_created"] == 0
    assert result["next_stage_executed"] is False
    assert result["authoritative_state"]["promoted_overlay_sha256"] == (
        "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
    )
    entries = read_entries(fixture, EPISODE)
    stage_entries = [entry for entry in entries if entry["stage"] == MEDIA_COST_PREFLIGHT]
    assert [entry["status"] for entry in stage_entries] == ["STARTED", "COMPLETED"]
    assert sha256_file(ledger) != before
    state = controller.inspect()
    assert state.current_stage == "PROVIDER_EXECUTION"
    assert state.status == "READY"


def test_stale_review_head_fails_closed_without_starting_stage(tmp_path: Path) -> None:
    fixture = _isolated_episode_repo(tmp_path)
    controller = DesktopProductionResumeController(fixture, EPISODE)
    intent = replace(controller.prepare_resume(source=DESKTOP_SOURCE), ledger_head_sha256="0" * 64)
    with pytest.raises(MediaCostPreflightError, match="AUTHORITATIVE_STATE_CHANGED_REVIEW_REQUIRED"):
        CanonicalMediaCostPreflightExecutor(fixture, EPISODE).execute(
            intent,
            authorization=_offline_authorization(),
        )
    assert len(read_entries(fixture, EPISODE)) == 19


def test_paid_or_wrong_episode_authorization_is_rejected_before_ledger_write(tmp_path: Path) -> None:
    fixture = _isolated_episode_repo(tmp_path)
    controller = DesktopProductionResumeController(fixture, EPISODE)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    authorization = _offline_authorization()
    authorization["paid_operation"] = True
    with pytest.raises(MediaCostPreflightError, match="DESKTOP_LOCAL_AUTHORIZATION_INVALID"):
        CanonicalMediaCostPreflightExecutor(fixture, EPISODE).execute(
            intent,
            authorization=authorization,
        )
    assert len(read_entries(fixture, EPISODE)) == 19


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("first_stage", "PROVIDER_EXECUTION", "INVALID_RESUME_STAGE"),
        ("promoted_overlay_sha256", "bad-overlay", "REVIEWED_OVERLAY_CHANGED"),
        ("structural_fingerprint", "bad-structure", "REVIEWED_STRUCTURAL_FINGERPRINT_CHANGED"),
    ],
)
def test_reviewed_input_identity_or_stage_mismatch_fails_closed(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    fixture = _isolated_episode_repo(tmp_path)
    controller = DesktopProductionResumeController(fixture, EPISODE)
    intent = replace(controller.prepare_resume(source=DESKTOP_SOURCE), **{field: value})
    with pytest.raises(MediaCostPreflightError, match=message):
        CanonicalMediaCostPreflightExecutor(fixture, EPISODE).execute(
            intent,
            authorization=_offline_authorization(),
        )
    assert len(read_entries(fixture, EPISODE)) == 19


def test_preflight_failure_is_persisted_and_does_not_project_success(tmp_path: Path) -> None:
    fixture = _isolated_episode_repo(tmp_path)

    def fail_builder(*args, **kwargs):
        raise RuntimeError("FAKE_PREFLIGHT_COMPUTATION_FAILURE")

    controller = DesktopProductionResumeController(fixture, EPISODE)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    executor = CanonicalMediaCostPreflightExecutor(
        fixture,
        EPISODE,
        preflight_builder=fail_builder,
    )
    with pytest.raises(RuntimeError, match="FAKE_PREFLIGHT_COMPUTATION_FAILURE"):
        executor.execute(intent, authorization=_offline_authorization())
    state = project_state(fixture, EPISODE)
    assert state.current_stage == MEDIA_COST_PREFLIGHT
    assert state.status == "FAILED"
    assert not executor.result_path.exists()
    failures = list(executor.result_path.parent.glob("media-cost-preflight-failure-*.json"))
    assert len(failures) == 1


def test_result_persistence_failure_is_recorded_as_failed(tmp_path: Path) -> None:
    fixture = _isolated_episode_repo(tmp_path)

    def fail_writer(*args, **kwargs):
        raise OSError("FAKE_RESULT_PERSISTENCE_FAILURE")

    controller = DesktopProductionResumeController(fixture, EPISODE)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    executor = CanonicalMediaCostPreflightExecutor(
        fixture,
        EPISODE,
        result_writer=fail_writer,
    )
    with pytest.raises(OSError, match="FAKE_RESULT_PERSISTENCE_FAILURE"):
        executor.execute(intent, authorization=_offline_authorization())
    assert project_state(fixture, EPISODE).status == "FAILED"
    assert list(executor.result_path.parent.glob("media-cost-preflight-failure-*.json"))


def test_partial_result_write_is_preserved_and_failed_receipt_is_appended(tmp_path: Path) -> None:
    fixture = _isolated_episode_repo(tmp_path)

    def partial_writer(path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{\"partial\":", encoding="utf-8")
        raise OSError("FAKE_INTERRUPTED_JSON_WRITE")

    controller = DesktopProductionResumeController(fixture, EPISODE)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    executor = CanonicalMediaCostPreflightExecutor(
        fixture,
        EPISODE,
        result_writer=partial_writer,
    )
    with pytest.raises(OSError, match="FAKE_INTERRUPTED_JSON_WRITE"):
        executor.execute(intent, authorization=_offline_authorization())
    assert executor.result_path.read_text(encoding="utf-8") == "{\"partial\":"
    assert project_state(fixture, EPISODE).status == "FAILED"
    assert list(executor.result_path.parent.glob("media-cost-preflight-failure-*.json"))


def test_transition_commit_failure_is_recoverable_without_rerun(tmp_path: Path) -> None:
    fixture = _isolated_episode_repo(tmp_path)
    calls = 0

    def append_once_then_fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("FAKE_LEDGER_APPEND_FAILURE")
        from src.application.episode_transition_ledger_v1 import append_transition_if_head

        return append_transition_if_head(*args, **kwargs)

    controller = DesktopProductionResumeController(fixture, EPISODE)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    executor = CanonicalMediaCostPreflightExecutor(
        fixture,
        EPISODE,
        ledger_appender=append_once_then_fail,
    )
    with pytest.raises(OSError, match="FAKE_LEDGER_APPEND_FAILURE"):
        executor.execute(intent, authorization=_offline_authorization())
    recovery = executor.recover()
    assert recovery.status == "RESULT_PERSISTED_BUT_TRANSITION_NOT_COMMITTED"
    assert recovery.recovery_action == "HUMAN_REVIEW_REQUIRED_NO_RERUN"
    assert project_state(fixture, EPISODE).status == "RUNNING"


def test_malformed_media_policy_fails_before_planning(tmp_path: Path) -> None:
    fixture = _isolated_episode_repo(tmp_path)
    policy_path = fixture / "projects" / "_series" / "siraj-visual-mix-duplicate-policy-v6.2.1.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["generated_video_max_ratio"] = "not-a-number"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    controller = DesktopProductionResumeController(fixture, EPISODE)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    with pytest.raises(MediaCostPreflightError, match="MEDIA_POLICY_NUMERIC_FIELDS_INVALID"):
        CanonicalMediaCostPreflightExecutor(fixture, EPISODE).execute(
            intent,
            authorization=_offline_authorization(),
        )
    assert project_state(fixture, EPISODE).status == "FAILED"


def test_duplicate_generated_video_direction_fails_pre_spend(tmp_path: Path) -> None:
    fixture = _isolated_episode_repo(tmp_path)
    plan_path = fixture / "projects" / EPISODE / "preproduction" / "siraj-promoted-provider-ready-prompt-plan-v1.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    generated = [item for item in plan["items"] if item["final_budget_treatment"] == "GENERATED_VIDEO"]
    assert len(generated) >= 2
    generated[1]["runware_positive_prompt_en"] = generated[0]["runware_positive_prompt_en"]
    generated[1]["contains_people"] = generated[0]["contains_people"]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    controller = DesktopProductionResumeController(fixture, EPISODE)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    with pytest.raises(MediaCostPreflightError, match="REPEATED_VIDEO_PLANNING_PAYLOAD"):
        CanonicalMediaCostPreflightExecutor(fixture, EPISODE).execute(
            intent,
            authorization=_offline_authorization(),
        )
    assert project_state(fixture, EPISODE).status == "FAILED"


def test_duplicate_resume_intent_cannot_start_second_transaction(tmp_path: Path) -> None:
    fixture = _isolated_episode_repo(tmp_path)
    controller = DesktopProductionResumeController(fixture, EPISODE)
    intent = controller.prepare_resume(source=DESKTOP_SOURCE)
    executor = CanonicalMediaCostPreflightExecutor(fixture, EPISODE)
    executor.execute(intent, authorization=_offline_authorization())
    with pytest.raises(MediaCostPreflightError, match="AUTHORITATIVE_STATE_CHANGED_REVIEW_REQUIRED"):
        executor.execute(intent, authorization=_offline_authorization())
    stage_entries = [entry for entry in read_entries(fixture, EPISODE) if entry["stage"] == MEDIA_COST_PREFLIGHT]
    assert [entry["status"] for entry in stage_entries] == ["STARTED", "COMPLETED"]


def test_worker_interruption_finishes_without_sticky_active_flag(tmp_path: Path) -> None:
    fixture = _isolated_episode_repo(tmp_path)
    controller = DesktopProductionResumeController(fixture, EPISODE)
    with pytest.raises(RuntimeError, match="WORKER_INTERRUPTED"):
        controller.simulate_offline_resume(
            source=DESKTOP_SOURCE,
            stage_runner=lambda stage: (_ for _ in ()).throw(RuntimeError("WORKER_INTERRUPTED")),
        )
    assert controller.worker_lifecycle.may_close
    assert controller._execution_active is False
