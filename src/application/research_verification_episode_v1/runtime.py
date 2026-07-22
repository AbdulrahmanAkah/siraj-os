"""Canonical offline contracts for source research, verification and approval.

The adapter validates recorded provenance only.  It never decides historical
truth and never calls a model; an extractor is injected by the composition.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Any, Callable, Protocol

from src.application.evidence_to_script_episode_v1.runtime import EVIDENCE_PACKAGE_SCHEMA
from src.application.episode_orchestration_v1.runtime import EpisodeContext, StageExecutionResult, StageSpec

SOURCE_PACKAGE_SCHEMA = "siraj-episode-source-package-v1"
RESEARCH_DOSSIER_SCHEMA = "siraj-episode-research-dossier-v1"
RESEARCH_VERIFICATION_SCHEMA = "siraj-episode-research-verification-v1"
APPROVED_EVIDENCE_SCHEMA = EVIDENCE_PACKAGE_SCHEMA


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fp(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _without(value: dict[str, Any], *names: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in names}


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("CONTRACT_NOT_OBJECT")
    return value


def _inside(root: Path, value: str) -> Path:
    candidate = Path(value)
    candidate = candidate if candidate.is_absolute() else root / candidate
    candidate = candidate.resolve(strict=False)
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("SOURCE_PATH_OUTSIDE_PROJECT") from error
    return candidate


def validate_source_package(package: dict[str, Any], *, project_root: Path, episode_id: str) -> list[str]:
    required = {"schema_version", "episode_id", "source_package_id", "title", "central_question", "historical_scope", "geographical_scope", "language", "source_items", "inclusion_policy", "exclusion_policy", "religious_sensitivity", "research_questions", "created_at", "updated_at", "input_fingerprint"}
    errors = [f"SOURCE_PACKAGE_FIELD_MISSING:{key}" for key in sorted(required - set(package))]
    if package.get("schema_version") != SOURCE_PACKAGE_SCHEMA:
        errors.append("SOURCE_PACKAGE_SCHEMA_INVALID")
    if package.get("episode_id") != episode_id:
        errors.append("SOURCE_PACKAGE_EPISODE_ID_MISMATCH")
    items = package.get("source_items")
    if not isinstance(items, list) or not items:
        return sorted(set(errors + ["SOURCE_ITEMS_INVALID"]))
    ids: set[str] = set()
    required_item = {"source_id", "source_type", "title", "language", "path", "checksum", "access_status", "authority_class", "primary_or_secondary", "allowed_for_extraction", "allowed_for_quotation"}
    for item in items:
        if not isinstance(item, dict):
            errors.append("SOURCE_ITEM_INVALID")
            continue
        missing = required_item - set(item)
        if missing:
            errors.append(f"SOURCE_ITEM_FIELD_MISSING:{','.join(sorted(missing))}")
            continue
        source_id = item.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            errors.append("SOURCE_ID_INVALID")
            continue
        if source_id in ids:
            errors.append("SOURCE_ID_DUPLICATE")
        ids.add(source_id)
        if item.get("access_status") == "AVAILABLE":
            try:
                path = _inside(project_root, str(item.get("path", "")))
                if not path.is_file():
                    errors.append(f"SOURCE_PATH_MISSING:{source_id}")
                elif item.get("checksum") != sha256(path.read_bytes()).hexdigest():
                    errors.append(f"SOURCE_CHECKSUM_MISMATCH:{source_id}")
            except ValueError as error:
                errors.append(str(error))
    if package.get("input_fingerprint") != _fp(_without(package, "input_fingerprint")):
        errors.append("SOURCE_PACKAGE_FINGERPRINT_INVALID")
    return sorted(set(errors))


def verify_dossier(dossier: dict[str, Any], *, source_package: dict[str, Any]) -> dict[str, Any]:
    """Deterministic reference, locator, quote and independence checks only."""
    errors: list[str] = []
    warnings: list[str] = []
    sources = {str(item["source_id"]): item for item in source_package["source_items"] if isinstance(item, dict) and item.get("source_id")}
    passages = {str(item.get("passage_id")): item for item in dossier.get("extracted_passages", []) if isinstance(item, dict) and item.get("passage_id")}
    claims = dossier.get("candidate_claims", [])
    claim_ids: set[str] = set()
    relations = {str(item.get("source_id")): item for item in dossier.get("source_relationships", []) if isinstance(item, dict) and item.get("source_id")}
    for passage_id, passage in passages.items():
        if passage.get("source_id") not in sources or not isinstance(passage.get("exact_locator"), str) or not passage["exact_locator"].strip():
            errors.append(f"PASSAGE_LOCATOR_INVALID:{passage_id}")
        if passage.get("verbatim") is not True or not isinstance(passage.get("normalized_text"), str):
            errors.append(f"PASSAGE_VERBATIM_INVALID:{passage_id}")
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict) or not isinstance(claim.get("claim_id"), str):
            errors.append("CLAIM_INVALID")
            continue
        claim_id = claim["claim_id"]
        if claim_id in claim_ids:
            errors.append("CLAIM_ID_DUPLICATE")
        claim_ids.add(claim_id)
        evidence_refs, source_refs = claim.get("evidence_refs", []), claim.get("source_refs", [])
        if not evidence_refs or not source_refs or any(ref not in passages for ref in evidence_refs) or any(ref not in sources for ref in source_refs):
            errors.append(f"CLAIM_PROVENANCE_REQUIRED:{claim_id}")
        if claim.get("verification_status") == "CORROBORATED":
            independent = {ref for ref in source_refs if relations.get(ref, {}).get("independence_status", "INDEPENDENT") == "INDEPENDENT"}
            if len(independent) < 2:
                errors.append(f"CORROBORATION_INDEPENDENCE_REQUIRED:{claim_id}")
        if claim.get("dispute_status") in {"DISPUTED", "CONTRADICTED"} and not claim.get("uncertainty_language_requirement"):
            errors.append(f"DISPUTED_CLAIM_UNCERTAINTY_REQUIRED:{claim_id}")
    for relation in dossier.get("source_relationships", []):
        if not isinstance(relation, dict):
            continue
        parent = relation.get("parent_source_id")
        if parent and parent == relation.get("source_id"):
            errors.append("SOURCE_CIRCULARITY_DETECTED")
        if relation.get("source_relationship_type") in {"DERIVATIVE", "TRANSLATION", "SAME_WORK_EDITION", "COPIED_QUOTATION"}:
            warnings.append(f"SOURCE_NOT_INDEPENDENT:{relation.get('source_id')}")
    chronology = [item.get("claim_id") for item in dossier.get("chronology", []) if isinstance(item, dict)]
    if len(chronology) != len(set(chronology)) or any(item not in claim_ids for item in chronology):
        errors.append("CHRONOLOGY_REFERENCE_INVALID")
    status = "FAIL" if errors else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    return {"schema_version": RESEARCH_VERIFICATION_SCHEMA, "episode_id": dossier.get("episode_id"), "dossier_id": dossier.get("dossier_id"), "status": status, "source_checks": [], "provenance_checks": [], "claim_checks": [], "chronology_checks": [], "quotation_checks": [], "conflict_findings": list(dossier.get("disputed_points", [])), "source_independence_findings": sorted(set(warnings)), "coverage_findings": list(dossier.get("coverage_gaps", [])), "religious_sensitivity_findings": [], "unresolved_issues": list(dossier.get("unresolved_questions", [])), "warnings": sorted(set(warnings)), "errors": sorted(set(errors)), "human_review_required": True, "generated_at": _now(), "input_fingerprint": dossier.get("output_fingerprint", ""), "output_fingerprint": ""}


class ResearchExtractor(Protocol):
    def extract(self, *, source_package: dict[str, Any]) -> dict[str, Any]: ...


def _artifact(stage: str, artifact_type: str, path: Path, root: Path, fingerprint: str, *, sources: list[str] | None = None, approval: str = "PENDING") -> dict[str, Any]:
    return {"artifact_id": f"{artifact_type}:{fingerprint[:16]}", "artifact_type": artifact_type, "stage_id": stage, "path": path.relative_to(root).as_posix(), "schema_version": "1", "fingerprint": fingerprint, "created_at": _now(), "status": "COMPLETED", "approval_status": approval, "source_artifact_ids": sources or [], "supersedes": None, "runtime_only": True, "git_trackable": False}


class ResearchVerificationEpisodeAdapter:
    def __init__(self, project_root: Path, source_package_path: Path, extractor: ResearchExtractor | None = None) -> None:
        self.project_root, self.source_package_path, self.extractor = project_root.resolve(), source_package_path, extractor

    def run(self, context: EpisodeContext, stage: StageSpec, run_id: str) -> StageExecutionResult:
        try:
            package = _read(self.source_package_path)
        except (OSError, ValueError, json.JSONDecodeError):
            return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "SOURCE_PACKAGE_INVALID"},))
        errors = validate_source_package(package, project_root=self.project_root, episode_id=context.definition["episode_id"])
        if errors:
            return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=tuple({"code": item} for item in errors), blocker={"code": "SOURCE_PACKAGE_INVALID"})
        if self.extractor is None:
            return StageExecutionResult(stage.stage_id, run_id, "NOT_IMPLEMENTED", blocker={"code": "IMPLEMENTED_EXTRACTOR_DISCONNECTED"}, next_action="Inject a callable research extractor; no extraction is inferred from the contract.")
        extracted = self.extractor.extract(source_package=package)
        if not isinstance(extracted, dict):
            return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "EXTRACTOR_RESULT_INVALID"},))
        output = context.output_root / "research-verification-v1"
        source_artifacts = [{"artifact_id": item["source_id"], "path": str(item["path"]), "fingerprint": item["checksum"]} for item in package["source_items"]]
        dossier = {"schema_version": RESEARCH_DOSSIER_SCHEMA, "episode_id": package["episode_id"], "dossier_id": _fp({"source": package["input_fingerprint"], "extractor": extracted.get("extractor_version", "injected")})[:24], "source_package_fingerprint": package["input_fingerprint"], "source_inventory": package["source_items"], "extracted_passages": list(extracted.get("extracted_passages", [])), "candidate_claims": list(extracted.get("claims", [])), "events": list(extracted.get("events", [])), "entities": list(extracted.get("entities", [])), "locations": list(extracted.get("locations", [])), "chronology": list(extracted.get("chronology", [])), "quotations": list(extracted.get("quotations", [])), "disputed_points": list(extracted.get("disputed_points", [])), "source_relationships": list(extracted.get("source_relationships", [])), "unresolved_questions": list(extracted.get("unresolved_questions", [])), "coverage_gaps": list(extracted.get("coverage_gaps", [])), "extraction_warnings": list(extracted.get("warnings", [])), "provenance_graph": {"source_ids": [item["source_id"] for item in package["source_items"]]}, "input_fingerprint": package["input_fingerprint"], "output_fingerprint": ""}
        dossier["output_fingerprint"] = _fp(_without(dossier, "output_fingerprint"))
        report = verify_dossier(dossier, source_package=package)
        report["output_fingerprint"] = _fp(_without(report, "output_fingerprint", "generated_at"))
        candidate = {"schema_version": APPROVED_EVIDENCE_SCHEMA, "episode_id": package["episode_id"], "source_package_id": package["source_package_id"], "evidence_package_id": f"candidate-{dossier['dossier_id']}", "evidence_status": "HUMAN_REVIEW_REQUIRED", "approved_at": "", "approved_by": "", "source_artifacts": source_artifacts, "claims": dossier["candidate_claims"], "events": dossier["events"], "entities": dossier["entities"], "chronology": dossier["chronology"], "locations": dossier["locations"], "quotations": dossier["quotations"], "disputed_points": dossier["disputed_points"], "uncertainty_notes": dossier["unresolved_questions"], "exclusions": list(extracted.get("exclusions", [])), "religious_sensitivity": package["religious_sensitivity"], "historical_scope": package["historical_scope"], "geographical_scope": package["geographical_scope"], "provenance": {"evidence": [{"evidence_id": item.get("passage_id")} for item in dossier["extracted_passages"] if item.get("passage_id")]}, "input_fingerprint": ""}
        candidate["input_fingerprint"] = _fp(_without(candidate, "input_fingerprint"))
        dossier_path, report_path, candidate_path = output / "episode-research-dossier-v1.json", output / "episode-research-verification-v1.json", output / "evidence-review-package-v1.json"
        _write(dossier_path, dossier); _write(report_path, report); _write(candidate_path, candidate)
        source_ids = [item["source_id"] for item in package["source_items"]]
        artifacts = (_artifact(stage.stage_id, "episode-research-dossier", dossier_path, context.project_root, dossier["output_fingerprint"], sources=source_ids), _artifact(stage.stage_id, "episode-research-verification", report_path, context.project_root, report["output_fingerprint"], sources=source_ids), _artifact(stage.stage_id, "evidence-review-package", candidate_path, context.project_root, candidate["input_fingerprint"], sources=source_ids))
        status = "COMPLETED" if report["status"] in {"PASS", "PASS_WITH_WARNINGS"} else "PERMANENT_FAILURE"
        return StageExecutionResult(stage.stage_id, run_id, status, outputs=artifacts if status == "COMPLETED" else (), warnings=tuple(report["warnings"]), errors=tuple({"code": item} for item in report["errors"]), output_fingerprint=dossier["output_fingerprint"], next_action="Record human evidence approval before narrative generation.")


def build_approved_evidence_runner() -> Callable[[EpisodeContext, StageSpec, str], StageExecutionResult]:
    def run(context: EpisodeContext, stage: StageSpec, run_id: str) -> StageExecutionResult:
        approval = next((item for item in reversed(context.manifest.get("approvals", [])) if item.get("stage_id") == stage.stage_id and item.get("status") in {"APPROVED", "APPROVED_WITH_NOTES"}), None)
        candidates = [item for item in context.manifest["stage_states"].get("evidence_knowledge", {}).get("outputs", []) if item.get("artifact_type") in {"evidence-review-package", "approved-evidence-package"}]
        if approval is None or not candidates:
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_HUMAN_APPROVAL", blocker={"code": "EVIDENCE_APPROVAL_REQUIRED"})
        path = context.project_root / str(candidates[-1]["path"])
        try:
            package = _read(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "EVIDENCE_REVIEW_PACKAGE_INVALID"},))
        package.update({"schema_version": APPROVED_EVIDENCE_SCHEMA, "evidence_status": approval["status"], "approved_at": approval["resolved_at"], "approved_by": approval["reviewer"], "evidence_package_id": f"approved-{package.get('evidence_package_id', 'evidence')}"})
        package["input_fingerprint"] = _fp(_without(package, "input_fingerprint"))
        output = context.output_root / "research-verification-v1" / "approved-evidence-package-v1.json"
        _write(output, package)
        source_ids = [item["artifact_id"] for item in candidates]
        artifact = _artifact(stage.stage_id, "approved-evidence-package", output, context.project_root, package["input_fingerprint"], sources=source_ids, approval=approval["status"])
        return StageExecutionResult(stage.stage_id, run_id, "COMPLETED", outputs=(artifact,), output_fingerprint=package["input_fingerprint"], next_action="Generate the evidence-bound narrative script.")
    return run
