"""Build public/internal publication manifests without uploading anything."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from src.application.episode_orchestration_v1.runtime import EpisodeContext, StageExecutionResult, StageSpec

PUBLICATION_POLICY_SCHEMA = "siraj-publication-policy-v1"
PUBLICATION_PACKAGE_SCHEMA = "siraj-episode-publication-package-v1"
PUBLICATION_READINESS_SCHEMA = "siraj-episode-publication-readiness-v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _fp(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name); handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


class PublicationPackageBuilder:
    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = policy or {"schema_version": PUBLICATION_POLICY_SCHEMA, "profiles": ["GENERIC_VIDEO", "YOUTUBE", "WEBSITE_ARCHIVE"], "allow_pass_with_warnings": True}

    def run(self, context: EpisodeContext, stage: StageSpec, run_id: str) -> StageExecutionResult:
        qa_outputs = context.manifest["stage_states"].get("qa_gate", {}).get("outputs", [])
        if not qa_outputs:
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_DEPENDENCY", blocker={"code": "BLOCKED_BY_QA"})
        report_path = next((context.project_root / item["path"] for item in qa_outputs if item.get("artifact_type") == "episode-qa-report"), None)
        if report_path is None or not report_path.is_file():
            return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "QA_REPORT_MISSING"},))
        qa = json.loads(report_path.read_text(encoding="utf-8"))
        if qa.get("status") not in {"PASS", "PASS_WITH_WARNINGS"}:
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_DEPENDENCY", blocker={"code": "BLOCKED_BY_QA"})
        render = [item for item in context.manifest["stage_states"].get("render", {}).get("outputs", []) if item.get("artifact_type") == "rendered-video"]
        if not render:
            return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "FINAL_RENDER_MISSING"},))
        metadata = context.definition.get("publication_metadata", {})
        required = ("title", "language")
        missing = [key for key in required if not isinstance(metadata.get(key, context.definition.get(key)), str) or not str(metadata.get(key, context.definition.get(key))).strip()]
        if missing:
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_DEPENDENCY", blocker={"code": "BLOCKED_BY_MISSING_METADATA", "fields": missing})
        root = context.output_root / "publication" / context.definition["episode_id"]
        public, internal = root / "public", root / "internal"
        public.mkdir(parents=True, exist_ok=True); internal.mkdir(parents=True, exist_ok=True)
        exported: list[dict[str, str]] = []
        selected = render + [item for item in context.manifest.get("artifact_index", []) if item.get("artifact_type") in {"srt", "vtt", "ass"}]
        for artifact in selected:
            source = context.project_root / str(artifact["path"])
            if not source.is_file():
                return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "PUBLICATION_ASSET_MISSING"},))
            target = public / source.name
            shutil.copyfile(source, target)
            exported.append({"artifact_id": artifact["artifact_id"], "filename": target.name, "sha256": sha256(target.read_bytes()).hexdigest()})
        public_metadata = {"title": metadata.get("title", context.definition["title"]), "short_title": metadata.get("short_title", context.definition["working_title"]), "language": metadata.get("language", context.definition["language"]), "central_question": context.definition.get("central_question", ""), "description": metadata.get("description", ""), "credits": metadata.get("credits", []), "source_list": sorted({source for item in context.manifest.get("artifact_index", []) for source in item.get("source_artifact_ids", [])}), "historical_dispute_disclaimer": metadata.get("historical_dispute_disclaimer", "Human review required for disputed historical material."), "ai_generated_media_disclosure": metadata.get("ai_generated_media_disclosure", "Media provenance is recorded in the internal archive."), "profiles": self.policy["profiles"]}
        checksums = {item["filename"]: item["sha256"] for item in exported}
        package = {"schema_version": PUBLICATION_PACKAGE_SCHEMA, "episode_id": context.definition["episode_id"], "status": "BUILT", "public_metadata": public_metadata, "assets": exported, "checksums": checksums, "qa_report_fingerprint": qa.get("output_fingerprint"), "public_path": "public", "internal_path": "internal", "created_at": _now(), "output_fingerprint": ""}
        package["output_fingerprint"] = _fp({key: value for key, value in package.items() if key not in {"output_fingerprint", "created_at"}})
        readiness = {"schema_version": PUBLICATION_READINESS_SCHEMA, "episode_id": context.definition["episode_id"], "status": "HUMAN_REVIEW_REQUIRED", "package_fingerprint": package["output_fingerprint"], "upload_performed": False, "blockers": [], "warnings": []}
        _write(public / "episode-publication-metadata-v1.json", public_metadata); _write(internal / "episode-publication-package-v1.json", package); _write(internal / "publication-checksums-v1.json", {"checksums": checksums}); _write(internal / "episode-publication-readiness-v1.json", readiness)
        def artifact(kind: str, path: Path, fingerprint: str) -> dict[str, Any]:
            return {"artifact_id": f"{kind}:{fingerprint[:16]}", "artifact_type": kind, "stage_id": stage.stage_id, "path": path.relative_to(context.project_root).as_posix(), "schema_version": "1", "fingerprint": fingerprint, "created_at": _now(), "status": "COMPLETED", "approval_status": "HUMAN_REVIEW_REQUIRED", "source_artifact_ids": [item["artifact_id"] for item in selected], "supersedes": None, "runtime_only": True, "git_trackable": False}
        outputs = (artifact("episode-publication-package", internal / "episode-publication-package-v1.json", package["output_fingerprint"]), artifact("publication-checksums", internal / "publication-checksums-v1.json", _fp(checksums)))
        return StageExecutionResult(stage.stage_id, run_id, "COMPLETED", outputs=outputs, output_fingerprint=package["output_fingerprint"], next_action="Record publication approval; building files never uploads them.")
