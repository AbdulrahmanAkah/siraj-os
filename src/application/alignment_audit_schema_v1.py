"""One strict, versioned narration/visual alignment audit schema."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.application.artifact_provenance_v1 import canonical_sha256


SCHEMA_VERSION = "siraj-alignment-audit-v1"
DETERMINISTIC_CATEGORIES = {
    "TIMELINE_GAP",
    "TIMELINE_OVERLAP",
    "TIMELINE_DISCONTINUITY",
    "DURATION_MISMATCH",
    "SHOT_ID_MISMATCH",
    "SEGMENT_BINDING_MISMATCH",
    "BEAT_BINDING_MISMATCH",
    "GENERATED_VIDEO_POLICY_FAILED",
    "PROMPT_SCHEMA_INVALID",
    "PRE_SPEND_GATE_NOT_CLOSED",
}


class AlignmentAuditSchemaError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AlignmentFinding:
    finding_id: str
    category: str
    scope: Mapping[str, Any]
    severity: str
    blocking: bool
    description: str
    affected_shot_ids: tuple[str, ...]
    evidence: tuple[str, ...]
    recommended_resolution_class: str

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["scope"] = dict(self.scope)
        value["affected_shot_ids"] = list(self.affected_shot_ids)
        value["evidence"] = list(self.evidence)
        return value


@dataclass(frozen=True, slots=True)
class AlignmentAudit:
    status: str
    findings: tuple[AlignmentFinding, ...]
    source_schema: str
    source_sha256: str

    @property
    def blocking_findings(self) -> tuple[AlignmentFinding, ...]:
        return tuple(finding for finding in self.findings if finding.blocking)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "findings": [finding.as_dict() for finding in self.findings],
            "source_schema": self.source_schema,
            "source_sha256": self.source_sha256,
            "normalized_finding_count": len(self.findings),
            "normalized_blocking_finding_count": len(self.blocking_findings),
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _scope(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if value is None:
        return {}
    return {"location": value}


def _normalize_finding(raw: Mapping[str, Any], index: int) -> AlignmentFinding:
    category = _text(raw.get("category") or raw.get("type"))
    if not category:
        raise AlignmentAuditSchemaError(
            f"AUDIT_SCHEMA_INVALID:FINDING_{index}:CATEGORY_REQUIRED"
        )
    scope = _scope(raw.get("scope") or raw.get("location"))
    affected = _strings(
        raw.get("affected_shot_ids")
        or scope.get("shot_ids")
        or raw.get("shot_ids")
        or raw.get("shot_id")
    )
    severity = _text(raw.get("severity") or "BLOCKER").upper()
    blocking_raw = raw.get("blocking")
    blocking = (
        bool(blocking_raw)
        if isinstance(blocking_raw, bool)
        else severity in {"BLOCKER", "CRITICAL", "HIGH", "MAJOR"}
    )
    description = _text(
        raw.get("description")
        or raw.get("finding_ar")
        or raw.get("message")
        or raw.get("why")
    )
    if not description:
        raise AlignmentAuditSchemaError(
            f"AUDIT_SCHEMA_INVALID:FINDING_{index}:DESCRIPTION_REQUIRED"
        )
    evidence = _strings(raw.get("evidence") or raw.get("why_it_fails"))
    resolution = _text(raw.get("recommended_resolution_class"))
    if not resolution:
        resolution = (
            "DETERMINISTIC_LOCAL_REPAIR"
            if category in DETERMINISTIC_CATEGORIES
            else "SEMANTIC_CINEMATIC_REPAIR"
        )
    finding_id = _text(raw.get("finding_id") or raw.get("id"))
    if not finding_id:
        finding_id = "LEGACY-" + canonical_sha256(
            {"category": category, "scope": scope, "description": description}
        )[:16].upper()
    return AlignmentFinding(
        finding_id=finding_id,
        category=category,
        scope=scope,
        severity=severity,
        blocking=blocking,
        description=description,
        affected_shot_ids=tuple(sorted(set(affected))),
        evidence=evidence,
        recommended_resolution_class=resolution,
    )


def normalize_alignment_audit(value: Mapping[str, Any]) -> AlignmentAudit:
    if not isinstance(value, Mapping):
        raise AlignmentAuditSchemaError("AUDIT_SCHEMA_INVALID:OBJECT_REQUIRED")
    status = _text(value.get("status")).upper()
    if status not in {"PASS", "FAIL"}:
        raise AlignmentAuditSchemaError("AUDIT_SCHEMA_INVALID:STATUS_REQUIRED")
    source_schema = _text(value.get("schema_version") or "LEGACY_UNVERSIONED")
    if "findings" in value:
        rows = value.get("findings")
    elif "blocking_findings" in value:
        rows = value.get("blocking_findings")
    elif status == "PASS":
        rows = []
    else:
        raise AlignmentAuditSchemaError(
            "AUDIT_SCHEMA_INVALID:FAIL_FINDINGS_REQUIRED"
        )
    if not isinstance(rows, list):
        raise AlignmentAuditSchemaError("AUDIT_SCHEMA_INVALID:FINDINGS_ARRAY_REQUIRED")
    findings = tuple(
        _normalize_finding(row, index)
        for index, row in enumerate(rows, start=1)
        if isinstance(row, Mapping)
    )
    if len(findings) != len(rows):
        raise AlignmentAuditSchemaError(
            "AUDIT_SCHEMA_INVALID:FINDING_OBJECT_REQUIRED"
        )
    if status == "FAIL" and not findings:
        raise AlignmentAuditSchemaError(
            "AUDIT_SCHEMA_INVALID:FAIL_CANNOT_NORMALIZE_TO_EMPTY"
        )
    if status == "PASS" and any(finding.blocking for finding in findings):
        raise AlignmentAuditSchemaError(
            "AUDIT_SCHEMA_INVALID:PASS_HAS_BLOCKING_FINDINGS"
        )
    return AlignmentAudit(
        status=status,
        findings=findings,
        source_schema=source_schema,
        source_sha256=canonical_sha256(value),
    )


def load_alignment_audit(path: Path) -> AlignmentAudit:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AlignmentAuditSchemaError("AUDIT_SCHEMA_INVALID:UNREADABLE") from exc
    if not isinstance(value, dict):
        raise AlignmentAuditSchemaError("AUDIT_SCHEMA_INVALID:OBJECT_REQUIRED")
    return normalize_alignment_audit(value)
