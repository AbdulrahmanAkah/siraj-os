"""Evidence-bound episode scripting contracts; no model or provider is called here."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Any, Protocol

from src.application.episode_orchestration_v1.runtime import (
    EpisodeContext,
    StageExecutionResult,
    StageSpec,
)


EVIDENCE_PACKAGE_SCHEMA = "siraj-approved-evidence-package-v1"
NARRATIVE_BRIEF_SCHEMA = "siraj-episode-narrative-brief-v1"
OUTLINE_SCHEMA = "siraj-episode-outline-v1"
SCRIPT_SCHEMA = "siraj-episode-script-v1"
VERIFICATION_SCHEMA = "siraj-episode-script-verification-v1"
STAGE_RESULT_SCHEMA = "siraj-evidence-to-script-stage-result-v1"
ADAPTER_VERSION = "1.0"
SPEAKING_RATE_POLICY = {
    "schema_version": "siraj-arabic-documentary-speaking-rate-v1",
    "words_per_minute": 120,
    "minimum_words_per_minute": 105,
    "maximum_words_per_minute": 135,
}
DEFAULT_NARRATIVE_MODEL_POLICY = {
    "schema_version": "siraj-evidence-to-script-model-policy-v1",
    "provider": "CONFIG_REQUIRED",
    "model_id": "CONFIG_REQUIRED",
    "task_type": "EVIDENCE_BOUND_SCRIPT_DRAFTING",
    "maximum_input_tokens": 0,
    "maximum_output_tokens": 0,
    "temperature": 0,
    "structured_output_required": True,
    "grounding_policy": "APPROVED_EVIDENCE_ONLY",
    "external_confirmation_required": True,
    "disclosure_permission_required": True,
    "request_limit": 0,
    "retry_policy": "NO_AUTOMATIC_RETRY",
    "prohibited_fallbacks": ["UNDECLARED_CLOUD_FALLBACK"],
    "prompt_version": "NOT_CONFIGURED",
}
FACTUAL_BLOCK_TYPES = frozenset({"OPENING", "CONTEXT", "CHRONOLOGY", "ANALYSIS", "QUOTATION", "DISPUTED_ACCOUNT", "CONCLUSION", "NEXT_EPISODE_BRIDGE"})
NON_FACTUAL_ASSERTION_CLASSES = frozenset({"EDITORIAL_TRANSITION", "RHETORICAL_FRAMING", "NON_FACTUAL_NARRATION"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("CONTRACT_NOT_OBJECT")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(value)
    temporary.replace(path)


def _within(root: Path, value: str) -> Path:
    candidate = Path(value)
    candidate = candidate if candidate.is_absolute() else root / candidate
    candidate = candidate.resolve(strict=False)
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("SOURCE_PATH_OUTSIDE_PROJECT") from error
    return candidate


def _without(value: dict[str, Any], *names: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in names}


def _words(text: str) -> int:
    return len([part for part in text.split() if part])


def _claim_map(package: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(claim["claim_id"]): claim for claim in package.get("claims", []) if isinstance(claim, dict) and claim.get("claim_id")}


def _approved_claim_ids(package: dict[str, Any]) -> list[str]:
    return [str(claim["claim_id"]) for claim in package["claims"] if claim.get("approved_for_narrative") is True and claim.get("status") not in {"REJECTED", "EXCLUDED"}]


def validate_model_policy(policy: dict[str, Any]) -> list[str]:
    required = {"provider", "model_id", "task_type", "maximum_input_tokens", "maximum_output_tokens", "temperature", "structured_output_required", "grounding_policy", "external_confirmation_required", "disclosure_permission_required", "request_limit", "retry_policy", "prohibited_fallbacks", "prompt_version"}
    return [f"MODEL_POLICY_FIELD_MISSING:{field}" for field in sorted(required - set(policy))]


def validate_evidence_package(package: dict[str, Any], *, project_root: Path, episode_id: str) -> list[str]:
    """Validate only recorded provenance and policy; no semantic fact judgement occurs."""
    errors: list[str] = []
    required = {
        "schema_version", "episode_id", "source_package_id", "evidence_package_id", "evidence_status",
        "approved_at", "approved_by", "source_artifacts", "claims", "events", "entities", "chronology",
        "locations", "quotations", "disputed_points", "uncertainty_notes", "exclusions",
        "religious_sensitivity", "historical_scope", "geographical_scope", "provenance", "input_fingerprint",
    }
    errors.extend(f"EVIDENCE_FIELD_MISSING:{field}" for field in sorted(required - set(package)))
    if package.get("schema_version") != EVIDENCE_PACKAGE_SCHEMA:
        errors.append("EVIDENCE_SCHEMA_INVALID")
    if package.get("episode_id") != episode_id:
        errors.append("EVIDENCE_EPISODE_ID_MISMATCH")
    if package.get("evidence_status") not in {"APPROVED", "APPROVED_WITH_NOTES"}:
        errors.append("EVIDENCE_NOT_APPROVED")
    for key in ("source_package_id", "evidence_package_id", "approved_at", "approved_by"):
        if not isinstance(package.get(key), str) or not package[key].strip():
            errors.append(f"EVIDENCE_FIELD_INVALID:{key}")
    if not isinstance(package.get("source_artifacts"), list) or not package["source_artifacts"]:
        errors.append("SOURCE_ARTIFACTS_INVALID")
        source_ids: set[str] = set()
    else:
        source_ids = set()
        for source in package["source_artifacts"]:
            if not isinstance(source, dict) or not all(isinstance(source.get(field), str) and source[field] for field in ("artifact_id", "path", "fingerprint")):
                errors.append("SOURCE_ARTIFACT_INVALID")
                continue
            if source["artifact_id"] in source_ids:
                errors.append("SOURCE_ARTIFACT_ID_DUPLICATE")
            source_ids.add(source["artifact_id"])
            try:
                if not _within(project_root, source["path"]).is_file():
                    errors.append(f"SOURCE_PATH_MISSING:{source['artifact_id']}")
            except ValueError as error:
                errors.append(str(error))
    provenance = package.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("PROVENANCE_INVALID")
        evidence_ids: set[str] = set()
    else:
        evidence_ids = {str(item.get("evidence_id")) for item in provenance.get("evidence", []) if isinstance(item, dict) and item.get("evidence_id")}
        if not evidence_ids:
            errors.append("PROVENANCE_EVIDENCE_REQUIRED")
    claims = package.get("claims")
    if not isinstance(claims, list):
        errors.append("CLAIMS_INVALID")
        claims = []
    seen_claims: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append("CLAIM_INVALID")
            continue
        required_claim = {"claim_id", "normalized_claim", "claim_type", "status", "confidence", "source_refs", "evidence_refs", "chronology_refs", "entity_refs", "dispute_status", "approved_for_narrative", "restrictions", "notes"}
        missing = required_claim - set(claim)
        if missing:
            errors.append(f"CLAIM_FIELD_MISSING:{','.join(sorted(missing))}")
            continue
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            errors.append("CLAIM_ID_INVALID")
            continue
        if claim_id in seen_claims:
            errors.append("CLAIM_ID_DUPLICATE")
        seen_claims.add(claim_id)
        if not isinstance(claim.get("normalized_claim"), str) or not claim["normalized_claim"].strip():
            errors.append(f"CLAIM_TEXT_INVALID:{claim_id}")
        if claim.get("status") in {"REJECTED", "EXCLUDED"} and claim.get("approved_for_narrative") is True:
            errors.append(f"CLAIM_REJECTED_FOR_NARRATIVE:{claim_id}")
        if claim.get("approved_for_narrative") is True:
            if not claim.get("source_refs") or not claim.get("evidence_refs"):
                errors.append(f"CLAIM_PROVENANCE_REQUIRED:{claim_id}")
            if any(ref not in source_ids for ref in claim.get("source_refs", [])):
                errors.append(f"CLAIM_SOURCE_REF_INVALID:{claim_id}")
            if any(ref not in evidence_ids for ref in claim.get("evidence_refs", [])):
                errors.append(f"CLAIM_EVIDENCE_REF_INVALID:{claim_id}")
    expected = _fingerprint(_without(package, "input_fingerprint"))
    if package.get("input_fingerprint") != expected:
        errors.append("EVIDENCE_INPUT_FINGERPRINT_INVALID")
    return sorted(set(errors))


def build_narrative_brief(definition: dict[str, Any], package: dict[str, Any]) -> dict[str, Any]:
    required_ids = _approved_claim_ids(package)
    excluded_ids = [str(claim["claim_id"]) for claim in package["claims"] if claim.get("approved_for_narrative") is not True]
    disputed_ids = [str(claim["claim_id"]) for claim in package["claims"] if claim.get("dispute_status") not in {None, "NONE", "UNDISPUTED"}]
    value = {
        "schema_version": NARRATIVE_BRIEF_SCHEMA,
        "episode_id": definition["episode_id"],
        "title": definition["title"], "working_title": definition["working_title"],
        "central_question": definition["central_question"],
        "narrative_thesis": definition["central_question"],
        "intended_audience": definition["intended_audience"],
        "target_duration_minutes": definition["target_duration_minutes"],
        "tone": "ARABIC_DOCUMENTARY_EVIDENCE_BOUND",
        "point_of_view": "EVIDENCE_FIRST_NARRATOR",
        "historical_scope": package["historical_scope"], "geographical_scope": package["geographical_scope"],
        "opening_strategy": "CENTRAL_QUESTION_WITHOUT_UNSUPPORTED_ASSERTION",
        "narrative_arc": ["OPENING", "CONTEXT", "CHRONOLOGY", "CONCLUSION"],
        "major_sections": ["OPENING", "DEVELOPMENT", "CONCLUSION"],
        "chronology_strategy": "PRESERVE_PACKAGE_ORDER",
        "disputed_material_strategy": "EXPLICIT_UNCERTAINTY_LANGUAGE",
        "quotation_strategy": "VERBATIM_ONLY",
        "religious_sensitivity_rules": package["religious_sensitivity"],
        "prohibited_assertions": package.get("exclusions", []),
        "required_claim_ids": required_ids, "optional_claim_ids": [], "excluded_claim_ids": excluded_ids,
        "unresolved_questions": list(package.get("uncertainty_notes", [])),
        "evidence_coverage_summary": {"approved_claim_count": len(required_ids), "disputed_claim_ids": disputed_ids},
        "created_at": _utc_now(),
    }
    value["input_fingerprint"] = _fingerprint({"definition": definition, "evidence": package["input_fingerprint"]})
    value["output_fingerprint"] = _fingerprint(_without(value, "output_fingerprint", "created_at"))
    return value


def build_episode_outline(brief: dict[str, Any], package: dict[str, Any]) -> dict[str, Any]:
    target_seconds = int(brief["target_duration_minutes"] * 60)
    ids = list(brief["required_claim_ids"])
    partitions = [ids[:1], ids[1:-1], ids[-1:]] if len(ids) > 2 else [ids[:1], ids[1:], []]
    durations = [target_seconds // 5, target_seconds - 2 * (target_seconds // 5), target_seconds // 5]
    quotation_ids = [str(item.get("quote_id")) for item in package.get("quotations", []) if isinstance(item, dict) and item.get("quote_id")]
    sections = []
    for index, (role, claims, seconds) in enumerate(zip(("OPENING", "DEVELOPMENT", "CONCLUSION"), partitions, durations), start=1):
        sections.append({
            "section_id": f"section-{index:02d}", "order": index, "title": role,
            "narrative_function": role, "target_duration_seconds": seconds,
            "target_word_count": round(seconds * SPEAKING_RATE_POLICY["words_per_minute"] / 60),
            "required_claim_ids": claims, "optional_claim_ids": [],
            "quotation_ids": quotation_ids if role == "DEVELOPMENT" else [],
            "transition_in": "NONE" if index == 1 else "EVIDENCE_BOUND_TRANSITION",
            "transition_out": "EVIDENCE_BOUND_TRANSITION" if index < 3 else "NONE",
            "uncertainty_handling": "EXPLICIT_FOR_DISPUTED_CLAIMS", "visual_intent_optional": "NONE", "notes": "",
        })
    value = {"schema_version": OUTLINE_SCHEMA, "episode_id": brief["episode_id"], "speaking_rate_policy": SPEAKING_RATE_POLICY, "target_duration_seconds": target_seconds, "sections": sections, "input_fingerprint": _fingerprint({"brief": brief["output_fingerprint"], "evidence": package["input_fingerprint"]})}
    value["output_fingerprint"] = _fingerprint(_without(value, "output_fingerprint"))
    return value


def validate_outline(outline: dict[str, Any], brief: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if outline.get("schema_version") != OUTLINE_SCHEMA or outline.get("episode_id") != brief.get("episode_id"):
        errors.append("OUTLINE_CONTRACT_INVALID")
    sections = outline.get("sections")
    if not isinstance(sections, list) or not sections:
        return errors + ["OUTLINE_SECTIONS_INVALID"]
    ids = [section.get("section_id") for section in sections if isinstance(section, dict)]
    if len(ids) != len(set(ids)) or not all(isinstance(item, str) and item for item in ids):
        errors.append("OUTLINE_SECTION_ID_INVALID")
    if [section.get("order") for section in sections] != list(range(1, len(sections) + 1)):
        errors.append("OUTLINE_ORDER_INVALID")
    if sum(section.get("target_duration_seconds", 0) for section in sections) != outline.get("target_duration_seconds"):
        errors.append("OUTLINE_DURATION_TOTAL_INVALID")
    allowed = set(brief["required_claim_ids"]) | set(brief["optional_claim_ids"])
    allocated = []
    for section in sections:
        claims = section.get("required_claim_ids", []) + section.get("optional_claim_ids", [])
        allocated.extend(claims)
        expected_words = round(section.get("target_duration_seconds", 0) * SPEAKING_RATE_POLICY["words_per_minute"] / 60)
        if section.get("target_word_count") != expected_words:
            errors.append("OUTLINE_WORD_COUNT_POLICY_INVALID")
    if any(claim not in allowed for claim in allocated) or set(brief["required_claim_ids"]) - set(allocated):
        errors.append("OUTLINE_CLAIM_ALLOCATION_INVALID")
    return sorted(set(errors))


class EvidenceBoundScriptWriter(Protocol):
    writer_id: str
    writer_version: str

    def generate(self, *, evidence_package: dict[str, Any], brief: dict[str, Any], outline: dict[str, Any]) -> dict[str, Any]: ...


def _normalise_script(writer_result: dict[str, Any], *, definition: dict[str, Any], evidence: dict[str, Any], brief: dict[str, Any], outline: dict[str, Any], prior: dict[str, Any] | None) -> dict[str, Any]:
    sections = writer_result.get("sections")
    if not isinstance(sections, list):
        raise ValueError("WRITER_RESULT_SECTIONS_INVALID")
    script_version = int(prior.get("script_version", 0)) + 1 if prior else 1
    full_text = "\n\n".join(block.get("text", "") for section in sections if isinstance(section, dict) for block in section.get("narration_blocks", []) if isinstance(block, dict))
    claim_usage = {claim_id: [] for claim_id in _approved_claim_ids(evidence)}
    citation_index: dict[str, list[str]] = {}
    uncertainty: list[dict[str, Any]] = []
    for section in sections:
        for block in section.get("narration_blocks", []):
            for claim_id in block.get("claim_ids", []):
                claim_usage.setdefault(claim_id, []).append(block.get("block_id"))
            citation_index[block.get("block_id", "")] = list(block.get("evidence_refs", []))
            if block.get("uncertainty_language"):
                uncertainty.append({"block_id": block.get("block_id"), "language": block.get("uncertainty_language")})
    value = {
        "schema_version": SCRIPT_SCHEMA, "episode_id": definition["episode_id"],
        "script_id": _fingerprint({"brief": brief["output_fingerprint"], "outline": outline["output_fingerprint"], "sections": sections})[:24],
        "script_version": script_version, "previous_script_id": prior.get("script_id") if prior else None,
        "supersedes": prior.get("script_id") if prior else None,
        "revision_reason": "INPUT_FINGERPRINT_CHANGED" if prior else "INITIAL_GENERATION",
        "changed_sections": [section.get("section_id") for section in sections],
        "changed_claim_usage": sorted(claim_usage), "language": definition["language"], "title": definition["title"],
        "target_duration_minutes": definition["target_duration_minutes"],
        "estimated_duration_seconds": round(_words(full_text) * 60 / SPEAKING_RATE_POLICY["words_per_minute"]),
        "estimated_word_count": _words(full_text), "speaking_rate_policy": SPEAKING_RATE_POLICY,
        "narrator_profile": "ARABIC_DOCUMENTARY_NARRATOR", "sections": sections,
        "full_narration_text": full_text, "claim_usage_index": claim_usage, "citation_index": citation_index,
        "quotation_index": writer_result.get("quotation_index", {}), "uncertainty_index": uncertainty,
        "prohibited_content_check": "PENDING_DETERMINISTIC_VALIDATION", "religious_sensitivity_check": "PENDING_DETERMINISTIC_VALIDATION",
        "evidence_coverage": {"used_claim_ids": sorted(claim_id for claim_id, blocks in claim_usage.items() if blocks), "unused_claim_ids": sorted(claim_id for claim_id, blocks in claim_usage.items() if not blocks)},
        "unresolved_items": list(evidence.get("uncertainty_notes", [])), "warnings": [], "approval_status": "PENDING",
        "created_at": _utc_now(), "updated_at": _utc_now(),
        "input_fingerprint": _fingerprint({"evidence": evidence["input_fingerprint"], "brief": brief["output_fingerprint"], "outline": outline["output_fingerprint"]}),
    }
    value["output_fingerprint"] = _fingerprint(_without(value, "output_fingerprint", "created_at", "updated_at"))
    return value


def validate_episode_script(script: dict[str, Any], *, evidence: dict[str, Any], outline: dict[str, Any], definition: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if script.get("schema_version") != SCRIPT_SCHEMA or script.get("episode_id") != definition.get("episode_id"):
        errors.append("SCRIPT_CONTRACT_INVALID")
    if script.get("approval_status") != "PENDING":
        errors.append("SCRIPT_APPROVAL_STATUS_INVALID")
    sections = script.get("sections")
    if not isinstance(sections, list) or not sections:
        return errors + ["SCRIPT_SECTIONS_INVALID"]
    if [section.get("section_id") for section in sections] != [section.get("section_id") for section in outline["sections"]]:
        errors.append("SCRIPT_OUTLINE_SECTION_MISMATCH")
    claims = _claim_map(evidence)
    quotes = {str(item.get("quote_id")): item for item in evidence.get("quotations", []) if isinstance(item, dict) and item.get("quote_id")}
    block_ids: set[str] = set()
    used_claims: list[str] = []
    chronology = [str(item.get("claim_id")) for item in evidence.get("chronology", []) if isinstance(item, dict) and item.get("claim_id")]
    chronology_positions = {claim_id: index for index, claim_id in enumerate(chronology)}
    last_position = -1
    prohibited = {str(item) for item in evidence.get("exclusions", []) if isinstance(item, str)}
    for section in sections:
        for block in section.get("narration_blocks", []):
            block_id = block.get("block_id")
            if not isinstance(block_id, str) or not block_id or block_id in block_ids:
                errors.append("SCRIPT_BLOCK_ID_INVALID")
            block_ids.add(str(block_id))
            text = block.get("text")
            if not isinstance(text, str) or not text.strip():
                errors.append("SCRIPT_BLOCK_TEXT_INVALID")
                continue
            claim_ids = block.get("claim_ids", [])
            assertion_class = block.get("assertion_class")
            factual = block.get("block_type") in FACTUAL_BLOCK_TYPES and assertion_class not in NON_FACTUAL_ASSERTION_CLASSES
            if factual and not claim_ids:
                errors.append(f"UNSUPPORTED_FACTUAL_ASSERTION:{block_id}")
            if not factual and not claim_ids and assertion_class not in NON_FACTUAL_ASSERTION_CLASSES:
                errors.append(f"NON_FACTUAL_CLASSIFICATION_REQUIRED:{block_id}")
            for claim_id in claim_ids:
                claim = claims.get(claim_id)
                if not claim or claim.get("approved_for_narrative") is not True or claim.get("status") in {"REJECTED", "EXCLUDED"}:
                    errors.append(f"CLAIM_NOT_APPROVED:{claim_id}")
                    continue
                used_claims.append(claim_id)
                if claim["normalized_claim"] not in text:
                    errors.append(f"CLAIM_EXPANSION_OR_UNSUPPORTED_TEXT:{block_id}")
                if any(ref not in claim.get("evidence_refs", []) for ref in block.get("evidence_refs", [])) or any(ref not in claim.get("source_refs", []) for ref in block.get("source_refs", [])):
                    errors.append(f"CITATION_LAUNDERING:{block_id}")
                if block.get("citation_required") is not True or block.get("citation_status") != "BOUND":
                    errors.append(f"CITATION_REQUIRED:{block_id}")
                if claim.get("dispute_status") not in {None, "NONE", "UNDISPUTED"} and (block.get("disputed") is not True or not block.get("uncertainty_language")):
                    errors.append(f"CERTAINTY_INFLATION:{block_id}")
                if claim_id in chronology_positions:
                    if chronology_positions[claim_id] < last_position:
                        errors.append("CHRONOLOGY_DISTORTION")
                    last_position = max(last_position, chronology_positions[claim_id])
            if block.get("direct_quote") is True:
                quote = quotes.get(str(block.get("quote_id")))
                if not quote or quote.get("text") not in text:
                    errors.append(f"QUOTE_ALTERATION:{block_id}")
            for phrase in prohibited:
                if phrase and phrase in text:
                    errors.append(f"RELIGIOUS_OR_SCOPE_PROHIBITION:{block_id}")
    if set(_approved_claim_ids(evidence)) - set(used_claims):
        errors.append("REQUIRED_CLAIM_UNUSED")
    duration = script.get("estimated_duration_seconds")
    if not isinstance(duration, (int, float)) or not 18 * 60 <= duration <= 25 * 60:
        errors.append("SCRIPT_DURATION_OUT_OF_POLICY")
    return sorted(set(errors))


def verification_report(script: dict[str, Any], *, evidence: dict[str, Any], outline: dict[str, Any], definition: dict[str, Any]) -> dict[str, Any]:
    errors = validate_episode_script(script, evidence=evidence, outline=outline, definition=definition)
    warnings = []
    disputed = [claim["claim_id"] for claim in evidence["claims"] if claim.get("dispute_status") not in {None, "NONE", "UNDISPUTED"}]
    if disputed:
        warnings.append("DISPUTED_CLAIMS_REQUIRE_HUMAN_REVIEW")
    status = "FAIL" if errors else "PASS_WITH_WARNINGS" if warnings else "PASS"
    return {"schema_version": VERIFICATION_SCHEMA, "episode_id": definition["episode_id"], "script_id": script.get("script_id"), "status": status, "deterministic_checks": {"semantic_limit": "DETERMINISTIC_BINDING_ONLY; HUMAN_REVIEW_REQUIRED_FOR_MEANING"}, "evidence_binding_summary": {"approved_claims": len(_approved_claim_ids(evidence)), "used_claims": len(script.get("evidence_coverage", {}).get("used_claim_ids", []))}, "claim_coverage": script.get("evidence_coverage", {}), "unsupported_blocks": [item for item in errors if item.startswith("UNSUPPORTED") or item.startswith("CLAIM_EXPANSION")], "unresolved_citations": [item for item in errors if "CITATION" in item], "disputed_claim_handling": {"claim_ids": disputed, "status": "HUMAN_REVIEW_REQUIRED" if disputed else "NONE"}, "chronology_findings": [item for item in errors if "CHRONOLOGY" in item], "quotation_findings": [item for item in errors if "QUOTE" in item], "religious_sensitivity_findings": [item for item in errors if "RELIGIOUS" in item], "duration_findings": [item for item in errors if "DURATION" in item], "structure_findings": [item for item in errors if "SECTION" in item or "BLOCK" in item], "warnings": warnings, "errors": errors, "human_review_required": True, "generated_at": _utc_now()}


def script_review_markdown(script: dict[str, Any], verification: dict[str, Any]) -> str:
    lines = [f"# {script['title']}", "", f"- Estimated duration: {script['estimated_duration_seconds']} seconds", f"- Estimated words: {script['estimated_word_count']}", f"- Approval: {script['approval_status']}", ""]
    for section in script["sections"]:
        lines.extend([f"## {section['heading']}", ""])
        for block in section["narration_blocks"]:
            marker = " ⚠ disputed" if block.get("disputed") else ""
            lines.extend([f"{block['text']}{marker}", "", f"Claims: {', '.join(block.get('claim_ids', [])) or 'editorial/non-factual'}", f"Evidence: {', '.join(block.get('evidence_refs', [])) or 'none'}", ""])
    lines.extend(["## Evidence coverage", "", json.dumps(script["evidence_coverage"], ensure_ascii=False, indent=2), "", "## Warnings", "", *[f"- {item}" for item in verification["warnings"] + verification["errors"]]])
    return "\n".join(lines).rstrip() + "\n"


@dataclass
class EvidenceToScriptEpisodeAdapter:
    project_root: Path
    evidence_package_path: Path
    writer: EvidenceBoundScriptWriter | None = None
    output_root: Path | None = None

    def _output_root(self, episode_id: str) -> Path:
        return self.output_root or self.project_root / "working" / episode_id / "narrative-script-v1"

    def validate_input(self, definition: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        try:
            package = _read_json(self.evidence_package_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            return None, [f"EVIDENCE_PACKAGE_UNREADABLE:{type(error).__name__}"]
        return package, validate_evidence_package(package, project_root=self.project_root, episode_id=str(definition.get("episode_id")))

    def plan(self, definition: dict[str, Any]) -> dict[str, Any]:
        package, errors = self.validate_input(definition)
        if errors or package is None:
            return {"status": "VALIDATION_ERROR", "errors": errors, "external_calls": 0}
        brief = build_narrative_brief(definition, package)
        outline = build_episode_outline(brief, package)
        outline_errors = validate_outline(outline, brief)
        return {"status": "READY" if not outline_errors else "VALIDATION_ERROR", "brief": brief, "outline": outline, "errors": outline_errors, "external_calls": 0, "writer_status": "AVAILABLE" if self.writer else "DISCONNECTED"}

    def verify(self, definition: dict[str, Any]) -> dict[str, Any]:
        package, errors = self.validate_input(definition)
        if errors or package is None:
            return {"status": "VALIDATION_ERROR", "errors": errors, "external_calls": 0}
        root = self._output_root(str(definition["episode_id"]))
        required = (root / "episode-narrative-brief-v1.json", root / "episode-outline-v1.json", root / "episode-script-v1.json")
        if not all(path.is_file() for path in required):
            return {"status": "MISSING_INPUT", "errors": ["SCRIPT_ARTIFACTS_MISSING"], "external_calls": 0}
        brief, outline, script = (_read_json(path) for path in required)
        outline_errors = validate_outline(outline, brief)
        report = verification_report(script, evidence=package, outline=outline, definition=definition)
        report["errors"] = sorted(set(report["errors"] + outline_errors))
        if report["errors"]:
            report["status"] = "FAIL"
        return report

    def status(self, definition: dict[str, Any]) -> dict[str, Any]:
        root = self._output_root(str(definition["episode_id"]))
        script_path = root / "episode-script-v1.json"
        if not script_path.is_file():
            return {"status": "NOT_STARTED", "writer_status": "AVAILABLE" if self.writer else "DISCONNECTED", "external_calls": 0}
        script = _read_json(script_path)
        return {"status": "PENDING_HUMAN_APPROVAL" if script.get("approval_status") == "PENDING" else str(script.get("approval_status")), "script_id": script.get("script_id"), "script_version": script.get("script_version"), "external_calls": 0}

    def execute(self, definition: dict[str, Any], run_id: str) -> StageExecutionResult:
        started_at = _utc_now()
        plan = self.plan(definition)
        if plan["status"] != "READY":
            return StageExecutionResult("narrative_script", run_id, "PERMANENT_FAILURE", errors=tuple({"code": item} for item in plan["errors"]), blocker={"code": "VALIDATION_ERROR"}, retryable=False, next_action="Repair the approved evidence package.", started_at=started_at, completed_at=_utc_now())
        if self.writer is None:
            return StageExecutionResult("narrative_script", run_id, "NOT_IMPLEMENTED", blocker={"code": "GENERATOR_DISCONNECTED", "safe_message": "No callable evidence-bound narrative writer is configured."}, retryable=False, next_action="Configure an approved writer adapter; no external request was made.", started_at=started_at, completed_at=_utc_now())
        package = self.validate_input(definition)[0]
        assert package is not None
        brief, outline = plan["brief"], plan["outline"]
        root = self._output_root(str(definition["episode_id"]))
        script_path = root / "episode-script-v1.json"
        prior = _read_json(script_path) if script_path.is_file() else None
        input_fingerprint = _fingerprint({"evidence": package["input_fingerprint"], "brief": brief["output_fingerprint"], "outline": outline["output_fingerprint"], "writer": {"id": self.writer.writer_id, "version": self.writer.writer_version}})
        if prior and prior.get("input_fingerprint") == input_fingerprint:
            report_path = root / "episode-script-verification-v1.json"
            if report_path.is_file() and _read_json(report_path).get("status") in {"PASS", "PASS_WITH_WARNINGS"}:
                outputs = self._artifact_outputs(root, prior, _read_json(report_path), brief, outline)
                return StageExecutionResult("narrative_script", run_id, "COMPLETED_WITH_WARNINGS" if _read_json(report_path).get("status") == "PASS_WITH_WARNINGS" else "COMPLETED", outputs=tuple(outputs), warnings=("CACHE_HIT",), input_fingerprint=input_fingerprint, output_fingerprint=prior["output_fingerprint"], next_action="Record human script approval before TTS.", started_at=started_at, completed_at=_utc_now())
        try:
            raw = self.writer.generate(evidence_package=package, brief=brief, outline=outline)
        except Exception as error:  # The writer boundary is intentionally normalized without exposing prompts or secrets.
            return StageExecutionResult("narrative_script", run_id, "RETRYABLE_FAILURE", errors=({"code": "WRITER_RUNTIME_FAILURE", "exception_class": type(error).__name__},), blocker={"code": "WRITER_RUNTIME_FAILURE"}, retryable=True, input_fingerprint=input_fingerprint, next_action="Inspect the configured writer adapter and resume; prior artifacts are preserved by the orchestrator.", started_at=started_at, completed_at=_utc_now())
        if not isinstance(raw, dict):
            return StageExecutionResult("narrative_script", run_id, "PERMANENT_FAILURE", errors=({"code": "WRITER_RESULT_INVALID"},), blocker={"code": "WRITER_RESULT_INVALID"}, retryable=False, input_fingerprint=input_fingerprint, next_action="Repair the structured writer contract.", started_at=started_at, completed_at=_utc_now())
        script = _normalise_script(raw, definition=definition, evidence=package, brief=brief, outline=outline, prior=prior)
        script["input_fingerprint"] = input_fingerprint
        script["output_fingerprint"] = _fingerprint(_without(script, "output_fingerprint", "created_at", "updated_at"))
        report = verification_report(script, evidence=package, outline=outline, definition=definition)
        if report["status"] == "FAIL":
            return StageExecutionResult("narrative_script", run_id, "PERMANENT_FAILURE", errors=tuple({"code": item} for item in report["errors"]), blocker={"code": "SCRIPT_VERIFICATION_FAILED"}, retryable=False, input_fingerprint=input_fingerprint, output_fingerprint=script["output_fingerprint"], next_action="Repair the writer output or evidence package.", started_at=started_at, completed_at=_utc_now())
        root.mkdir(parents=True, exist_ok=True)
        if prior:
            _write_json(root / f"episode-script-v1-{prior['script_version']}.json", prior)
        _write_json(root / "episode-narrative-brief-v1.json", brief)
        _write_json(root / "episode-outline-v1.json", outline)
        _write_json(script_path, script)
        _write_json(root / "episode-script-verification-v1.json", report)
        _write_text(root / "episode-script-review-v1.md", script_review_markdown(script, report))
        outputs = self._artifact_outputs(root, script, report, brief, outline)
        result = StageExecutionResult("narrative_script", run_id, "COMPLETED_WITH_WARNINGS" if report["status"] == "PASS_WITH_WARNINGS" else "COMPLETED", outputs=tuple(outputs), warnings=tuple(report["warnings"]), input_fingerprint=input_fingerprint, output_fingerprint=script["output_fingerprint"], next_action="Record human script approval before TTS.", started_at=started_at, completed_at=_utc_now())
        _write_json(root / "stage-execution-result-v1.json", {"schema_version": STAGE_RESULT_SCHEMA, **asdict(result)})
        return result

    def _artifact_outputs(self, root: Path, script: dict[str, Any], report: dict[str, Any], brief: dict[str, Any], outline: dict[str, Any]) -> list[dict[str, Any]]:
        items = [("narrative-brief", "episode-narrative-brief-v1.json", brief["output_fingerprint"], NARRATIVE_BRIEF_SCHEMA), ("episode-outline", "episode-outline-v1.json", outline["output_fingerprint"], OUTLINE_SCHEMA), ("episode-script", "episode-script-v1.json", script["output_fingerprint"], SCRIPT_SCHEMA), ("script-verification", "episode-script-verification-v1.json", _fingerprint(report), VERIFICATION_SCHEMA)]
        return [{"artifact_id": f"{kind}:{script['script_id']}", "artifact_type": kind, "stage_id": "narrative_script", "path": (root / path).resolve().relative_to(self.project_root.resolve()).as_posix(), "schema_version": schema, "fingerprint": fingerprint, "created_at": _utc_now(), "status": "COMPLETED", "approval_status": "PENDING" if kind == "episode-script" else "NOT_REQUESTED", "source_artifact_ids": [], "supersedes": script.get("supersedes") if kind == "episode-script" else None, "runtime_only": True, "git_trackable": False} for kind, path, fingerprint, schema in items]

    def as_stage_runner(self):
        def run(context: EpisodeContext, stage: StageSpec, run_id: str) -> StageExecutionResult:
            if stage.stage_id != "narrative_script":
                raise ValueError("EVIDENCE_TO_SCRIPT_STAGE_MISMATCH")
            result = self.execute(context.definition, run_id)
            # The orchestrator owns the stage fingerprint; the adapter keeps its richer
            # evidence/writer fingerprint inside the canonical script artifact and cache.
            return replace(result, input_fingerprint=context.manifest["stage_states"][stage.stage_id]["input_fingerprint"])
        return run


def build_narrative_stage_spec() -> StageSpec:
    """An available status is valid only when paired with adapter.as_stage_runner()."""
    return StageSpec("narrative_script", "Evidence-bound narrative script", "1", 30, "evidence_to_script_episode_v1", ("approved-evidence-package-v1",), ("episode-script-v1", "script-verification-v1"), dependencies=("evidence_knowledge",), retry_policy="NO_AUTOMATIC_RETRY", current_implementation_status="AVAILABLE_LOCAL_ADAPTER")
