from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from src.application.episode_orchestration_v1.runtime import EpisodeContext, StageSpec
from src.application.episode_quality_v1.runtime import EpisodeQAGate
from src.application.local_operator_ui_v1.runtime import LocalOperatorApplication, build_operator_server
from src.application.publication_package_v1.runtime import PublicationPackageBuilder
from src.application.research_verification_episode_v1.runtime import (
    SOURCE_PACKAGE_SCHEMA,
    ResearchVerificationEpisodeAdapter,
    validate_source_package,
)


def _source_package(root: Path) -> tuple[Path, dict]:
    source = root / "sources" / "source.txt"; source.parent.mkdir(parents=True); source.write_text("نص موثق", encoding="utf-8")
    package = {"schema_version": SOURCE_PACKAGE_SCHEMA, "episode_id": "episode-research", "source_package_id": "sources-1", "title": "بحث", "central_question": "سؤال", "historical_scope": {}, "geographical_scope": {}, "language": "ar", "source_items": [{"source_id": "source-1", "source_type": "BOOK", "title": "مصدر", "author": "", "publisher": "", "publication_date": "", "edition": "", "language": "ar", "path": source.relative_to(root).as_posix(), "checksum": sha256(source.read_bytes()).hexdigest(), "page/section availability": "YES", "access_status": "AVAILABLE", "authority_class": "PRIMARY", "primary_or_secondary": "PRIMARY", "notes": "", "allowed_for_extraction": True, "allowed_for_quotation": True, "copyright_or_usage_notes": ""}], "inclusion_policy": {}, "exclusion_policy": {}, "religious_sensitivity": {}, "research_questions": [], "created_at": "", "updated_at": ""}
    package["input_fingerprint"] = sha256(json.dumps(package, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    path = root / "source-package.json"; path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    return path, package


class FakeExtractor:
    def extract(self, *, source_package):  # type: ignore[no-untyped-def]
        claim = {"claim_id": "claim-1", "normalized_claim": "حدث موثق.", "claim_type": "EVENT", "temporal_scope": None, "geographical_scope": None, "entity_refs": [], "event_refs": [], "supporting_evidence_refs": ["passage-1"], "contradicting_evidence_refs": [], "source_refs": ["source-1"], "evidence_refs": ["passage-1"], "corroboration_count": 1, "independence_assessment": "SINGLE_SOURCE", "confidence": 0.8, "dispute_status": "NONE", "verification_status": "SUPPORTED", "approved_for_narrative": True, "restrictions": [], "uncertainty_language_requirement": "", "reviewer_notes": "", "status": "SUPPORTED", "chronology_refs": [], "notes": ""}
        return {"extractor_version": "fake", "extracted_passages": [{"passage_id": "passage-1", "source_id": "source-1", "exact_locator": "p.1", "normalized_text": "نص موثق", "verbatim": True, "extraction_method": "FIXTURE", "checksum": "x", "context_before_ref": None, "context_after_ref": None, "language": "ar", "confidence": 1.0, "reviewer_status": "PENDING"}], "claims": [claim], "events": [], "entities": [], "locations": [], "chronology": [{"claim_id": "claim-1"}], "quotations": [], "disputed_points": [], "source_relationships": [{"source_id": "source-1", "source_relationship_type": "INDEPENDENT", "parent_source_id": None, "independence_status": "INDEPENDENT", "rationale": "recorded", "deterministic_or_human_assessment": "DETERMINISTIC"}], "unresolved_questions": [], "coverage_gaps": [], "warnings": []}


def test_research_adapter_validates_provenance_and_outputs_review_candidate(tmp_path: Path) -> None:
    source_path, package = _source_package(tmp_path)
    assert validate_source_package(package, project_root=tmp_path, episode_id="episode-research") == []
    context = EpisodeContext(tmp_path, {"episode_id": "episode-research"}, {"stage_states": {}, "approvals": []}, tmp_path / "working")
    result = ResearchVerificationEpisodeAdapter(tmp_path, source_path, FakeExtractor()).run(context, StageSpec("evidence_knowledge", "Evidence", "1", 1, "fixture"), "run")
    assert result.status == "COMPLETED"
    assert {item["artifact_type"] for item in result.outputs} == {"episode-research-dossier", "episode-research-verification", "evidence-review-package"}
    assert all((tmp_path / item["path"]).is_file() for item in result.outputs)


def test_source_contract_rejects_duplicate_and_outside_paths(tmp_path: Path) -> None:
    _, package = _source_package(tmp_path)
    package["source_items"].append(dict(package["source_items"][0]))
    package["source_items"][1]["path"] = "C:/outside.txt"
    assert "SOURCE_ID_DUPLICATE" in validate_source_package(package, project_root=tmp_path, episode_id="episode-research")


def _qa_context(root: Path) -> EpisodeContext:
    video = root / "working" / "final.mp4"; video.parent.mkdir(parents=True); video.write_bytes(b"video")
    stages = {name: {"status": "COMPLETED", "outputs": []} for name in ("evidence_approval", "script_approval", "storyboard_approval", "master_visual_approval", "video_approval", "final_render_approval", "render")}
    stages["render"]["outputs"] = [{"artifact_id": "render:1", "artifact_type": "rendered-video", "stage_id": "render", "path": "working/final.mp4", "fingerprint": sha256(video.read_bytes()).hexdigest(), "created_at": "", "status": "COMPLETED", "approval_status": "APPROVED", "source_artifact_ids": [], "supersedes": None, "runtime_only": True, "git_trackable": False}]
    return EpisodeContext(root, {"episode_id": "episode-qa", "title": "عنوان", "working_title": "عنوان", "language": "ar", "central_question": "سؤال"}, {"stage_states": stages, "artifact_index": list(stages["render"]["outputs"]), "approvals": []}, root / "working" / "orchestrator")


def test_qa_and_publication_are_deterministic_and_private(tmp_path: Path) -> None:
    context = _qa_context(tmp_path)
    qa = EpisodeQAGate(); result = qa.run(context, StageSpec("qa_gate", "QA", "1", 1, "qa"), "run")
    assert result.status == "COMPLETED"
    context.manifest["stage_states"]["qa_gate"] = {"status": "COMPLETED", "outputs": list(result.outputs)}
    publication = PublicationPackageBuilder().run(context, StageSpec("publication_package", "Publication", "1", 2, "publication"), "run")
    assert publication.status == "COMPLETED"
    package = json.loads((tmp_path / publication.outputs[0]["path"]).read_text(encoding="utf-8"))
    assert "C:/" not in json.dumps(package) and package["status"] == "BUILT"


def test_qa_fails_for_stale_required_artifact(tmp_path: Path) -> None:
    context = _qa_context(tmp_path); context.manifest["stage_states"]["render"]["status"] = "STALE"
    report, _ = EpisodeQAGate().evaluate(context)
    assert report["status"] == "FAIL" and any(item["category"] == "STALE_ARTIFACT" for item in report["findings"])


class _FakeOrchestrator:
    def __init__(self) -> None: self.approvals = []
    def execute(self, *, mode: str, **kwargs):  # type: ignore[no-untyped-def]
        return {"status": "WAITING_FOR_HUMAN_APPROVAL", "manifest": {"status": "WAITING_FOR_HUMAN_APPROVAL", "current_stage": "evidence_approval", "next_action": "approve", "stage_states": {}, "approvals": self.approvals, "artifact_index": [], "execution_history": []}}
    def record_approval(self, **kwargs):  # type: ignore[no-untyped-def]
        self.approvals.append(kwargs); return {"status": "UPDATED"}


def test_local_operator_ui_is_local_safe_and_uses_services(tmp_path: Path) -> None:
    fake = _FakeOrchestrator(); app = LocalOperatorApplication(tmp_path, lambda episode_id: fake)
    assert app.episode_detail("episode-1")["status"] == "WAITING_FOR_HUMAN_APPROVAL"
    app.action("episode-1", "approve-evidence", reviewer="reviewer")
    assert fake.approvals[-1]["stage_id"] == "evidence_approval"
    with pytest.raises(ValueError, match="EPISODE_ID_INVALID"):
        app.episode_detail("../outside")
    with pytest.raises(ValueError, match="LOCALHOST_BIND_REQUIRED"):
        build_operator_server(app, host="0.0.0.0")
