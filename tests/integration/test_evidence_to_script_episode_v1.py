from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from src.application.episode_orchestration_v1.runtime import (
    EpisodeOrchestrator,
    StageExecutionResult,
    StageSpec,
    default_episode_definition,
)
from src.application.evidence_to_script_episode_v1.runtime import (
    EVIDENCE_PACKAGE_SCHEMA,
    EvidenceToScriptEpisodeAdapter,
    SPEAKING_RATE_POLICY,
    build_narrative_stage_spec,
    validate_evidence_package,
    validate_episode_script,
)


def _fingerprint(value: dict[str, object]) -> str:
    from hashlib import sha256
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _package(tmp_path: Path, *, disputed: bool = False) -> Path:
    source = tmp_path / "source.json"
    source.write_text('{"source":"fixture"}', encoding="utf-8")
    claims = [
        {"claim_id": "claim-1", "normalized_claim": "وقع الحدث الأول في المدينة.", "claim_type": "EVENT", "status": "APPROVED", "confidence": 0.9, "source_refs": ["source-1"], "evidence_refs": ["evidence-1"], "chronology_refs": ["chronology-1"], "entity_refs": ["entity-1"], "dispute_status": "NONE", "approved_for_narrative": True, "restrictions": [], "notes": ""},
        {"claim_id": "claim-2", "normalized_claim": "وردت رواية مختلفة عن الحدث الثاني.", "claim_type": "EVENT", "status": "APPROVED", "confidence": 0.6, "source_refs": ["source-1"], "evidence_refs": ["evidence-2"], "chronology_refs": ["chronology-2"], "entity_refs": ["entity-2"], "dispute_status": "DISPUTED" if disputed else "NONE", "approved_for_narrative": True, "restrictions": [], "notes": ""},
        {"claim_id": "claim-3", "normalized_claim": "نقل المصدر قولًا محفوظًا.", "claim_type": "QUOTATION", "status": "APPROVED", "confidence": 0.8, "source_refs": ["source-1"], "evidence_refs": ["evidence-3"], "chronology_refs": ["chronology-3"], "entity_refs": ["entity-3"], "dispute_status": "NONE", "approved_for_narrative": True, "restrictions": [], "notes": ""},
        {"claim_id": "claim-rejected", "normalized_claim": "ادعاء مرفوض.", "claim_type": "EVENT", "status": "REJECTED", "confidence": 0.1, "source_refs": ["source-1"], "evidence_refs": ["evidence-1"], "chronology_refs": [], "entity_refs": [], "dispute_status": "NONE", "approved_for_narrative": False, "restrictions": ["DO_NOT_USE"], "notes": ""},
    ]
    package: dict[str, object] = {
        "schema_version": EVIDENCE_PACKAGE_SCHEMA, "episode_id": "episode-fixture", "source_package_id": "source-package-1", "evidence_package_id": "evidence-package-1", "evidence_status": "APPROVED", "approved_at": "2026-07-22T00:00:00Z", "approved_by": "reviewer",
        "source_artifacts": [{"artifact_id": "source-1", "path": str(source), "fingerprint": sha256(source.read_bytes()).hexdigest()}],
        "claims": claims, "events": [], "entities": [], "chronology": [{"claim_id": "claim-1"}, {"claim_id": "claim-2"}, {"claim_id": "claim-3"}], "locations": [],
        "quotations": [{"quote_id": "quote-1", "text": "قول محفوظ حرفيًا.", "source_refs": ["source-1"], "evidence_refs": ["evidence-3"]}],
        "disputed_points": [], "uncertainty_notes": ["يحتاج معنى الرواية إلى مراجعة بشرية."], "exclusions": ["عبارة محظورة"],
        "religious_sensitivity": {"status": "HUMAN_REVIEW_REQUIRED", "prohibited_depictions": ["PROPHET_VISUALIZATION"]}, "historical_scope": {"period": "fixture"}, "geographical_scope": {"region": "fixture"},
        "provenance": {"evidence": [{"evidence_id": "evidence-1"}, {"evidence_id": "evidence-2"}, {"evidence_id": "evidence-3"}]},
    }
    package["input_fingerprint"] = _fingerprint(package)
    path = tmp_path / "evidence-package.json"
    path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    return path


def _definition(tmp_path: Path, evidence: Path) -> dict[str, object]:
    source = tmp_path / "episode-source.json"
    source.write_text("{}", encoding="utf-8")
    return default_episode_definition(
        episode_id="episode-fixture", series_id="series-fixture", title="حلقة اختبار", working_title="اختبار", subject="موضوع", central_question="ما الذي تقوله الأدلة؟", intended_audience="general", source_package={"path": str(source), "approval_status": "APPROVED"}, evidence_package={"path": str(evidence), "input_fingerprint": json.loads(evidence.read_text(encoding="utf-8"))["input_fingerprint"]}, created_at="2026-07-22T00:00:00Z", updated_at="2026-07-22T00:00:00Z",
    )


class FakeEvidenceWriter:
    writer_id = "test-fake-writer"
    writer_version = "1"

    def generate(self, *, evidence_package, brief, outline):  # type: ignore[no-untyped-def]
        claims = {item["claim_id"]: item for item in evidence_package["claims"]}
        sections = []
        for section in outline["sections"]:
            blocks = []
            for claim_id in section["required_claim_ids"]:
                claim = claims[claim_id]
                text = claim["normalized_claim"]
                direct_quote = claim_id == "claim-3"
                if direct_quote:
                    text += " قول محفوظ حرفيًا."
                blocks.append({"block_id": f"{section['section_id']}-{claim_id}", "block_type": "DISPUTED_ACCOUNT" if claim["dispute_status"] != "NONE" else "CONTEXT", "assertion_class": "FACTUAL", "text": text, "claim_ids": [claim_id], "evidence_refs": claim["evidence_refs"], "source_refs": claim["source_refs"], "citation_required": True, "citation_status": "BOUND", "confidence": claim["confidence"], "disputed": claim["dispute_status"] != "NONE", "uncertainty_language": "وردت رواية مختلفة" if claim["dispute_status"] != "NONE" else None, "direct_quote": direct_quote, "quote_id": "quote-1" if direct_quote else None, "pronunciation_notes_optional": None, "restricted_content_flags": []})
            if section["order"] == len(outline["sections"]):
                filler_words = max(0, round(brief["target_duration_minutes"] * SPEAKING_RATE_POLICY["words_per_minute"]) - sum(len(block["text"].split()) for item in sections for block in item["narration_blocks"]) - sum(len(block["text"].split()) for block in blocks))
                blocks.append({"block_id": "editorial-duration", "block_type": "TRANSITION", "assertion_class": "EDITORIAL_TRANSITION", "text": " ".join(["انتقال" for _ in range(filler_words)]), "claim_ids": [], "evidence_refs": [], "source_refs": [], "citation_required": False, "citation_status": "NOT_REQUIRED", "confidence": 1.0, "disputed": False, "uncertainty_language": None, "direct_quote": False, "quote_id": None, "pronunciation_notes_optional": None, "restricted_content_flags": []})
            sections.append({"section_id": section["section_id"], "order": section["order"], "heading": section["title"], "narration_blocks": blocks, "estimated_duration_seconds": section["target_duration_seconds"], "claim_ids": section["required_claim_ids"], "source_refs": ["source-1"], "evidence_refs": ["evidence-1", "evidence-2", "evidence-3"], "quotation_ids": section["quotation_ids"], "uncertainty_markers": [], "transition": section["transition_out"], "notes": ""})
        return {"sections": sections, "quotation_index": {"quote-1": "claim-3"}}


class FailingWriter:
    writer_id = "test-failing-writer"
    writer_version = "1"

    def generate(self, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("fixture failure")


def test_approved_evidence_contract_and_rejections(tmp_path: Path) -> None:
    path = _package(tmp_path)
    package = json.loads(path.read_text(encoding="utf-8"))
    assert validate_evidence_package(package, project_root=tmp_path, episode_id="episode-fixture") == []
    package["evidence_status"] = "PENDING"
    assert "EVIDENCE_NOT_APPROVED" in validate_evidence_package(package, project_root=tmp_path, episode_id="episode-fixture")
    package = json.loads(path.read_text(encoding="utf-8"))
    package["claims"][0]["evidence_refs"] = []
    assert "CLAIM_PROVENANCE_REQUIRED:claim-1" in validate_evidence_package(package, project_root=tmp_path, episode_id="episode-fixture")
    package = json.loads(path.read_text(encoding="utf-8"))
    package["source_artifacts"][0]["path"] = "working/missing-source.json"
    assert "SOURCE_PATH_MISSING:source-1" in validate_evidence_package(package, project_root=tmp_path, episode_id="episode-fixture")
    assert "EVIDENCE_EPISODE_ID_MISMATCH" in validate_evidence_package(json.loads(path.read_text(encoding="utf-8")), project_root=tmp_path, episode_id="other")
    package["input_fingerprint"] = "invalid"
    assert "EVIDENCE_INPUT_FINGERPRINT_INVALID" in validate_evidence_package(package, project_root=tmp_path, episode_id="episode-fixture")


def test_plan_only_uses_approved_claims_and_is_deterministic(tmp_path: Path) -> None:
    evidence = _package(tmp_path, disputed=True)
    adapter = EvidenceToScriptEpisodeAdapter(tmp_path, evidence)
    definition = _definition(tmp_path, evidence)
    first, second = adapter.plan(definition), adapter.plan(definition)
    assert first["status"] == "READY" and first["brief"]["output_fingerprint"] == second["brief"]["output_fingerprint"]
    assert "claim-rejected" not in first["brief"]["required_claim_ids"]
    assert first["brief"]["evidence_coverage_summary"]["disputed_claim_ids"] == ["claim-2"]
    assert sum(section["target_duration_seconds"] for section in first["outline"]["sections"]) == 22 * 60
    assert all(section["target_word_count"] == round(section["target_duration_seconds"] * 120 / 60) for section in first["outline"]["sections"])


def test_disconnected_writer_is_honest_and_makes_no_external_call(tmp_path: Path) -> None:
    evidence = _package(tmp_path)
    adapter = EvidenceToScriptEpisodeAdapter(tmp_path, evidence)
    result = adapter.execute(_definition(tmp_path, evidence), "run-1")
    assert result.status == "NOT_IMPLEMENTED" and result.blocker["code"] == "GENERATOR_DISCONNECTED" and result.external_calls == 0


def test_fake_writer_generates_verified_evidence_bound_script_and_cache(tmp_path: Path) -> None:
    evidence = _package(tmp_path, disputed=True)
    adapter = EvidenceToScriptEpisodeAdapter(tmp_path, evidence, writer=FakeEvidenceWriter())
    definition = _definition(tmp_path, evidence)
    first = adapter.execute(definition, "run-1")
    assert first.status == "COMPLETED_WITH_WARNINGS"
    root = tmp_path / "working" / "episode-fixture" / "narrative-script-v1"
    script = json.loads((root / "episode-script-v1.json").read_text(encoding="utf-8"))
    report = json.loads((root / "episode-script-verification-v1.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS_WITH_WARNINGS" and script["approval_status"] == "PENDING"
    assert script["estimated_duration_seconds"] == 22 * 60
    assert (root / "episode-script-review-v1.md").is_file()
    second = adapter.execute(definition, "run-2")
    assert second.status == "COMPLETED_WITH_WARNINGS" and "CACHE_HIT" in second.warnings


def test_changed_evidence_versions_script_and_writer_failure_is_resumable(tmp_path: Path) -> None:
    evidence = _package(tmp_path)
    definition = _definition(tmp_path, evidence)
    adapter = EvidenceToScriptEpisodeAdapter(tmp_path, evidence, writer=FakeEvidenceWriter())
    assert adapter.execute(definition, "run-1").status == "COMPLETED"
    package = json.loads(evidence.read_text(encoding="utf-8"))
    package["uncertainty_notes"].append("ملاحظة محدثة")
    package["input_fingerprint"] = _fingerprint({key: value for key, value in package.items() if key != "input_fingerprint"})
    evidence.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    definition["evidence_package"]["input_fingerprint"] = package["input_fingerprint"]  # type: ignore[index]
    assert adapter.execute(definition, "run-2").status == "COMPLETED"
    root = tmp_path / "working" / "episode-fixture" / "narrative-script-v1"
    assert (root / "episode-script-v1-1.json").is_file()
    assert json.loads((root / "episode-script-v1.json").read_text(encoding="utf-8"))["script_version"] == 2
    failed = EvidenceToScriptEpisodeAdapter(tmp_path, evidence, writer=FailingWriter()).execute(definition, "run-3")
    assert failed.status == "RETRYABLE_FAILURE" and failed.retryable is True


def test_script_validator_catches_unsupported_quote_chronology_and_religious_failures(tmp_path: Path) -> None:
    evidence = _package(tmp_path)
    adapter = EvidenceToScriptEpisodeAdapter(tmp_path, evidence, writer=FakeEvidenceWriter())
    definition = _definition(tmp_path, evidence)
    adapter.execute(definition, "run-1")
    root = tmp_path / "working" / "episode-fixture" / "narrative-script-v1"
    package = json.loads(evidence.read_text(encoding="utf-8")); outline = json.loads((root / "episode-outline-v1.json").read_text(encoding="utf-8")); script = json.loads((root / "episode-script-v1.json").read_text(encoding="utf-8"))
    first_block = script["sections"][0]["narration_blocks"][0]
    first_block["text"] = "نص غير مدعوم"
    assert any(item.startswith("CLAIM_EXPANSION") for item in validate_episode_script(script, evidence=package, outline=outline, definition=definition))
    first_block["text"] = package["claims"][0]["normalized_claim"]
    quote_block = script["sections"][2]["narration_blocks"][0]
    quote_block["text"] = package["claims"][2]["normalized_claim"]
    assert any(item.startswith("QUOTE_ALTERATION") for item in validate_episode_script(script, evidence=package, outline=outline, definition=definition))
    quote_block["text"] = package["claims"][2]["normalized_claim"] + " قول محفوظ حرفيًا. عبارة محظورة"
    assert any(item.startswith("RELIGIOUS_OR_SCOPE") for item in validate_episode_script(script, evidence=package, outline=outline, definition=definition))


def _evidence_runner(calls: list[str]):
    def run(context, stage, run_id):  # type: ignore[no-untyped-def]
        calls.append(stage.stage_id)
        artifact = {"artifact_id": "evidence:fixture", "artifact_type": "approved-evidence-package", "stage_id": stage.stage_id, "path": "evidence-package.json", "schema_version": EVIDENCE_PACKAGE_SCHEMA, "fingerprint": "evidence-fingerprint", "created_at": "2026-07-22T00:00:00Z", "status": "COMPLETED", "approval_status": "APPROVED", "source_artifact_ids": [], "supersedes": None, "runtime_only": True, "git_trackable": False}
        return StageExecutionResult(stage.stage_id, run_id, "COMPLETED", outputs=(artifact,), output_fingerprint="evidence-fingerprint")
    return run


def test_orchestrator_runs_narrative_then_stops_for_human_approval(tmp_path: Path) -> None:
    evidence = _package(tmp_path)
    definition = _definition(tmp_path, evidence)
    calls: list[str] = []
    registry = (
        StageSpec("evidence_knowledge", "Evidence", "1", 20, "fake"),
        build_narrative_stage_spec(),
        StageSpec("script_approval", "Approval", "1", 40, "gate", dependencies=("narrative_script",), human_approval_required=True, current_implementation_status="ORCHESTRATOR_GATE"),
        StageSpec("production_tts", "TTS", "1", 50, "tts", dependencies=("script_approval",), current_implementation_status="DISCONNECTED"),
    )
    adapter = EvidenceToScriptEpisodeAdapter(tmp_path, evidence, writer=FakeEvidenceWriter())
    orchestrator = EpisodeOrchestrator(tmp_path, definition, output_root=tmp_path / "working" / "orchestrator", registry=registry, runners={"evidence_knowledge": _evidence_runner(calls), "narrative_script": adapter.as_stage_runner()})
    first = orchestrator.execute(mode="run-through")
    assert calls == ["evidence_knowledge"] and first["manifest"]["stage_states"]["narrative_script"]["status"] == "COMPLETED"
    assert first["status"] == "WAITING_FOR_HUMAN_APPROVAL"
    script_id = first["manifest"]["stage_states"]["narrative_script"]["outputs"][2]["artifact_id"]
    verification_id = first["manifest"]["stage_states"]["narrative_script"]["outputs"][3]["artifact_id"]
    with pytest.raises(ValueError, match="SCRIPT_APPROVAL_ARTIFACT_BINDING_REQUIRED"):
        orchestrator.record_approval(stage_id="script_approval", decision="APPROVED", reviewer="reviewer", artifact_ids=(script_id,))
    orchestrator.record_approval(stage_id="script_approval", decision="APPROVED", reviewer="reviewer", artifact_ids=(script_id, verification_id))
    resumed = orchestrator.execute(mode="resume")
    assert resumed["manifest"]["stage_states"]["production_tts"]["status"] == "NOT_IMPLEMENTED"
    definition["evidence_package"]["input_fingerprint"] = "changed"  # type: ignore[index]
    stale = orchestrator.execute(mode="status")["manifest"]
    assert stale["stage_states"]["narrative_script"]["status"] == "READY"
    assert stale["stage_states"]["script_approval"]["status"] == "BLOCKED_BY_DEPENDENCY"


def test_cli_json_is_clean_and_plan_never_calls_network(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.fast_track.run_evidence_to_script_episode_v1 import main
    evidence = _package(tmp_path)
    definition = _definition(tmp_path, evidence)
    definition_path = tmp_path / "episode-definition.json"
    definition_path.write_text(json.dumps(definition, ensure_ascii=False), encoding="utf-8")
    assert main(["--project-root", str(tmp_path), "--episode-definition", str(definition_path), "--evidence-package", str(evidence), "--mode", "plan", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "READY" and result["external_calls"] == 0
