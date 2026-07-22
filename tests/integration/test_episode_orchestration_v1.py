from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.episode_orchestration_v1.runtime import (
    EpisodeOrchestrator,
    StageExecutionResult,
    StageSpec,
    build_default_stage_registry,
    build_dependency_graph,
    default_episode_definition,
    validate_episode_definition,
    validate_generated_video_allocation,
)


def _definition(tmp_path: Path, **changes: object) -> dict[str, object]:
    source = tmp_path / "source-package.json"
    source.write_text('{"schema_version":"fixture"}', encoding="utf-8")
    external_policy = {"default_allowed": False, "explicit_live_confirmation_required": True, "provider_configured": True, "credential_present": True, "disclosure_permitted": True, "request_limit_available": True, "quota_policy_valid": True, "stage_permissions": {"external": True}}
    external_policy.update(changes.pop("external_provider_policy", {}))
    return default_episode_definition(
        episode_id="episode-fixture",
        series_id="series-fixture",
        title="Fixture",
        working_title="Fixture",
        subject="subject",
        central_question="question",
        source_package={"path": str(source), "approval_status": "APPROVED"},
        external_provider_policy=external_policy,
        created_at="2026-07-22T00:00:00Z",
        updated_at="2026-07-22T00:00:00Z",
        **changes,
    )


def _registry() -> tuple[StageSpec, ...]:
    return (
        StageSpec("prepare", "Prepare", "1", 10, "fake"),
        StageSpec("review", "Review", "1", 20, "human_approval_gate", dependencies=("prepare",), human_approval_required=True, current_implementation_status="ORCHESTRATOR_GATE"),
        StageSpec("external", "External", "1", 30, "fake", dependencies=("review",), external_provider_required=True),
        StageSpec("finish", "Finish", "1", 40, "fake", dependencies=("external",)),
    )


def _fake_runner(calls: list[str]):
    def run(context, stage: StageSpec, run_id: str) -> StageExecutionResult:  # type: ignore[no-untyped-def]
        calls.append(stage.stage_id)
        artifact = {
            "artifact_id": f"{stage.stage_id}:{run_id}",
            "artifact_type": "fixture",
            "stage_id": stage.stage_id,
            "path": f"working/{stage.stage_id}.json",
            "schema_version": "fixture-v1",
            "fingerprint": f"fingerprint-{stage.stage_id}",
            "created_at": "2026-07-22T00:00:00Z",
            "status": "COMPLETED",
            "approval_status": "NOT_REQUESTED",
            "source_artifact_ids": [],
            "supersedes": None,
            "runtime_only": True,
            "git_trackable": False,
        }
        return StageExecutionResult(stage.stage_id, run_id, "COMPLETED", outputs=(artifact,), output_fingerprint=artifact["fingerprint"])
    return run


def _orchestrator(tmp_path: Path, calls: list[str]) -> EpisodeOrchestrator:
    return EpisodeOrchestrator(tmp_path, _definition(tmp_path), output_root=tmp_path / "working" / "episode-orchestrator-v1", registry=_registry(), runners={"prepare": _fake_runner(calls), "external": _fake_runner(calls), "finish": _fake_runner(calls)})


def test_episode_definition_accepts_standard_22_minute_profile_and_rejects_policy_errors(tmp_path: Path) -> None:
    assert validate_episode_definition(_definition(tmp_path)) == []
    assert "EPISODE_DURATION_POLICY_INVALID" in validate_episode_definition(_definition(tmp_path, minimum_duration_minutes=23))
    assert "POLICY_VALIDATION_ERROR:MAXIMUM_FINAL_GENERATED_VIDEO_SECONDS" in validate_episode_definition(_definition(tmp_path, generated_video_policy={"maximum_final_generated_video_seconds": 301}))
    assert "POLICY_VALIDATION_ERROR:VIDEO_MODEL_NOT_ALLOWED" in validate_episode_definition(_definition(tmp_path, generated_video_policy={"maximum_final_generated_video_seconds": 300, "allowed_models": ["UNSUPPORTED"], "allocation_owner": "STORYBOARD_WRITER", "enforcement_owner": "VIDEO_POLICY_GUARD", "final_approval_required": True}))
    assert any(item.startswith("REQUESTED_OUTPUT_UNKNOWN") for item in validate_episode_definition(_definition(tmp_path, requested_outputs=["unknown_output"])))
    assert validate_generated_video_allocation(300, _definition(tmp_path)["generated_video_policy"]) == []  # type: ignore[arg-type]
    assert validate_generated_video_allocation(301, _definition(tmp_path)["generated_video_policy"]) == ["POLICY_VALIDATION_ERROR:GENERATED_VIDEO_SECONDS_EXCEEDED"]  # type: ignore[arg-type]
    assert validate_generated_video_allocation(1, _definition(tmp_path)["generated_video_policy"], model="UNSUPPORTED") == ["POLICY_VALIDATION_ERROR:VIDEO_MODEL_NOT_ALLOWED"]  # type: ignore[arg-type]


def test_default_registry_never_marks_a_disconnected_component_available() -> None:
    registry = build_default_stage_registry()
    statuses = {stage.stage_id: stage.current_implementation_status for stage in registry}
    assert statuses["source_package"] == "CONTRACT_ONLY"
    assert statuses["evidence_knowledge"] == "DISCONNECTED"
    assert statuses["narrative_script"] == "DISCONNECTED"
    assert statuses["production_tts"] == "DISCONNECTED"
    assert statuses["subtitles"] == "DISCONNECTED"
    assert statuses["storyboard"] == "DISCONNECTED"
    assert statuses["render"] == "DISCONNECTED"
    assert statuses["visual_provider"] == "IMPLEMENTATION_COMPLETED_LIVE_VALIDATION_DEFERRED"
    with pytest.raises(ValueError, match="AVAILABLE_STAGE_RUNNER_REQUIRED"):
        EpisodeOrchestrator(Path("."), default_episode_definition(created_at="x", updated_at="x"), registry=(StageSpec("available", "Available", "1", 1, "missing"),))


def test_dependency_graph_detects_cycles_and_exposes_dependents() -> None:
    graph = build_dependency_graph(_registry())
    assert graph["dependents"]["prepare"] == ["review"]
    with pytest.raises(ValueError, match="STAGE_DEPENDENCY_CYCLE"):
        build_dependency_graph((StageSpec("a", "A", "1", 1, "fake", dependencies=("b",)), StageSpec("b", "B", "1", 2, "fake", dependencies=("a",))))


def test_plan_is_dry_and_run_next_executes_exactly_one_stage(tmp_path: Path) -> None:
    calls: list[str] = []
    orchestrator = _orchestrator(tmp_path, calls)
    planned = orchestrator.execute(mode="plan")
    assert planned["plan"]["stages_ready"] == ["prepare"] and calls == []
    result = orchestrator.execute(mode="run-next")
    assert calls == ["prepare"]
    assert result["manifest"]["stage_states"]["prepare"]["status"] == "COMPLETED"
    assert result["manifest"]["stage_states"]["review"]["status"] == "BLOCKED_BY_HUMAN_APPROVAL"


def test_run_through_stops_at_human_approval_and_resume_skips_completed(tmp_path: Path) -> None:
    calls: list[str] = []
    orchestrator = _orchestrator(tmp_path, calls)
    first = orchestrator.execute(mode="run-through")
    assert calls == ["prepare"] and first["status"] == "WAITING_FOR_HUMAN_APPROVAL"
    orchestrator.record_approval(stage_id="review", decision="APPROVED", reviewer="reviewer")
    resumed = orchestrator.execute(mode="resume", allow_external=True, confirm_live=True)
    assert calls == ["prepare", "external"]
    assert resumed["manifest"]["stage_states"]["prepare"]["cache_status"] == "HIT"


def test_external_stage_requires_explicit_confirmation_without_provider_call(tmp_path: Path) -> None:
    calls: list[str] = []
    orchestrator = _orchestrator(tmp_path, calls)
    orchestrator.execute(mode="run-next")
    orchestrator.record_approval(stage_id="review", decision="APPROVED", reviewer="reviewer")
    state = orchestrator.execute(mode="status")["manifest"]["stage_states"]["external"]
    assert state["status"] == "BLOCKED_BY_EXTERNAL_PROVIDER"
    assert state["blocker"]["code"] == "EXTERNAL_CONFIRMATION_REQUIRED"
    assert calls == ["prepare"]


def test_external_preflight_blocks_without_leaking_credentials(tmp_path: Path) -> None:
    calls: list[str] = []
    definition = _definition(tmp_path, external_provider_policy={"default_allowed": False, "explicit_live_confirmation_required": True, "provider_configured": True, "credential_present": False, "disclosure_permitted": False, "request_limit_available": False, "quota_policy_valid": False, "stage_permissions": {"external": True}})
    registry = (StageSpec("external", "External", "1", 1, "fake", external_provider_required=True),)
    orchestrator = EpisodeOrchestrator(tmp_path, definition, output_root=tmp_path / "orchestrator", registry=registry, runners={"external": _fake_runner(calls)})
    state = orchestrator.execute(mode="status", allow_external=True, confirm_live=True)["manifest"]["stage_states"]["external"]
    assert state["status"] == "BLOCKED_BY_EXTERNAL_PROVIDER"
    assert state["blocker"]["code"] == "EXTERNAL_PROVIDER_POLICY_INCOMPLETE"
    assert "CREDENTIAL_PRESENT_REQUIRED" in state["blocker"]["requirements"]
    assert "secret" not in json.dumps(state).lower() and calls == []


def test_visual_quota_block_is_resumable_and_preserves_prior_work(tmp_path: Path) -> None:
    report = tmp_path / "working" / "visual-provider-v1" / "production-visual-quota-report-v1.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"provider_error_code": "QUOTA_EXHAUSTED", "quota_status": "QUOTA_EXHAUSTED"}), encoding="utf-8")
    visual = StageSpec("visual_provider", "Visual", "1", 1, "visual_provider_v1", external_provider_required=True, current_implementation_status="IMPLEMENTATION_COMPLETED_LIVE_VALIDATION_DEFERRED")
    orchestrator = EpisodeOrchestrator(tmp_path, _definition(tmp_path), output_root=tmp_path / "orchestrator", registry=(visual,))
    state = orchestrator.execute(mode="status")["manifest"]["stage_states"]["visual_provider"]
    assert state["status"] == "BLOCKED_BY_EXTERNAL_PROVIDER"
    assert state["blocker"]["code"] == "QUOTA_EXHAUSTED"
    assert state["blocker"]["prior_work_preserved"] is True


def test_invalidation_marks_downstream_stale_without_deleting_artifacts(tmp_path: Path) -> None:
    calls: list[str] = []
    registry = (StageSpec("one", "One", "1", 1, "fake"), StageSpec("two", "Two", "1", 2, "fake", dependencies=("one",)))
    orchestrator = EpisodeOrchestrator(tmp_path, _definition(tmp_path), output_root=tmp_path / "orchestrator", registry=registry, runners={"one": _fake_runner(calls), "two": _fake_runner(calls)})
    orchestrator.execute(mode="run-through")
    before = orchestrator.execute(mode="status")["manifest"]
    assert before["stage_states"]["two"]["status"] == "COMPLETED"
    invalidated = orchestrator.execute(mode="invalidate-stage", stage_id="one")["manifest"]
    assert invalidated["stage_states"]["one"]["status"] == "READY"
    assert invalidated["stage_states"]["two"]["status"] == "BLOCKED_BY_DEPENDENCY"
    assert invalidated["artifact_index"]


def test_changed_input_invalidates_completed_downstream_stages(tmp_path: Path) -> None:
    calls: list[str] = []
    registry = (StageSpec("narrative_script", "Narrative", "1", 1, "fake"), StageSpec("two", "Two", "1", 2, "fake", dependencies=("narrative_script",)))
    orchestrator = EpisodeOrchestrator(tmp_path, _definition(tmp_path), output_root=tmp_path / "orchestrator", registry=registry, runners={"narrative_script": _fake_runner(calls), "two": _fake_runner(calls)})
    orchestrator.execute(mode="run-through")
    orchestrator.definition["subject"] = "changed subject"
    refreshed = orchestrator.execute(mode="status")["manifest"]
    assert refreshed["stage_states"]["narrative_script"]["status"] == "READY"
    assert refreshed["stage_states"]["two"]["status"] == "BLOCKED_BY_DEPENDENCY"


def test_permanent_failure_blocks_dependents_and_preserves_prior_outputs(tmp_path: Path) -> None:
    artifact = {"artifact_id": "preserved", "artifact_type": "fixture", "stage_id": "one", "path": "working/preserved.json", "schema_version": "fixture-v1", "fingerprint": "old", "created_at": "2026-07-22T00:00:00Z", "status": "COMPLETED", "approval_status": "NOT_REQUESTED", "source_artifact_ids": [], "supersedes": None, "runtime_only": True, "git_trackable": False}
    def failing(context, stage: StageSpec, run_id: str) -> StageExecutionResult:  # type: ignore[no-untyped-def]
        return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "OUTPUT_INVALID"},), blocker={"code": "OUTPUT_INVALID"})
    registry = (StageSpec("one", "One", "1", 1, "failing"), StageSpec("two", "Two", "1", 2, "fake", dependencies=("one",)))
    orchestrator = EpisodeOrchestrator(tmp_path, _definition(tmp_path), output_root=tmp_path / "orchestrator", registry=registry, runners={"one": failing, "two": _fake_runner([])})
    manifest = orchestrator._load_or_create_manifest()
    manifest["stage_states"]["one"].update({"status": "READY", "outputs": [artifact], "output_fingerprint": "old"})
    orchestrator._persist(manifest)
    result = orchestrator.execute(mode="run-next")["manifest"]
    assert result["stage_states"]["one"]["status"] == "PERMANENT_FAILURE"
    assert result["stage_states"]["one"]["outputs"] == [artifact]
    assert result["stage_states"]["two"]["status"] == "BLOCKED_BY_DEPENDENCY"


def test_artifact_duplicate_ids_are_rejected_and_runtime_artifacts_are_not_git_trackable(tmp_path: Path) -> None:
    calls: list[str] = []
    orchestrator = _orchestrator(tmp_path, calls)
    manifest = orchestrator._load_or_create_manifest()
    artifact = {"artifact_id": "a", "artifact_type": "fixture", "stage_id": "prepare", "path": "working/a.json", "schema_version": "fixture-v1", "fingerprint": "one", "created_at": "2026-07-22T00:00:00Z", "status": "COMPLETED", "approval_status": "NOT_REQUESTED", "source_artifact_ids": [], "supersedes": None, "runtime_only": True, "git_trackable": False}
    orchestrator._index_artifacts(manifest, (artifact,))
    assert manifest["artifact_index"][0]["git_trackable"] is False
    with pytest.raises(ValueError, match="ARTIFACT_ID_DUPLICATE"):
        orchestrator._index_artifacts(manifest, ({**artifact, "fingerprint": "two"},))
    with pytest.raises(ValueError, match="ARTIFACT_PATH_OUTSIDE_PROJECT"):
        orchestrator._index_artifacts(manifest, ({**artifact, "artifact_id": "outside", "path": "C:/outside-project.json"},))


def test_approval_requires_reviewer_and_becomes_stale_after_upstream_change(tmp_path: Path) -> None:
    calls: list[str] = []
    orchestrator = _orchestrator(tmp_path, calls)
    orchestrator.execute(mode="run-next")
    with pytest.raises(ValueError, match="APPROVAL_REVIEWER_REQUIRED"):
        orchestrator.record_approval(stage_id="review", decision="APPROVED")
    orchestrator.record_approval(stage_id="review", decision="APPROVED", reviewer="reviewer")
    assert orchestrator.execute(mode="status")["manifest"]["stage_states"]["review"]["status"] == "COMPLETED"
    stored = orchestrator._load_or_create_manifest()
    orchestrator._mark_stale(stored, "prepare", "FIXTURE_ARTIFACT_CHANGED")
    orchestrator._persist(stored)
    manifest = orchestrator.execute(mode="status")["manifest"]
    assert manifest["approvals"][-1]["status"] == "STALE"
    assert manifest["stage_states"]["review"]["status"] == "BLOCKED_BY_DEPENDENCY"


def test_external_stage_needs_both_confirmation_flags_and_stage_permission(tmp_path: Path) -> None:
    calls: list[str] = []
    orchestrator = _orchestrator(tmp_path, calls)
    orchestrator.execute(mode="run-next")
    orchestrator.record_approval(stage_id="review", decision="APPROVED", reviewer="reviewer")
    assert orchestrator.execute(mode="status", allow_external=True)["manifest"]["stage_states"]["external"]["blocker"]["code"] == "EXTERNAL_CONFIRMATION_REQUIRED"
    assert orchestrator.execute(mode="status", confirm_live=True)["manifest"]["stage_states"]["external"]["blocker"]["code"] == "EXTERNAL_CONFIRMATION_REQUIRED"
    orchestrator.definition["external_provider_policy"]["stage_permissions"] = {}  # type: ignore[index]
    state = orchestrator.execute(mode="status", allow_external=True, confirm_live=True)["manifest"]["stage_states"]["external"]
    assert "STAGE_PERMISSION_REQUIRED:external" in state["blocker"]["requirements"]
    assert calls == ["prepare"]


def test_run_stage_rejects_unknown_stage_and_status_uses_first_required_blocker(tmp_path: Path) -> None:
    calls: list[str] = []
    orchestrator = _orchestrator(tmp_path, calls)
    with pytest.raises(ValueError, match="ORCHESTRATOR_STAGE_UNKNOWN"):
        orchestrator.execute(mode="run-stage", stage_id="unknown")
    manifest = orchestrator.execute(mode="status")["manifest"]
    manifest["stage_states"]["prepare"]["status"] = "BLOCKED_BY_HUMAN_APPROVAL"
    manifest["stage_states"]["external"]["status"] = "BLOCKED_BY_EXTERNAL_PROVIDER"
    orchestrator._derive_episode_status(manifest)
    assert manifest["status"] == "WAITING_FOR_HUMAN_APPROVAL"


def test_episode_readiness_states_are_derived_only_from_stage_states(tmp_path: Path) -> None:
    registry = (
        StageSpec("assets", "Assets", "1", 1, "fake"),
        StageSpec("render", "Render", "1", 2, "fake", dependencies=("assets",)),
        StageSpec("final_render_approval", "Render approval", "1", 3, "gate", dependencies=("render",), human_approval_required=True, current_implementation_status="ORCHESTRATOR_GATE"),
        StageSpec("publication", "Publication", "1", 4, "gate", dependencies=("final_render_approval",), human_approval_required=True, current_implementation_status="ORCHESTRATOR_GATE"),
    )
    orchestrator = EpisodeOrchestrator(tmp_path, _definition(tmp_path), output_root=tmp_path / "orchestrator", registry=registry, runners={"assets": _fake_runner([]), "render": _fake_runner([])})
    manifest = orchestrator._load_or_create_manifest()
    manifest["stage_states"]["assets"]["status"] = "COMPLETED"
    manifest["stage_states"]["render"]["status"] = "READY"
    orchestrator._derive_episode_status(manifest)
    assert manifest["status"] == "READY_FOR_RENDER"
    manifest["stage_states"]["render"]["status"] = "COMPLETED"
    manifest["stage_states"]["final_render_approval"]["status"] = "COMPLETED"
    manifest["stage_states"]["publication"]["status"] = "BLOCKED_BY_HUMAN_APPROVAL"
    orchestrator._derive_episode_status(manifest)
    assert manifest["status"] == "READY_FOR_PUBLICATION"
    manifest["stage_states"]["publication"]["status"] = "COMPLETED"
    orchestrator._derive_episode_status(manifest)
    assert manifest["status"] == "COMPLETED"
    manifest["stage_states"]["assets"]["status"] = "PERMANENT_FAILURE"
    orchestrator._derive_episode_status(manifest)
    assert manifest["status"] == "FAILED"


def test_cli_parser_is_local_and_does_not_enable_external_by_default(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.fast_track.run_episode_orchestrator_v1 import _natural_message, build_parser, exit_code_for_result, main
    args = build_parser().parse_args(["--project-root", "project", "--episode-definition", "episode.json", "--mode", "plan", "--json"])
    assert args.allow_external is False and args.confirm_live is False and args.json is True
    assert exit_code_for_result({"status": "WAITING_FOR_EXTERNAL_PROVIDER"}) == 0
    assert exit_code_for_result({"status": "FAILED"}) != 0
    assert _natural_message({"status": "WAITING_FOR_EXTERNAL_PROVIDER"}) == "BLOCKED_OR_WAITING: WAITING_FOR_EXTERNAL_PROVIDER"
    assert "FAIL: FAIL" not in _natural_message({"status": "FAILED"})
    definition_path = tmp_path / "episode-definition.json"
    definition_path.write_text(json.dumps(_definition(tmp_path)), encoding="utf-8")
    assert main(["--project-root", str(tmp_path), "--episode-definition", str(definition_path), "--mode", "plan", "--dry-run", "--output", str(tmp_path / "orchestrator")]) == 0
    assert "FAIL: FAIL" not in capsys.readouterr().out
    assert main(["--project-root", str(tmp_path), "--episode-definition", str(definition_path), "--mode", "status", "--output", str(tmp_path / "orchestrator"), "--json"]) == 0
    assert isinstance(json.loads(capsys.readouterr().out), dict)


def test_episode_definition_example_is_schema_valid() -> None:
    path = Path(__file__).resolve().parents[2] / "docs" / "execution" / "examples" / "episode-definition-v1.example.json"
    assert validate_episode_definition(json.loads(path.read_text(encoding="utf-8"))) == []
