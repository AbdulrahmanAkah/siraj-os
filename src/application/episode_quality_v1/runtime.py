"""Aggregate existing episode checks into one deterministic QA decision."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Any

from src.application.episode_orchestration_v1.runtime import EpisodeContext, StageExecutionResult, StageSpec

QA_POLICY_SCHEMA = "siraj-episode-qa-policy-v1"
QA_REPORT_SCHEMA = "siraj-episode-qa-report-v1"
QA_READINESS_SCHEMA = "siraj-episode-qa-readiness-v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fp(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def default_qa_policy() -> dict[str, Any]:
    value = {"schema_version": QA_POLICY_SCHEMA, "required_stage_ids": ["evidence_approval", "script_approval", "storyboard_approval", "master_visual_approval", "video_approval", "final_render_approval"], "allow_pass_with_warnings": True, "waivers_require_reviewer": True}
    value["policy_fingerprint"] = _fp(value)
    return value


class EpisodeQAGate:
    """Does not redo validators; it makes their known findings auditable."""
    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = policy or default_qa_policy()

    def evaluate(self, context: EpisodeContext) -> tuple[dict[str, Any], dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        states = context.manifest["stage_states"]
        for stage_id, state in states.items():
            status = str(state.get("status"))
            if status == "STALE":
                findings.append({"finding_id": f"stale:{stage_id}", "category": "STALE_ARTIFACT", "severity": "BLOCKER", "stage_id": stage_id, "artifact_ids": [item.get("artifact_id") for item in state.get("outputs", [])], "policy_rule": "REQUIRED_ARTIFACT_NOT_STALE", "safe_message": "A required upstream artifact is stale.", "evidence": [], "human_review_required": False, "resolution_status": "OPEN", "waiver": None, "created_at": _now()})
            for error in state.get("errors", []):
                code = str(error.get("code", "")) if isinstance(error, dict) else str(error)
                if code in {"UNSUPPORTED_FACTUAL_ASSERTION", "SCRIPT_UNSUPPORTED_ASSERTION"}:
                    findings.append({"finding_id": f"script:{stage_id}:{code}", "category": "SCRIPT_EVIDENCE", "severity": "BLOCKER", "stage_id": stage_id, "artifact_ids": [], "policy_rule": "NO_UNSUPPORTED_FACTUAL_ASSERTION", "safe_message": "A script assertion is unsupported.", "evidence": [code], "human_review_required": True, "resolution_status": "OPEN", "waiver": None, "created_at": _now()})
        for stage_id in self.policy.get("required_stage_ids", []):
            if states.get(stage_id, {}).get("status") not in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}:
                findings.append({"finding_id": f"approval:{stage_id}", "category": "APPROVAL", "severity": "BLOCKER", "stage_id": stage_id, "artifact_ids": [], "policy_rule": "REQUIRED_APPROVAL", "safe_message": "A required approval is missing or stale.", "evidence": [], "human_review_required": True, "resolution_status": "OPEN", "waiver": None, "created_at": _now()})
        if states.get("render", {}).get("status") not in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}:
            findings.append({"finding_id": "render:missing", "category": "RENDER", "severity": "BLOCKER", "stage_id": "render", "artifact_ids": [], "policy_rule": "APPROVED_FINAL_RENDER_REQUIRED", "safe_message": "A valid final render is required.", "evidence": [], "human_review_required": True, "resolution_status": "OPEN", "waiver": None, "created_at": _now()})
        blockers = [item for item in findings if item["severity"] == "BLOCKER"]
        warnings = [item for item in findings if item["severity"] == "WARNING"]
        status = "FAIL" if blockers else ("PASS_WITH_WARNINGS" if warnings else "PASS")
        report = {"schema_version": QA_REPORT_SCHEMA, "episode_id": context.definition["episode_id"], "status": status, "policy": self.policy, "findings": findings, "artifact_index_fingerprint": _fp(context.manifest.get("artifact_index", [])), "stage_state_fingerprint": _fp(states), "generated_at": _now(), "input_fingerprint": _fp({"policy": self.policy.get("policy_fingerprint"), "artifacts": context.manifest.get("artifact_index", []), "states": states}), "output_fingerprint": ""}
        report["output_fingerprint"] = _fp({key: value for key, value in report.items() if key not in {"output_fingerprint", "generated_at"}})
        readiness = {"schema_version": QA_READINESS_SCHEMA, "episode_id": context.definition["episode_id"], "qa_status": status, "ready_for_publication_package": status in {"PASS", "PASS_WITH_WARNINGS"}, "blockers": [item["finding_id"] for item in blockers], "warnings": [item["finding_id"] for item in warnings], "qa_report_fingerprint": report["output_fingerprint"], "policy_fingerprint": self.policy.get("policy_fingerprint"), "output_fingerprint": ""}
        readiness["output_fingerprint"] = _fp({key: value for key, value in readiness.items() if key != "output_fingerprint"})
        return report, readiness

    def run(self, context: EpisodeContext, stage: StageSpec, run_id: str) -> StageExecutionResult:
        report, readiness = self.evaluate(context)
        directory = context.output_root / "episode-qa-v1"
        report_path, readiness_path = directory / "episode-qa-report-v1.json", directory / "episode-qa-readiness-v1.json"
        _write(report_path, report); _write(readiness_path, readiness)
        artifact = lambda artifact_type, path, fingerprint: {"artifact_id": f"{artifact_type}:{fingerprint[:16]}", "artifact_type": artifact_type, "stage_id": stage.stage_id, "path": path.relative_to(context.project_root).as_posix(), "schema_version": "1", "fingerprint": fingerprint, "created_at": _now(), "status": report["status"], "approval_status": "NOT_REQUESTED", "source_artifact_ids": [item.get("artifact_id") for item in context.manifest.get("artifact_index", [])], "supersedes": None, "runtime_only": True, "git_trackable": False}
        outputs = (artifact("episode-qa-report", report_path, report["output_fingerprint"]), artifact("episode-qa-readiness", readiness_path, readiness["output_fingerprint"]))
        return StageExecutionResult(stage.stage_id, run_id, "COMPLETED" if report["status"] in {"PASS", "PASS_WITH_WARNINGS"} else "PERMANENT_FAILURE", outputs=outputs if report["status"] != "FAIL" else (), warnings=tuple(item["finding_id"] for item in report["findings"] if item["severity"] == "WARNING"), errors=tuple({"code": item["finding_id"]} for item in report["findings"] if item["severity"] == "BLOCKER"), output_fingerprint=report["output_fingerprint"], next_action="Build the publication package after QA passes." if report["status"] != "FAIL" else "Resolve QA blockers before publication.")
