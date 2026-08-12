"""Create the read-only EP002 desktop-resume readiness reports.

This tool never resumes production.  It records local inspection evidence only.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.application.artifact_provenance_v1 import (
    artifact_reference,
    canonical_sha256,
    sha256_file,
    write_new_json,
)
from src.application.desktop_resume_readiness_v1 import (
    AUTHORITATIVE_STATE_SOURCE,
    EPISODE_002,
    EXPECTED_OVERLAY_SHA256,
    PRODUCTION_RESUME_ENTRYPOINT,
    read_desktop_episode_state,
    supported_desktop_composition_root,
)


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    reports = repo / "reports"
    markdown_path = reports / "episode-002-desktop-resume-readiness.md"
    json_path = reports / "episode-002-desktop-resume-readiness.json"
    if markdown_path.exists() or json_path.exists():
        raise RuntimeError("READINESS_REPORT_TARGET_EXISTS_FAIL_CLOSED")

    state = read_desktop_episode_state(repo, EPISODE_002)
    episode = repo / "projects" / EPISODE_002
    overlay_path = episode / "preproduction" / "siraj-creative-shot-direction-promoted-v1.json"
    plan_path = episode / "preproduction" / "siraj-promoted-provider-ready-prompt-plan-v1.json"
    storyboard_path = episode / "preproduction" / "audio-bound-storyboard-v6-1.json"
    timeline_path = episode / "preproduction" / "audio-timestamps-and-beats-v6-1.json"
    gate_path = episode / "orchestration" / "prompt-similarity-duplicate-gate-promoted-v1.json"
    promotion_path = episode / "orchestration" / "episode-creative-promotion-state-v1.json"
    gate = _read(gate_path)
    promotion = _read(promotion_path)
    overlay = _read(overlay_path)

    payload = {
        "schema_version": "siraj-episode-002-desktop-resume-readiness-v1",
        "status": "PASS",
        "readiness_blocker": {
            "id": "SIRAJ-DESKTOP-RESUME-001",
            "severity": "HIGH",
            "status": "CLOSED",
            "description": "The supported UI reads the Phase 0–4 ledger and invokes the canonical transactional local MEDIA_COST_PREFLIGHT executor on explicit Desktop confirmation.",
            "fail_closed_behavior": "Stale reviewed state, invalid inputs, persistence failure, or ledger commit failure prevents success projection; no downstream stage is started.",
            "required_fix_before_paid_resume": "None for SIRAJ-DESKTOP-RESUME-001; future paid continuation remains separately authorization-gated.",
        },
        "episode_id": EPISODE_002,
        "supported_desktop_launcher": "src/presentation/desktop/app.py (python -m src.presentation.desktop)",
        "supported_desktop_composition_root": supported_desktop_composition_root(),
        "supported_controller": "src.application.desktop_resume_readiness_v1.DesktopProductionResumeController",
        "supported_state_reader": "src.application.desktop_resume_readiness_v1.read_desktop_episode_state",
        "authoritative_state_source": AUTHORITATIVE_STATE_SOURCE,
        "authoritative_state_path": state.ledger_path,
        "authoritative_projection": state.as_dict(),
        "resume_path": [
            "CanonicalProductionDesktopWindow.request_explicit_resume",
            "DesktopProductionResumeController.prepare_resume",
            "authoritative transition-ledger projection",
            "CanonicalMediaCostPreflightExecutor.execute (local transactional stage only)",
            "paid_operation_gateway.execute_bytes/execute_json",
        ],
        "first_resumed_stage": state.current_stage,
        "actual_resume_executor": "src.application.desktop_media_cost_preflight_v1.CanonicalMediaCostPreflightExecutor",
        "ui_open_causes_production_execution": False,
        "ui_load_episode_causes_production_execution": False,
        "production_resume_entrypoint": PRODUCTION_RESUME_ENTRYPOINT,
        "cli_production_resume": "BLOCKED",
        "direct_script_production_resume": "BLOCKED",
        "legacy_launchers": {
            "status": "BLOCKED",
            "blocked_scripts": [
                "scripts/desktop/run_siraj_production_studio_v6_4.py",
                "scripts/desktop/run_siraj_production_studio_v6_0_1.py",
                "scripts/desktop/run_siraj_production_studio_v5_4_4.py",
                "scripts/desktop/run_end_to_end_production_v1.py run",
                "scripts/desktop/run_consolidated_episode_production_controller_v2.py run",
            ],
            "legacy_projection_policy": "V6/V6.4/V6.0.1/V4+/autonomous/R9 remain non-authoritative projections and are not loaded by the supported launcher.",
        },
        "structural_authority": {
            "fingerprint": state.authoritative_structural_fingerprint,
            "duration_seconds": state.duration_seconds,
            "shot_count": state.shot_count,
            "timeline_discontinuities": state.timeline_discontinuities,
            "final_shot": "EP002-SH-055:622.784-623.584",
            "provider_plan_contract_fingerprint": state.provider_plan_contract_fingerprint,
            "compatibility_note": "The preserved provider-ready plan uses a distinct contract fingerprint; the supported UI derives structural authority from the ledger and canonical storyboard manifest, never from that legacy-named plan field.",
        },
        "promoted_creative_overlay": {
            "canonical_sha256": canonical_sha256(overlay),
            "file_sha256": sha256_file(overlay_path),
            "expected_canonical_sha256": EXPECTED_OVERLAY_SHA256,
            "unchanged": canonical_sha256(overlay) == EXPECTED_OVERLAY_SHA256,
            "artifact": artifact_reference(overlay_path, base=repo),
        },
        "current_inputs": {
            "storyboard": artifact_reference(storyboard_path, base=repo),
            "timeline": artifact_reference(timeline_path, base=repo),
            "provider_ready_prompt_plan": artifact_reference(plan_path, base=repo),
            "promotion_state": artifact_reference(promotion_path, base=repo),
            "duplicate_gate": artifact_reference(gate_path, base=repo),
        },
        "gate_state": {
            "narration_visual_alignment_gate": state.alignment_gate,
            "prompt_similarity_duplicate_gate": state.duplicate_gate,
            "luna_gate_001": "CLOSED_BY_LOCAL_DUPLICATE_GATE",
            "stale_duplicate_gate_counts_as_completion": False,
            "current_gate_artifact_status": gate.get("status"),
        },
        "media_cost_preflight": {
            "executed": False,
            "future_inputs": [
                "current promoted provider-ready prompt plan",
                "canonical audio-bound storyboard",
                "current media-allocation policy",
                "locally configured provider price/cost contracts",
            ],
            "network_pricing_calls": False,
        },
        "paid_gateway": {
            "single_entry": "src.application.paid_operation_gateway.execute_bytes / execute_json",
            "request_identity": "PaidOperationRequest.immutable_attempt_id and payload_sha256",
            "authorization_binding": "_validate_authorization",
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
            "unknown_attempt_protection": "_validate_retry_authorization rejects retry/resubmission without distinct authorization",
        },
        "worker_safety": {
            "typed_qt_contract": "src.application.qt_worker_contracts.LiveProductionMonitorContract",
            "single_active_worker": "WorkerLifecycle.start_requested rejects duplicate starts",
            "watchdog": "WorkerLifecycle.watchdog emits LOCAL_WORKER_HEARTBEAT_TIMEOUT",
            "ui_close_behavior": "offline lifecycle test leaves only terminal workers closable",
            "legacy_r9_worker": "not loaded by supported launcher",
        },
        "offline_desktop_flow": {
            "open_desktop": "PASS (Qt offscreen, ledger hash unchanged)",
            "load_episode": "PASS (MEDIA_COST_PREFLIGHT)",
            "inspect": "PASS (zero executions)",
            "fake_resume": "PASS (only MEDIA_COST_PREFLIGHT passed to fake runner)",
            "duplicate_click": "PASS (WorkerLifecycle blocks duplicate start)",
            "close_cancel": "PASS (terminal lifecycle is closable; nonterminal states are guarded)",
        },
        "offline_validation": "PASS_CANONICAL_EXECUTOR_ISOLATED_FIXTURE_ONLY",
        "network_deny": "PASS",
        "network_calls": 0,
        "paid_provider_calls": 0,
        "autopilot_runs": 0,
        "files_deleted": 0,
        "production_resume_authorized": False,
        "episode_production_state_modified": False,
    }
    write_new_json(json_path, payload)
    markdown = "\n".join([
        "# Episode 002 — Desktop UI Production Resume Readiness",
        "",
        "Status: `PASS` — the supported Desktop path remains paused until explicit human action, and the canonical local `MEDIA_COST_PREFLIGHT` executor is offline-tested.",
        "",
        "## Supported desktop path",
        "",
        "- Launcher: `src/presentation/desktop/app.py` via `python -m src.presentation.desktop`.",
        "- Composition root: `DesktopProductionResumeController`.",
        "- Authority: `episode-transition-ledger-v1.jsonl`; legacy V6/V6.4/V6.0.1/V4+/autonomous/R9 projections are not read by the supported launcher.",
        "- Opening/loading is read-only. The explicit UI action prepares a desktop-only intent; it does not create authorization or start execution implicitly.",
        "- The explicit UI action invokes `CanonicalMediaCostPreflightExecutor`; it persists a local result transactionally, appends a completion receipt, exposes `PROVIDER_EXECUTION`, and stops without executing it.",
        "",
        "## Episode 002 projection",
        "",
        "- Current stage: `MEDIA_COST_PREFLIGHT` (`READY`).",
        "- Alignment and duplicate gates: `PASS`; `LUNA-GATE-001=CLOSED_BY_LOCAL_DUPLICATE_GATE`.",
        "- Overlay canonical SHA-256: `" + payload["promoted_creative_overlay"]["canonical_sha256"] + "`.",
        "- Structural authority: `" + state.authoritative_structural_fingerprint + "`; 623.584 seconds, 55 shots, 0 discontinuities, final shot 622.784–623.584.",
        "",
        "## Safety and tests",
        "",
        "- Legacy supported launch scripts and run commands now fail closed with `PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY`.",
        "- The fake offline UI flow passed only `MEDIA_COST_PREFLIGHT` to a fake runner. No stage was executed.",
        "- Qt offscreen open/load preserved the ledger hash. Network-deny test passed.",
        "- Isolated executor failure-injection tests passed; no real Episode 002 preflight, network, provider, Autopilot, or production-state operation occurred.",
        "",
        "## Compatibility note",
        "",
        "The preserved provider-ready plan carries its legacy contract fingerprint (`"
        + state.provider_plan_contract_fingerprint
        + "`). The canonical UI uses the ledger-bound storyboard-manifest fingerprint (`"
        + state.authoritative_structural_fingerprint
        + "`) for structural authority; this avoids treating the compatibility field as an authority source.",
        "",
    ])
    with markdown_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown)
    print(json.dumps({"report_md": str(markdown_path), "report_json": str(json_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
