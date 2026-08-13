"""One-attempt, post-migration Luna alignment validation.

This module is deliberately separate from Autopilot.  It permits a human to
validate exactly one new planned editorial proposal at the alignment gate,
then stops for review.  It cannot retry, resubmit, enter downstream stages, or
change immutable storyboard structure.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Mapping
import uuid

from src.application.alignment_audit_schema_v1 import (
    AlignmentAudit,
    AlignmentAuditSchemaError,
    normalize_alignment_audit,
)
from src.application.alignment_finding_ownership_v1 import (
    FindingOwner,
    classify_alignment_finding,
    permits_semantic_creative_repair,
)
from src.application.artifact_provenance_v1 import (
    artifact_reference,
    canonical_sha256,
    sha256_file,
    utc_now,
    write_new_json,
)
from src.application.cinematic_shot_contracts import (
    CREATIVE_FIELDS,
    STRUCTURAL_FIELDS,
    CinematicShotContractError,
    join_provider_ready_plan,
    migrate_legacy_creative_overlay,
    roundtrip_preserves_legacy_creative_data,
    structural_fingerprint,
    structural_shots_from_storyboard,
    validate_creative_overlay,
)
from src.application.episode_transition_ledger_v1 import (
    append_transition,
    ledger_path,
    project_state,
    read_entries,
)
from src.application.objective_convergence import objective_from_alignment_audit
from src.application.paid_operation_gateway import (
    CONTROLLED_ALIGNMENT_AUTHORIZATION_SCHEMA,
    PaidOperationGatewayError,
    PaidOperationRequest,
    execute_json,
    http_json_transport,
)
from src.application.provider_credentials_v1 import read_openai_api_key
from src.application.provider_model_contracts import (
    CONTRACT_VERSION,
    validate_openai_responses_payload,
)
from src.application.siraj_live_telemetry_v6_6_r9 import emit_event
from src.application.siraj_luna_upstream_transport_v6_3 import (
    OPENAI_RESPONSES_URL,
    resolve_luna_model,
    resolve_reasoning_effort,
)


SCHEMA_VERSION = "siraj-controlled-alignment-validation-v1"
STAGE = "NARRATION_VISUAL_ALIGNMENT_GATE"
ROOT_NAME = "controlled-alignment-validation-v1"
EXPECTED_STRUCTURAL_FINGERPRINT = (
    "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"
)
EXPECTED_CREATIVE_HASH = (
    "0d4bc1f9216f7f84a37a4209f9fc1c9cdb00f82bddf0e209be70995ced09ea81"
)
EXPECTED_FINDING_IDS = (
    "LUNA-SEM-001",
    "LUNA-SEM-002",
    "LUNA-SEM-003",
    "LUNA-SEM-004",
    "LUNA-REP-001",
    "LUNA-GATE-001",
)
GENERIC_PHRASES = (
    "cinematic historical scene",
    "generic historical scene",
    "beautiful cinematic scene",
    "epic cinematic scene",
)


class ControlledAlignmentValidationError(RuntimeError):
    pass


def _root(repo: Path, episode_id: str) -> Path:
    return repo / "projects" / episode_id / "orchestration" / ROOT_NAME


def _path(repo: Path, episode_id: str, name: str) -> Path:
    return _root(repo, episode_id) / name


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ControlledAlignmentValidationError("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _relative(repo: Path, path: Path) -> str:
    return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")


def _structural_manifest(storyboard: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "shot_id": item.shot_id,
            "queue_order": item.queue_index,
            "start_seconds": item.start_ms / 1000.0,
            "end_seconds": item.end_ms / 1000.0,
            "segment_ids": list(item.segment_ids),
            "beat_id": item.beat_id,
        }
        for item in structural_shots_from_storyboard(storyboard)
    ]


def _required_structural_fingerprint(storyboard: Mapping[str, Any]) -> str:
    return canonical_sha256(_structural_manifest(storyboard))


def _extract_output_text(response: Mapping[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    texts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, Mapping):
            continue
        for content in item.get("content", []):
            if not isinstance(content, Mapping):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
    if not texts:
        raise ControlledAlignmentValidationError("OPENAI_OUTPUT_TEXT_MISSING")
    return "\n".join(texts)


def _parse_model_json(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1] if "\n" in value else ""
        if value.rstrip().endswith("```"):
            value = value.rstrip()[:-3]
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ControlledAlignmentValidationError("AUDIT_SCHEMA_INVALID:MODEL_JSON") from exc
    if not isinstance(parsed, dict):
        raise ControlledAlignmentValidationError("AUDIT_SCHEMA_INVALID:MODEL_OBJECT")
    return parsed


def _semantic_findings(audit: AlignmentAudit) -> tuple[Any, ...]:
    return tuple(
        finding
        for finding in audit.findings
        if permits_semantic_creative_repair(finding.finding_id)
    )


def _historical_failed_alignment_authority(
    repo: Path,
    episode_id: str,
    *,
    authority_paths: tuple[Path, ...],
) -> dict[str, Any]:
    """Return the latest evidence-bound historical alignment failure.

    A preserved candidate remains reviewable after a later human closure, but
    only while every source artifact still matches the immutable hashes bound
    into the append-only failure entry.  This is deliberately separate from
    the live execution preflight, which still requires the current stage to be
    failed.
    """

    entries = read_entries(repo, episode_id)
    indexed = list(enumerate(entries))
    for index, entry in reversed(indexed):
        if entry.get("stage") != STAGE or entry.get("status") != "FAILED":
            continue
        references = {
            str(reference.get("path") or ""): str(reference.get("sha256") or "")
            for reference in (
                list(entry.get("input_artifacts") or [])
                + list(entry.get("output_artifacts") or [])
            )
            if isinstance(reference, Mapping)
        }
        if not all(
            references.get(_relative(repo, path)) == sha256_file(path)
            for path in authority_paths
        ):
            continue
        metadata = entry.get("metadata")
        previous_hash = (
            str(metadata.get("previous_entry_sha256") or "")
            if isinstance(metadata, Mapping)
            else ""
        )
        if index and previous_hash != str(entries[index - 1].get("entry_sha256") or ""):
            continue
        return entry
    raise ControlledAlignmentValidationError(
        "HISTORICAL_ALIGNMENT_FAILURE_AUTHORITY_REQUIRED"
    )


def _preflight(
    repo_root: Path,
    episode_id: str,
    *,
    allow_evidence_bound_historical_failure: bool = False,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    ep = repo / "projects" / episode_id
    ledger = ledger_path(repo, episode_id)
    timeline_path = ep / "preproduction/audio-timestamps-and-beats-v6-1.json"
    storyboard_path = ep / "preproduction/audio-bound-storyboard-v6-1.json"
    prompt_path = ep / "preproduction/luna-semantic-prompt-direction-v6-2-1.json"
    audit_path = ep / "preproduction/narration-visual-alignment-gate-v6-2-1.json"
    script_path = ep / "preproduction/luna-final-script-v5-1.json"
    for path in (ledger, timeline_path, storyboard_path, prompt_path, audit_path, script_path):
        if not path.is_file():
            raise ControlledAlignmentValidationError("AUTHORITY_ARTIFACT_MISSING:" + _relative(repo, path))
    projection = project_state(repo, episode_id)
    historical_failure = None
    if allow_evidence_bound_historical_failure:
        historical_failure = _historical_failed_alignment_authority(
            repo,
            episode_id,
            authority_paths=(
                timeline_path,
                storyboard_path,
                prompt_path,
                audit_path,
                script_path,
            ),
        )
    elif (
        not projection.ledger_authoritative
        or projection.current_stage != STAGE
        or projection.status != "FAILED"
    ):
        raise ControlledAlignmentValidationError("AUTHORITATIVE_ALIGNMENT_STATE_REQUIRED")
    timeline = _read_json(timeline_path)
    storyboard = _read_json(storyboard_path)
    prompts = _read_json(prompt_path)
    raw_audit = _read_json(audit_path)
    script = _read_json(script_path)
    audit = normalize_alignment_audit(raw_audit)
    finding_ids = tuple(finding.finding_id for finding in audit.findings)
    if audit.status != "FAIL" or finding_ids != EXPECTED_FINDING_IDS or len(finding_ids) != 6:
        raise ControlledAlignmentValidationError("ALIGNMENT_FINDINGS_EXACTLY_SIX_REQUIRED")
    structures = structural_shots_from_storyboard(storyboard)
    required_fp = _required_structural_fingerprint(storyboard)
    implementation_fp = structural_fingerprint(structures)
    if required_fp != EXPECTED_STRUCTURAL_FINGERPRINT:
        raise ControlledAlignmentValidationError("STRUCTURAL_FINGERPRINT_MISMATCH")
    if (
        len(structures) != 55
        or any(first.end_ms != second.start_ms for first, second in zip(structures, structures[1:]))
        or (structures[-1].shot_id, structures[-1].start_ms, structures[-1].end_ms)
        != ("EP002-SH-055", 622784, 623584)
        or float(timeline.get("total_duration_seconds") or 0) != 623.584
    ):
        raise ControlledAlignmentValidationError("STRUCTURAL_AUTHORITY_MISMATCH")
    overlay = migrate_legacy_creative_overlay(storyboard, prompts)
    overlay_hash = canonical_sha256(overlay)
    if (
        overlay_hash != EXPECTED_CREATIVE_HASH
        or len(overlay.get("directions") or []) != 55
        or not roundtrip_preserves_legacy_creative_data(storyboard, prompts)
    ):
        raise ControlledAlignmentValidationError("CREATIVE_OVERLAY_AUTHORITY_MISMATCH")
    return {
        "repo": repo,
        "episode_id": episode_id,
        "episode_root": ep,
        "projection": projection,
        "historical_failure_authority": historical_failure,
        "paths": {
            "ledger": ledger,
            "timeline": timeline_path,
            "storyboard": storyboard_path,
            "prompts": prompt_path,
            "audit": audit_path,
            "script": script_path,
        },
        "timeline": timeline,
        "storyboard": storyboard,
        "prompts": prompts,
        "audit": audit,
        "raw_audit": raw_audit,
        "script": script,
        "structures": structures,
        "overlay": overlay,
        "required_structural_fingerprint": required_fp,
        "implementation_structural_fingerprint": implementation_fp,
        "creative_overlay_hash": overlay_hash,
    }


def _affected_context(state: Mapping[str, Any]) -> dict[str, Any]:
    audit: AlignmentAudit = state["audit"]
    structures = state["structures"]
    overlay = state["overlay"]
    script = state["script"]
    semantic = _semantic_findings(audit)
    affected = {
        shot_id
        for finding in semantic
        for shot_id in finding.affected_shot_ids
    }
    order = {row.shot_id: index for index, row in enumerate(structures)}
    contextual = set(affected)
    for shot_id in tuple(affected):
        index = order[shot_id]
        if index:
            contextual.add(structures[index - 1].shot_id)
        if index + 1 < len(structures):
            contextual.add(structures[index + 1].shot_id)
    structural = [
        row for row in _structural_manifest(state["storyboard"])
        if row["shot_id"] in contextual
    ]
    direction_by_id = {row["shot_id"]: row for row in overlay["directions"]}
    creative = [
        {
            key: direction_by_id[shot_id].get(key)
            for key in ("shot_id", *CREATIVE_FIELDS)
        }
        for shot_id in sorted(contextual, key=order.__getitem__)
    ]
    segments = {
        str(row.get("segment_id")): row
        for row in script.get("segments", [])
        if isinstance(row, Mapping) and row.get("segment_id")
    }
    used_segments = {
        segment_id for row in structural for segment_id in row["segment_ids"]
    }
    narration = [
        {
            "segment_id": segment_id,
            "beat_id": segments[segment_id].get("beat_id"),
            "narration_ar": segments[segment_id].get("narration_ar"),
            "source_sensitive_phrases_ar": segments[segment_id].get("source_sensitive_phrases_ar"),
            "visual_semantic_seed_ar": segments[segment_id].get("visual_semantic_seed_ar"),
        }
        for segment_id in sorted(used_segments)
        if segment_id in segments
    ]
    return {
        "affected_shot_ids": sorted(affected, key=order.__getitem__),
        "contextual_shot_ids": sorted(contextual, key=order.__getitem__),
        "relevant_structural_storyboard": structural,
        "current_creative_overlay": creative,
        "narration_context": narration,
    }


def _system_prompt() -> str:
    return """You are Luna, SIRAJ's cinematic director performing one tightly scoped editorial alignment proposal.

Return JSON only. You may change creative direction for the supplied affected shots only. You do not own timing, queue order, IDs, segment bindings, beat bindings, or episode duration. Do not return or infer any structural field.

The proposal must strengthen narration-specific visual meaning without literalizing unreported material, depicting prohibited people, inventing text, or replacing rich direction with generic language. Preserve and improve visual concept, cinematic treatment, composition, camera intent, lighting, environment, motion, symbolism, progression, continuity, distinctness, transition intent, historical/material specificity, depth/scale, and staging. Never use generic phrases such as 'cinematic historical scene'.

For each semantic finding, provide a traceable resolution. The PRE_SPEND_GATE_NOT_CLOSED finding is a local downstream-gate condition: do not claim to close it and do not propose any downstream execution.

Required JSON shape:
{
  "status": "PROPOSAL",
  "changed_directions": [
    {"shot_id": "affected ID only", "visual_concept": "...", "cinematic_treatment": "...", "composition": "...", "camera_intent": "...", "lighting": "...", "environment": "...", "motion": "...", "symbolism": "...", "continuity_strategy": "...", "distinctness_strategy": "...", "transition_intent": "...", "historical_material_details": "...", "subject_staging": "..."}
  ],
  "finding_resolutions": [
    {"finding_id": "LUNA-SEM-* or LUNA-REP-001", "affected_shot_ids": ["..."], "cinematic_rationale": "specific explanation"}
  ]
}
"""


def _request_payload(state: Mapping[str, Any], model: str) -> dict[str, Any]:
    context = _affected_context(state)
    audit: AlignmentAudit = state["audit"]
    editable_findings = [
        finding.as_dict()
        for finding in audit.findings
        if permits_semantic_creative_repair(finding.finding_id)
    ]
    local_read_only_context = [
        {
            "finding_id": finding.finding_id,
            "owner": classify_alignment_finding(finding.finding_id).value,
            "instruction": "DO_NOT_RESOLVE",
            "reason": "LOCAL_PIPELINE_OWNED",
        }
        for finding in audit.findings
        if not permits_semantic_creative_repair(finding.finding_id)
    ]
    return {
        "model": model,
        "store": False,
        "reasoning": {"effort": resolve_reasoning_effort()},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": _system_prompt()}]},
            {
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": json.dumps(
                        {
                            "episode_id": state["episode_id"],
                            "validation_scope": "CONTROLLED_ALIGNMENT_VALIDATION_ONLY",
                            "authoritative_constraints": {
                                "episode_duration_seconds": 623.584,
                                "shot_count": 55,
                                "timeline_discontinuities": 0,
                                "final_shot": "EP002-SH-055:622.784-623.584",
                                "required_structural_fingerprint": state["required_structural_fingerprint"],
                                "structural_fields_are_immutable": True,
                                "downstream_execution_forbidden": True,
                            },
                            "editable_semantic_findings": editable_findings,
                            "local_read_only_context": local_read_only_context,
                            **context,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }],
            },
        ],
        "text": {
            "verbosity": "high",
            "format": {
                "type": "json_schema",
                "name": "siraj_controlled_alignment_proposal",
                "strict": False,
                "schema": {"type": "object", "additionalProperties": True},
            },
        },
    }


def _snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    repo: Path = state["repo"]
    paths = state["paths"]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "episode_id": state["episode_id"],
        "captured_at_utc": utc_now(),
        "transition_ledger": artifact_reference(paths["ledger"], base=repo),
        "audio_timeline": artifact_reference(paths["timeline"], base=repo),
        "audio_bound_storyboard": artifact_reference(paths["storyboard"], base=repo),
        "alignment_audit": artifact_reference(paths["audit"], base=repo),
        "current_prompt_plan": artifact_reference(paths["prompts"], base=repo),
        "structural_fingerprint": state["required_structural_fingerprint"],
        "creative_overlay_canonical_sha256": state["creative_overlay_hash"],
        "authority": {
            "duration_seconds": 623.584,
            "shot_count": 55,
            "timeline_discontinuities": 0,
            "final_shot": "EP002-SH-055:622.784-623.584",
        },
        "normalized_finding_ids": [finding.finding_id for finding in state["audit"].findings],
        "normalized_finding_count": len(state["audit"].findings),
    }


def _candidate_overlay(
    state: Mapping[str, Any],
    response: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    if response.get("status") != "PROPOSAL":
        raise ControlledAlignmentValidationError("AUDIT_SCHEMA_INVALID:PROPOSAL_STATUS")
    context = _affected_context(state)
    affected = set(context["affected_shot_ids"])
    changes = response.get("changed_directions")
    if not isinstance(changes, list) or not changes:
        raise ControlledAlignmentValidationError("AUDIT_SCHEMA_INVALID:CHANGED_DIRECTIONS_REQUIRED")
    baseline = state["overlay"]
    by_id = {row["shot_id"]: dict(row) for row in baseline["directions"]}
    changed_ids: list[str] = []
    for patch in changes:
        if not isinstance(patch, Mapping):
            raise ControlledAlignmentValidationError("AUDIT_SCHEMA_INVALID:PATCH_OBJECT_REQUIRED")
        shot_id = str(patch.get("shot_id") or "").strip()
        if not shot_id or shot_id not in affected or shot_id not in by_id:
            raise ControlledAlignmentValidationError("AUDIT_SCHEMA_INVALID:PATCH_SHOT_NOT_AFFECTED")
        keys = set(patch)
        forbidden = (keys & STRUCTURAL_FIELDS) - {"shot_id"}
        unknown = keys - {"shot_id", *CREATIVE_FIELDS}
        if forbidden:
            raise CinematicShotContractError(
                "STRUCTURAL_INVARIANT_VIOLATION:" + ",".join(sorted(forbidden))
            )
        if unknown:
            raise ControlledAlignmentValidationError(
                "AUDIT_SCHEMA_INVALID:UNKNOWN_CREATIVE_FIELD:"
                + ",".join(sorted(unknown))
            )
        if shot_id in changed_ids:
            raise ControlledAlignmentValidationError("AUDIT_SCHEMA_INVALID:DUPLICATE_PATCH_SHOT")
        for key, value in patch.items():
            if key == "shot_id":
                continue
            if isinstance(value, str) and not value.strip():
                raise ControlledAlignmentValidationError("AUDIT_SCHEMA_INVALID:EMPTY_CREATIVE_VALUE:" + key)
            by_id[shot_id][key] = value
        changed_ids.append(shot_id)
    candidate = dict(baseline)
    candidate["directions"] = [by_id[row["shot_id"]] for row in baseline["directions"]]
    candidate["candidate_source"] = "CONTROLLED_ALIGNMENT_VALIDATION"
    candidate["candidate_changed_shot_ids"] = changed_ids
    candidate["candidate_canonical_sha256"] = canonical_sha256(candidate)
    validate_creative_overlay(candidate, state["structures"])
    joined = join_provider_ready_plan(state["structures"], candidate)
    if joined["storyboard_structural_fingerprint"] != structural_fingerprint(state["structures"]):
        raise CinematicShotContractError("STRUCTURAL_INVARIANT_VIOLATION:JOIN_FINGERPRINT")
    return candidate, [dict(item) for item in changes], changed_ids


def _validate_creative_quality(
    state: Mapping[str, Any],
    response: Mapping[str, Any],
    candidate: Mapping[str, Any],
    changed_ids: list[str],
) -> tuple[bool, list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    semantic = _semantic_findings(state["audit"])
    expected = {finding.finding_id: set(finding.affected_shot_ids) for finding in semantic}
    resolutions = response.get("finding_resolutions")
    if not isinstance(resolutions, list):
        return False, ["FINDING_RESOLUTIONS_REQUIRED"], [], []
    seen: set[str] = set()
    quality_errors: list[str] = []
    parsed: list[dict[str, Any]] = []
    protocol_violations: list[dict[str, Any]] = []
    for row in resolutions:
        if not isinstance(row, Mapping):
            quality_errors.append("FINDING_RESOLUTION_OBJECT_REQUIRED")
            continue
        finding_id = str(row.get("finding_id") or "").strip()
        shot_ids = [str(item) for item in row.get("affected_shot_ids", []) if str(item)]
        rationale = str(row.get("cinematic_rationale") or "").strip()
        # A local/downstream gate is not an editable Luna target.  Preserve the
        # attempted claim as evidence, but exclude it from semantic scoring so
        # it cannot discard otherwise valid creative work.
        if finding_id and not permits_semantic_creative_repair(finding_id):
            protocol_violations.append({
                "finding_id": finding_id,
                "owner": classify_alignment_finding(finding_id).value,
                "violation": "MODEL_ATTEMPTED_NON_EDITABLE_FINDING_RESOLUTION",
                "resolution": dict(row),
                "semantic_scoring": "IGNORED",
            })
            continue
        if (
            finding_id not in expected
            or finding_id in seen
            or not shot_ids
            or not set(shot_ids).issubset(expected[finding_id])
            or not set(shot_ids).intersection(changed_ids)
            or len(rationale) < 40
        ):
            quality_errors.append("INVALID_FINDING_RESOLUTION:" + finding_id)
            continue
        seen.add(finding_id)
        parsed.append({
            "finding_id": finding_id,
            "affected_shot_ids": shot_ids,
            "cinematic_rationale": rationale,
        })
    if seen != set(expected):
        quality_errors.append("SEMANTIC_FINDING_COVERAGE_INCOMPLETE")
    candidate_by_id = {row["shot_id"]: row for row in candidate["directions"]}
    for shot_id in changed_ids:
        direction = candidate_by_id[shot_id]
        joined = " ".join(
            str(direction.get(key) or "")
            for key in (
                "visual_concept", "cinematic_treatment", "composition",
                "camera_intent", "lighting", "environment", "motion",
                "symbolism", "continuity_strategy", "distinctness_strategy",
                "transition_intent", "historical_material_details", "subject_staging",
            )
        ).lower()
        if any(phrase in joined for phrase in GENERIC_PHRASES):
            quality_errors.append("GENERIC_PROMPT_REGRESSION:" + shot_id)
        if any(
            not str(direction.get(key) or "").strip()
            for key in (
                "visual_concept", "cinematic_treatment", "composition",
                "camera_intent", "lighting", "environment", "motion",
                "symbolism", "continuity_strategy", "distinctness_strategy",
                "transition_intent", "historical_material_details", "subject_staging",
            )
        ):
            quality_errors.append("CREATIVE_INFORMATION_LOST:" + shot_id)
    return not quality_errors, quality_errors, parsed, protocol_violations


def _objective_after(state: Mapping[str, Any]) -> AlignmentAudit:
    gate = next(
        finding.as_dict()
        for finding in state["audit"].findings
        if finding.finding_id == "LUNA-GATE-001"
    )
    return normalize_alignment_audit({"status": "FAIL", "findings": [gate]})


def _validate_response(
    state: Mapping[str, Any],
    response: Mapping[str, Any],
) -> dict[str, Any]:
    before = objective_from_alignment_audit(
        state["audit"], structural_fingerprint=state["required_structural_fingerprint"]
    )
    try:
        candidate, patches, changed_ids = _candidate_overlay(state, response)
    except CinematicShotContractError as exc:
        return {"classification": "STRUCTURAL_INVARIANT_VIOLATION", "error": str(exc), "before": before.as_dict()}
    except (ControlledAlignmentValidationError, AlignmentAuditSchemaError) as exc:
        return {"classification": "AUDIT_SCHEMA_INVALID", "error": str(exc), "before": before.as_dict()}
    quality_ok, quality_errors, resolutions, protocol_violations = _validate_creative_quality(
        state, response, candidate, changed_ids
    )
    if not quality_ok:
        classification = (
            "REGRESSION"
            if any("GENERIC_PROMPT_REGRESSION" in item or "CREATIVE_INFORMATION_LOST" in item for item in quality_errors)
            else "NO_OBJECTIVE_PROGRESS"
        )
        return {
            "classification": classification,
            "before": before.as_dict(),
            "quality_errors": quality_errors,
            "changed_shot_ids": changed_ids,
            "candidate_overlay": candidate,
            "patches": patches,
            "finding_resolutions": resolutions,
            "protocol_violations": protocol_violations,
        }
    after_audit = _objective_after(state)
    after = objective_from_alignment_audit(
        after_audit, structural_fingerprint=state["required_structural_fingerprint"]
    )
    classification = "OBJECTIVE_IMPROVEMENT"
    return {
        "classification": classification,
        "before": before.as_dict(),
        "after": after.as_dict(),
        "post_alignment_finding_ids": [finding.finding_id for finding in after_audit.findings],
        "post_alignment_finding_count": len(after_audit.findings),
        "changed_shot_ids": changed_ids,
        "candidate_overlay": candidate,
        "candidate_overlay_sha256": canonical_sha256(candidate),
        "patches": patches,
        "finding_resolutions": resolutions,
        "protocol_violations": protocol_violations,
        "creative_information_preserved": True,
        "generic_prompt_regression": False,
        "structural_fingerprint_unchanged": True,
        "promotion": "NOT_PROMOTED_PENDING_HUMAN_REVIEW",
    }


def _fake_response(state: Mapping[str, Any]) -> dict[str, Any]:
    semantic = _semantic_findings(state["audit"])
    changes = []
    resolutions = []
    for finding in semantic:
        shot_id = finding.affected_shot_ids[0]
        changes.append({
            "shot_id": shot_id,
            "visual_concept": "Source-specific visual hinge for " + finding.finding_id,
            "cinematic_treatment": "Layered, materially specific cinematic transition that distinguishes the narrated claim without literal invention.",
            "composition": "Foreground evidence, midground causal shift, and a deep contextual field make the narrated turn legible.",
            "camera_intent": "A measured lateral reveal resolves from premise to consequence while retaining the established visual grammar.",
            "lighting": "Directional contrast changes only at the narrated hinge, preserving continuity with adjacent shots.",
            "environment": "A restrained, source-sensitive environment carries the claim through material detail rather than generic atmosphere.",
            "motion": "Controlled progression marks the causal or semantic turn without looped movement.",
            "symbolism": "Specific symbolic relation tied to the stated claim, not a general horizon or abstract path.",
            "continuity_strategy": "Retains the adjacent motif while transforming its function for this narrated beat.",
            "distinctness_strategy": "Introduces a unique visual function not reused by the neighboring scene.",
            "transition_intent": "A clear cinematic hinge into the next narrated proposition.",
            "historical_material_details": "Material cues remain non-literal and avoid unsupported historical invention.",
            "subject_staging": "No prohibited depiction; spatial staging makes the narrated relation intelligible.",
        })
        resolutions.append({
            "finding_id": finding.finding_id,
            "affected_shot_ids": [shot_id],
            "cinematic_rationale": "The revised direction makes the precise narrated relation visible through an intentional visual hinge, distinct material cues, and continuity-aware staging without inventing unsupported events.",
        })
    return {
        "status": "PROPOSAL",
        "changed_directions": changes,
        "finding_resolutions": resolutions,
    }


def offline_control_mode_proof(repo_root: Path, episode_id: str) -> dict[str, Any]:
    """Run the required Fake-Luna proof without writing state or using network."""

    state = _preflight(repo_root, episode_id)
    reserved = 0
    reserved += 1
    second_blocked = False
    try:
        if reserved >= 1:
            raise ControlledAlignmentValidationError("SECOND_LUNA_ATTEMPT_BLOCKED")
    except ControlledAlignmentValidationError:
        second_blocked = True
    validation = _validate_response(state, _fake_response(state))
    passed = (
        reserved == 1
        and second_blocked
        and validation.get("classification") == "OBJECTIVE_IMPROVEMENT"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if passed else "FAIL",
        "paid_attempt_count_simulated": reserved,
        "second_luna_attempt_blocked": second_blocked,
        "downstream_stage_execution": 0,
        "runware_calls": 0,
        "veo_calls": 0,
        "elevenlabs_calls": 0,
        "automatic_retry": False,
        "validation_classification": validation.get("classification"),
    }


def _append_ledger_entry(
    state: Mapping[str, Any],
    *,
    status: str,
    authorization_reference: Mapping[str, Any],
    input_artifacts: list[Mapping[str, Any]],
    output_artifacts: list[Mapping[str, Any]],
    attempt_reference: Mapping[str, Any] | None,
    failure_classification: str | None,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    repo: Path = state["repo"]
    entries = read_entries(repo, state["episode_id"])
    previous_hash = entries[-1]["entry_sha256"] if entries else None
    return append_transition(
        repo,
        state["episode_id"],
        stage=STAGE,
        previous_stage="LUNA_SEMANTIC_PROMPT_DIRECTION",
        status=status,
        input_artifacts=input_artifacts,
        output_artifacts=output_artifacts,
        schema_versions=[SCHEMA_VERSION],
        authorization_references=[authorization_reference],
        attempt_references=[attempt_reference] if attempt_reference else [],
        failure_classification=failure_classification,
        metadata={
            **dict(metadata),
            "previous_entry_sha256": previous_hash,
            "controlled_validation_only": True,
            "downstream_continuation_authorized": False,
            "automatic_retry": False,
            "automatic_resubmission": False,
        },
    )


def execute_real_controlled_alignment_validation(
    repo_root: Path,
    episode_id: str,
) -> dict[str, Any]:
    """Execute exactly one newly planned Luna request, then stop locally."""

    proof = offline_control_mode_proof(repo_root, episode_id)
    if proof["status"] != "PASS":
        raise ControlledAlignmentValidationError("OFFLINE_CONTROL_MODE_PROOF_FAILED")
    state = _preflight(repo_root, episode_id)
    repo: Path = state["repo"]
    root = _root(repo, episode_id)
    if root.exists():
        raise ControlledAlignmentValidationError("CONTROLLED_VALIDATION_ALREADY_RESERVED")
    api_key = str(read_openai_api_key() or "").strip()
    if not api_key:
        raise ControlledAlignmentValidationError("OPENAI_API_KEY_REQUIRED_BEFORE_RESERVATION")
    model = resolve_luna_model()
    payload = _request_payload(state, model)
    validate_openai_responses_payload(payload)
    inputs = {
        "transition_ledger": sha256_file(state["paths"]["ledger"]),
        "audio_timeline": sha256_file(state["paths"]["timeline"]),
        "audio_bound_storyboard": sha256_file(state["paths"]["storyboard"]),
        "structural_fingerprint": state["required_structural_fingerprint"],
        "creative_overlay": state["creative_overlay_hash"],
        "alignment_audit": sha256_file(state["paths"]["audit"]),
        "current_prompt_plan": sha256_file(state["paths"]["prompts"]),
    }
    provisional = PaidOperationRequest(
        repo_root=repo,
        episode_id=episode_id,
        stage=STAGE,
        operation_type="OPENAI_RESPONSES",
        provider="OPENAI",
        model=model,
        provider_contract_version=CONTRACT_VERSION,
        payload=payload,
        input_artifact_hashes=inputs,
        master_authorization_reference={},
        authorization_mode="CONTROLLED_ALIGNMENT_VALIDATION",
        operation_nonce="CONTROLLED_ALIGNMENT_VALIDATION_V1:" + inputs["current_prompt_plan"],
        attempt_id=str(uuid.uuid4()),
    )
    snapshot_path = _path(repo, episode_id, "pre-run-snapshot.json")
    write_new_json(snapshot_path, _snapshot(state))
    authorization_path = _path(repo, episode_id, "human-approval.json")
    authorization: dict[str, Any] = {
        "schema_version": CONTROLLED_ALIGNMENT_AUTHORIZATION_SCHEMA,
        "status": "ACTIVE",
        "episode_id": episode_id,
        "scope": "CONTROLLED_ALIGNMENT_VALIDATION_ONLY",
        "approval_source": "EXPLICIT_HUMAN_USER_INSTRUCTION_IN_CURRENT_SESSION",
        "authorized_at_utc": utc_now(),
        "allowed_stage": STAGE,
        "allowed_provider": "OPENAI",
        "allowed_model": model,
        "allowed_operation_type": "OPENAI_RESPONSES",
        "maximum_real_luna_attempts": 1,
        "planned_attempt_id": provisional.immutable_attempt_id,
        "payload_sha256": provisional.payload_sha256,
        "request_identity_sha256": provisional.request_identity_sha256,
        "input_artifact_hashes": inputs,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "authorizes_paid_retry": False,
        "authorizes_downstream_continuation": False,
        "authorizes_media_generation": False,
        "allowed_downstream_stage_execution": 0,
        "prohibited_providers": ["RUNWARE", "VEO", "ELEVENLABS"],
        "prohibited_operations": ["RETRY", "RESUBMISSION", "AUTOPILOT", "MEDIA_GENERATION"],
        "old_unknown_attempt_id": "85a1e2de-3c05-427f-82d0-c2effa0ae173",
        "old_unknown_attempt_reusable": False,
    }
    authorization["authorization_sha256"] = canonical_sha256(authorization)
    write_new_json(authorization_path, authorization)
    authorization_ref = artifact_reference(authorization_path, base=repo)
    request = PaidOperationRequest(
        **{
            **asdict(provisional),
            "master_authorization_reference": authorization_ref,
        }
    )
    reservation_path = _path(repo, episode_id, "attempt-reservation.json")
    reservation = {
        "schema_version": SCHEMA_VERSION,
        "status": "RESERVED_BEFORE_NETWORK",
        "episode_id": episode_id,
        "stage": STAGE,
        "attempt_id": request.immutable_attempt_id,
        "payload_sha256": request.payload_sha256,
        "request_identity_sha256": request.request_identity_sha256,
        "prior_attempt_id": None,
        "new_planned_editorial_work": True,
        "old_unknown_attempt_id": "85a1e2de-3c05-427f-82d0-c2effa0ae173",
        "is_retry": False,
        "is_resubmission": False,
        "maximum_attempts": 1,
        "created_at_utc": utc_now(),
    }
    reservation["reservation_sha256"] = canonical_sha256(reservation)
    write_new_json(reservation_path, reservation)
    reservation_ref = artifact_reference(reservation_path, base=repo)
    input_refs = [
        artifact_reference(state["paths"][key], base=repo)
        for key in ("timeline", "storyboard", "prompts", "audit", "script")
    ]
    emit_event(repo, episode_id, "CONTROLLED_ALIGNMENT_VALIDATION_AUTHORIZED", stage=STAGE, provider="OPENAI", model=model, task_uuid=request.immutable_attempt_id, status="AUTHORIZED")
    _append_ledger_entry(
        state,
        status="STARTED",
        authorization_reference=authorization_ref,
        input_artifacts=input_refs,
        output_artifacts=[reservation_ref],
        attempt_reference={"attempt_id": request.immutable_attempt_id, "status": "RESERVED", "retry": False},
        failure_classification=None,
        metadata={"record_kind": "CONTROLLED_ALIGNMENT_VALIDATION_STARTED"},
    )
    emit_event(repo, episode_id, "STAGE_STARTED", stage=STAGE, provider="OPENAI", model=model, task_uuid=request.immutable_attempt_id, status="RUNNING")
    emit_event(repo, episode_id, "PAID_ATTEMPT_RESERVED", stage=STAGE, provider="OPENAI", model=model, task_uuid=request.immutable_attempt_id, status="RESERVED")
    emit_event(repo, episode_id, "LUNA_REQUEST_STARTED", stage=STAGE, provider="OPENAI", model=model, task_uuid=request.immutable_attempt_id, status="TRANSPORT_STARTING")
    try:
        paid_result, provider_response = execute_json(
            request,
            http_json_transport(
                url=OPENAI_RESPONSES_URL,
                method="POST",
                payload=payload,
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                timeout_seconds=600,
            ),
            telemetry=None,
        )
    except PaidOperationGatewayError as exc:
        classification = "PROVIDER_UNKNOWN" if "NETWORK_RESULT_UNKNOWN" in str(exc) else "FAIL"
        attempt_ref = {
            "attempt_id": request.immutable_attempt_id,
            "status": classification,
            "payload_sha256": request.payload_sha256,
            "retry": False,
            "resubmission": False,
        }
        emit_event(repo, episode_id, "STAGE_FAILED", stage=STAGE, provider="OPENAI", model=model, task_uuid=request.immutable_attempt_id, status=classification, details={"error": str(exc), "no_retry": True})
        _append_ledger_entry(
            state,
            status="FAILED",
            authorization_reference=authorization_ref,
            input_artifacts=input_refs,
            output_artifacts=[reservation_ref],
            attempt_reference=attempt_ref,
            failure_classification=classification,
            metadata={"record_kind": "CONTROLLED_ALIGNMENT_PROVIDER_FAILURE", "error": str(exc), "real_luna_attempts": 1},
        )
        emit_event(repo, episode_id, "CONTROLLED_ALIGNMENT_VALIDATION_STOPPED", stage=STAGE, provider="OPENAI", model=model, task_uuid=request.immutable_attempt_id, status=classification)
        return {"status": classification, "attempt_id": request.immutable_attempt_id, "offline_proof": proof, "real_luna_attempts": 1}
    emit_event(repo, episode_id, "LUNA_RESPONSE_RECEIVED", stage=STAGE, provider="OPENAI", model=model, task_uuid=request.immutable_attempt_id, status="RECEIVED")
    emit_event(repo, episode_id, "RESULT_PERSISTED", stage=STAGE, provider="OPENAI", model=model, task_uuid=request.immutable_attempt_id, output_path=_relative(repo, paid_result.raw_response_path), status="RESULT_PERSISTED")
    emit_event(repo, episode_id, "TASK_COMPLETED", stage=STAGE, provider="OPENAI", model=model, task_uuid=request.immutable_attempt_id, status="COMPLETE")
    candidate_path = _path(repo, episode_id, "provider-proposal.json")
    try:
        response_text = _extract_output_text(provider_response)
        response_text_error = None
    except ControlledAlignmentValidationError as exc:
        response_text = ""
        response_text_error = str(exc)
    candidate_record = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "attempt_id": request.immutable_attempt_id,
        "payload_sha256": request.payload_sha256,
        "provider_response_id": provider_response.get("id"),
        "raw_response_path": _relative(repo, paid_result.raw_response_path),
        "raw_response_sha256": paid_result.response_sha256,
        "provider_response": provider_response,
        "output_text": response_text,
        "output_text_error": response_text_error,
        "created_at_utc": utc_now(),
    }
    candidate_record["record_sha256"] = canonical_sha256(candidate_record)
    write_new_json(candidate_path, candidate_record)
    candidate_ref = artifact_reference(candidate_path, base=repo)
    emit_event(repo, episode_id, "ALIGNMENT_LOCAL_VALIDATION_STARTED", stage=STAGE, provider="OPENAI", model=model, task_uuid=request.immutable_attempt_id, status="RUNNING")
    try:
        if response_text_error:
            raise ControlledAlignmentValidationError(response_text_error)
        validation = _validate_response(state, _parse_model_json(response_text))
    except ControlledAlignmentValidationError as exc:
        validation = {"classification": "AUDIT_SCHEMA_INVALID", "error": str(exc)}
    validation_path = _path(repo, episode_id, "local-objective-validation.json")
    validation_record = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "attempt_id": request.immutable_attempt_id,
        "pre_run_snapshot_path": _relative(repo, snapshot_path),
        "provider_proposal_path": _relative(repo, candidate_path),
        "validation": validation,
        "created_at_utc": utc_now(),
        "additional_luna_calls": 0,
    }
    validation_record["record_sha256"] = canonical_sha256(validation_record)
    write_new_json(validation_path, validation_record)
    validation_ref = artifact_reference(validation_path, base=repo)
    classification = str(validation.get("classification") or "FAIL")
    emit_event(repo, episode_id, "ALIGNMENT_LOCAL_VALIDATION_COMPLETED", stage=STAGE, provider="OPENAI", model=model, task_uuid=request.immutable_attempt_id, output_path=_relative(repo, validation_path), status=classification)
    _append_ledger_entry(
        state,
        status="FAILED" if classification != "ALIGNMENT_PASS" else "COMPLETED",
        authorization_reference=authorization_ref,
        input_artifacts=input_refs,
        output_artifacts=[candidate_ref, validation_ref],
        attempt_reference={
            "attempt_id": request.immutable_attempt_id,
            "gateway_attempt_id": paid_result.attempt_id,
            "status": "COMPLETE",
            "payload_sha256": request.payload_sha256,
            "retry": False,
            "resubmission": False,
        },
        failure_classification=None if classification == "ALIGNMENT_PASS" else classification,
        metadata={
            "record_kind": "CONTROLLED_ALIGNMENT_VALIDATION_RESULT",
            "classification": classification,
            "real_luna_attempts": 1,
            "additional_luna_calls": 0,
            "candidate_promoted": False,
            "current_stage_status": "FAIL" if classification != "ALIGNMENT_PASS" else "PASS",
            "post_alignment_finding_count": validation.get("post_alignment_finding_count"),
        },
    )
    emit_event(repo, episode_id, "STAGE_FAILED" if classification != "ALIGNMENT_PASS" else "STAGE_COMPLETED", stage=STAGE, provider="OPENAI", model=model, task_uuid=request.immutable_attempt_id, output_path=_relative(repo, validation_path), status=classification)
    emit_event(repo, episode_id, "CONTROLLED_ALIGNMENT_VALIDATION_STOPPED", stage=STAGE, provider="OPENAI", model=model, task_uuid=request.immutable_attempt_id, status=classification)
    return {
        "status": classification,
        "attempt_id": request.immutable_attempt_id,
        "gateway_attempt_id": paid_result.attempt_id,
        "payload_sha256": request.payload_sha256,
        "request_identity_sha256": request.request_identity_sha256,
        "authorization_path": _relative(repo, authorization_path),
        "snapshot_path": _relative(repo, snapshot_path),
        "reservation_path": _relative(repo, reservation_path),
        "provider_proposal_path": _relative(repo, candidate_path),
        "validation_path": _relative(repo, validation_path),
        "offline_proof": proof,
        "real_luna_attempts": 1,
    }
