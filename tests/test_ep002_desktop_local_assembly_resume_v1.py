from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.application.desktop_resume_readiness_v1 import (
    DESKTOP_SOURCE,
    DesktopEpisodeState,
    DesktopProductionResumeController,
    DesktopResumeIntent,
)
from src.application.desktop_local_assembly_montage_v1 import (
    CanonicalDesktopLocalAssemblyMontageExecutor,
    LOCAL_AUTH_SCOPE,
    NEXT_STAGE,
    STAGE,
)


def _state(tmp_path: Path) -> DesktopEpisodeState:
    return DesktopEpisodeState(
        episode_id="episode-002-adam-temptation-fall-repentance",
        current_stage=STAGE,
        status="READY",
        completed_stages=(),
        alignment_gate="PASS",
        duplicate_gate="PASS",
        promoted_overlay_sha256="overlay",
        authoritative_structural_fingerprint="struct",
        provider_plan_contract_fingerprint="contract",
        duration_seconds=1.0,
        shot_count=1,
        timeline_discontinuities=0,
        ledger_path=str(tmp_path / "ledger.jsonl"),
        ledger_head_sha256="ledger-head",
        ledger_entry_count=1,
    )


def _intent() -> DesktopResumeIntent:
    return DesktopResumeIntent(
        episode_id="episode-002-adam-temptation-fall-repentance",
        first_stage=STAGE,
        source=DESKTOP_SOURCE,
        requires_explicit_human_action=True,
        ledger_head_sha256="ledger-head",
        promoted_overlay_sha256="overlay",
        structural_fingerprint="struct",
        execution_token="token",
    )


def _auth() -> dict:
    return {
        "authorization_id": "local-test",
        "source": DESKTOP_SOURCE,
        "scope": LOCAL_AUTH_SCOPE,
        "episode_id": "episode-002-adam-temptation-fall-repentance",
        "stage": STAGE,
        "execution_token": "token",
        "provider_calls": 0,
        "paid_operation": False,
    }


def _make_outputs(repo: Path, episode_id: str) -> Path:
    deliverable = repo / "projects" / episode_id / "deliverables" / "autopilot-v6-2-1"
    deliverable.mkdir(parents=True, exist_ok=True)
    master = deliverable / "episode-master-autopilot-v6-2-1.mp4"
    master.write_bytes(b"local-master")
    master_sha = hashlib.sha256(master.read_bytes()).hexdigest()
    receipt = deliverable / "episode-master-autopilot-v6-2-1-receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "siraj-local-assembly-montage-v6.2.1",
                "status": "PASS",
                "episode_id": episode_id,
                "master_path_relative": str(master.relative_to(repo)).replace("\\", "/"),
                "master_sha256": master_sha,
                "duration_seconds": 1.0,
                "generated_video_policy": {},
                "duplicate_gate": "PASS",
                "animated_stills_motion": "ACTIVE",
                "video": {"width": 1920, "height": 1080, "fps": 30},
                "audio": {"sample_rate": 48000, "channels": 2, "codec": "aac"},
                "next_stage": NEXT_STAGE,
            }
        ),
        encoding="utf-8",
    )
    return receipt


def test_local_authorization_is_nonpaid_and_desktop_capability_bound(tmp_path):
    controller = DesktopProductionResumeController(tmp_path)
    capability = object()
    controller._pending_execution_capability = capability
    intent = _intent()
    auth = controller.execution_authorization(intent)
    assert auth["scope"] == LOCAL_AUTH_SCOPE
    assert auth["paid_operation"] is False
    assert auth["provider_calls"] == 0
    assert auth["_desktop_capability"] is capability


def test_local_executor_renders_once_then_cas_commits(tmp_path):
    episode_id = _intent().episode_id
    calls = {"assembler": 0, "ledger": 0}

    def assembler(repo, episode):
        calls["assembler"] += 1
        return _make_outputs(repo, episode)

    def appender(*args, **kwargs):
        calls["ledger"] += 1
        assert kwargs["expected_ledger_sha256"] == "ledger-head"
        assert kwargs["stage"] == STAGE
        assert kwargs["previous_stage"] == "PROVIDER_EXECUTION"
        assert kwargs["status"] == "COMPLETED"
        assert kwargs["metadata"]["next_stage_executed"] is False
        assert kwargs["metadata"]["provider_calls"] == 0
        return {"transition_id": "tx-local"}

    ledger = tmp_path / "projects" / episode_id / "orchestration" / "episode-transition-ledger-v1.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_bytes(b"ledger")

    executor = CanonicalDesktopLocalAssemblyMontageExecutor(
        tmp_path,
        episode_id,
        assembler=assembler,
        ledger_appender=appender,
        state_reader=lambda repo, ep: _state(tmp_path),
    )
    result = executor.execute(_intent(), authorization=_auth())
    assert result.status == "PASS"
    assert result.next_stage == NEXT_STAGE
    assert result.next_stage_executed is False
    assert result.provider_calls == 0
    assert result.paid_attempts_created == 0
    assert result.recovered_existing_receipt is False
    assert calls == {"assembler": 1, "ledger": 1}


def test_existing_valid_receipt_is_committed_without_rerender(tmp_path):
    episode_id = _intent().episode_id
    _make_outputs(tmp_path, episode_id)
    ledger = tmp_path / "projects" / episode_id / "orchestration" / "episode-transition-ledger-v1.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_bytes(b"ledger")

    def forbidden_assembler(repo, episode):
        raise AssertionError("existing durable receipt must not rerender")

    seen = {}

    def appender(*args, **kwargs):
        seen.update(kwargs)
        return {"transition_id": "tx-recovery"}

    executor = CanonicalDesktopLocalAssemblyMontageExecutor(
        tmp_path,
        episode_id,
        assembler=forbidden_assembler,
        ledger_appender=appender,
        state_reader=lambda repo, ep: _state(tmp_path),
    )
    result = executor.execute(_intent(), authorization=_auth())
    assert result.recovered_existing_receipt is True
    assert result.transition_id == "tx-recovery"
    assert seen["metadata"]["recovered_existing_receipt"] is True


def test_desktop_sources_expose_local_stage_and_fail_closed_for_unsupported():
    repo = Path(__file__).resolve().parents[1]
    readiness = (repo / "src/application/desktop_resume_readiness_v1.py").read_text(
        encoding="utf-8-sig"
    )
    main = (repo / "src/presentation/desktop/main_window.py").read_text(
        encoding="utf-8-sig"
    )
    v6 = (repo / "src/presentation/desktop/v6_dashboard_integration.py").read_text(
        encoding="utf-8-sig"
    )
    assert "SIRAJ_EP002_CANONICAL_DESKTOP_LOCAL_ASSEMBLY_RESUME_V1" in readiness
    assert "intent.first_stage == LOCAL_ASSEMBLY_AND_MONTAGE" in readiness
    assert "CANONICAL_DESKTOP_STAGE_NOT_IMPLEMENTED:" in readiness
    assert "intent.first_stage == LOCAL_ASSEMBLY_AND_MONTAGE" in main
    assert "CANONICAL_LOCAL_ASSEMBLY_AND_MONTAGE_REQUESTED" in main
    assert '"LOCAL_ASSEMBLY_AND_MONTAGE"' in v6
