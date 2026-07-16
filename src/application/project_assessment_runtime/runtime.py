from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from src.application.operations_common import (
    CANONICAL_TIMESTAMP,
    deterministic_id,
)
from src.application.project_runtime import (
    load_project,
    load_sources,
    project_paths,
)
from src.application.rc_hardening import (
    SQLiteConnectionConfig,
    SQLitePersistenceAdapter,
)


ASSESSMENT_SCHEMA_VERSION = "siraj-claim-assessment-v1"

_NUMBER_PATTERN = re.compile(
    r"(?<![\w])(?:\d{1,4}(?:[.,]\d+)?)(?![\w])"
)

_SPACE_PATTERN = re.compile(r"\s+")

_NEGATION_TOKENS = {
    "لا",
    "لم",
    "لن",
    "ليس",
    "ليست",
    "ما",
    "not",
    "never",
    "no",
    "did not",
    "was not",
    "is not",
}


@dataclass(frozen=True)
class ClaimAssessment:
    assessment_id: str
    claim_id: str
    claim_text: str
    status: str
    textual_support: str
    source_count: int
    independent_source_count: int
    evidence_count: int
    provenance_integrity: str
    contradiction_state: str
    coverage_state: str
    confidence_level: str
    confidence_reasons: list[str]


@dataclass(frozen=True)
class ContradictionCandidate:
    contradiction_id: str
    claim_a_id: str
    claim_b_id: str
    contradiction_type: str
    reason: str
    differing_values: list[str]
    source_ids: list[str]
    status: str = "CANDIDATE"


@dataclass(frozen=True)
class ResearchGap:
    gap_id: str
    gap_type: str
    subject_id: str
    priority: str
    reason: str
    recommended_action: str


@dataclass(frozen=True)
class SourceCoverage:
    source_id: str
    claim_count: int
    evidence_count: int
    unique_claim_count: int
    multi_source_claim_count: int
    contradiction_count: int
    coverage_state: str


@dataclass(frozen=True)
class AssessmentVerificationIssue:
    code: str
    subject_id: str = ""
    detail: str = ""


@dataclass(frozen=True)
class AssessmentVerificationReport:
    project_id: str
    status: str
    assessment_count: int
    contradiction_count: int
    gap_count: int
    source_coverage_count: int
    issues: list[AssessmentVerificationIssue]


def _absolute_path(raw: str | Path, field_name: str) -> Path:
    path = Path(raw).expanduser()

    if not path.is_absolute():
        raise ValueError(f"{field_name}_MUST_BE_ABSOLUTE")

    return path.resolve(strict=False)


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None

    try:
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=".siraj-",
            suffix=".tmp",
            delete=False,
        )
        temporary = handle.name

        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)
    finally:
        if temporary and Path(temporary).exists():
            Path(temporary).unlink(missing_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write(path, _canonical_json(payload).encode("utf-8"))


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"FILE_NOT_FOUND:{path}")

    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"INVALID_JSON:{path}:{error.lineno}:{error.colno}"
        ) from error


def _knowledge_artifact(
    project_root: Path,
    filename: str,
) -> dict[str, Any]:
    paths = project_paths(project_root)
    path = Path(paths.working_root) / "knowledge" / filename
    payload = _read_json(path)

    if payload.get("schema_version") != "siraj-knowledge-evidence-v1":
        raise ValueError("INVALID_KNOWLEDGE_SCHEMA")

    return payload


def _normalise_claim(text: str) -> str:
    return _SPACE_PATTERN.sub(
        " ",
        text.casefold().strip(),
    )


def _numeric_signature(text: str) -> tuple[str, tuple[str, ...]]:
    normalised = _normalise_claim(text)
    numbers = tuple(_NUMBER_PATTERN.findall(normalised))
    signature = _NUMBER_PATTERN.sub("{number}", normalised)
    return signature, numbers


def _contains_negation(text: str) -> bool:
    normalised = f" {_normalise_claim(text)} "

    return any(
        f" {token} " in normalised
        for token in _NEGATION_TOKENS
    )


def _lexical_signature(text: str) -> set[str]:
    normalised = _normalise_claim(text)
    without_numbers = _NUMBER_PATTERN.sub(" ", normalised)

    return {
        token
        for token in re.split(r"[^\w\u0600-\u06ff]+", without_numbers)
        if len(token) >= 3
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0

    return len(left & right) / len(left | right)


def _source_independence(
    source_ids: list[str],
    sources_by_id: dict[str, dict[str, Any]],
) -> int:
    identities: set[tuple[str, str]] = set()

    for source_id in source_ids:
        source = sources_by_id.get(source_id, {})
        identities.add(
            (
                str(source.get("sha256", "")),
                str(source.get("stored_path", "")),
            )
        )

    identities.discard(("", ""))
    return len(identities)


def _find_contradictions(
    claims: list[dict[str, Any]],
) -> list[ContradictionCandidate]:
    candidates: list[ContradictionCandidate] = []
    seen: set[tuple[str, str, str]] = set()

    for index, claim_a in enumerate(claims):
        text_a = str(claim_a["claim_text"])
        signature_a, numbers_a = _numeric_signature(text_a)
        tokens_a = _lexical_signature(text_a)

        for claim_b in claims[index + 1:]:
            text_b = str(claim_b["claim_text"])
            signature_b, numbers_b = _numeric_signature(text_b)
            tokens_b = _lexical_signature(text_b)

            contradiction_type: str | None = None
            reason = ""
            differing_values: list[str] = []

            if (
                numbers_a
                and numbers_b
                and signature_a == signature_b
                and numbers_a != numbers_b
            ):
                contradiction_type = "NUMERIC_CONFLICT"
                reason = (
                    "Claims share the same normalized textual pattern "
                    "but contain different numeric values."
                )
                differing_values = sorted(
                    set(numbers_a) | set(numbers_b)
                )

            elif (
                _jaccard(tokens_a, tokens_b) >= 0.75
                and _contains_negation(text_a)
                != _contains_negation(text_b)
            ):
                contradiction_type = "NEGATION_CONFLICT"
                reason = (
                    "Claims have strongly overlapping lexical content "
                    "but differ in explicit negation."
                )

            if contradiction_type is None:
                continue

            pair = tuple(
                sorted(
                    (
                        str(claim_a["claim_id"]),
                        str(claim_b["claim_id"]),
                    )
                )
            )
            identity = (pair[0], pair[1], contradiction_type)

            if identity in seen:
                continue

            seen.add(identity)

            source_ids = sorted(
                set(claim_a.get("source_ids", []))
                | set(claim_b.get("source_ids", []))
            )

            candidates.append(
                ContradictionCandidate(
                    contradiction_id=deterministic_id(
                        "contradiction",
                        [
                            pair,
                            contradiction_type,
                            differing_values,
                        ],
                    ),
                    claim_a_id=pair[0],
                    claim_b_id=pair[1],
                    contradiction_type=contradiction_type,
                    reason=reason,
                    differing_values=differing_values,
                    source_ids=source_ids,
                )
            )

    return sorted(
        candidates,
        key=lambda item: item.contradiction_id,
    )


def _confidence_level(
    source_count: int,
    independent_source_count: int,
    evidence_count: int,
    provenance_valid: bool,
    contradicted: bool,
) -> tuple[str, list[str]]:
    reasons = [
        f"source_count={source_count}",
        f"independent_source_count={independent_source_count}",
        f"evidence_count={evidence_count}",
        f"provenance_integrity={'VALID' if provenance_valid else 'INVALID'}",
        f"contradiction_state={'CANDIDATE' if contradicted else 'NONE'}",
    ]

    if not provenance_valid or evidence_count == 0:
        return "VERY_LOW", reasons

    if contradicted:
        return "LOW", reasons

    if independent_source_count >= 3 and evidence_count >= 3:
        return "VERY_HIGH", reasons

    if independent_source_count >= 2 and evidence_count >= 2:
        return "HIGH", reasons

    if source_count >= 1 and evidence_count >= 1:
        return "MEDIUM", reasons

    return "LOW", reasons


def assess_project_claims(
    project_root: str,
) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    project = load_project(root)
    source_registry = load_sources(root)
    paths = project_paths(root)

    claims_payload = _knowledge_artifact(root, "claims.json")
    evidence_payload = _knowledge_artifact(root, "evidence.json")
    provenance_payload = _knowledge_artifact(root, "provenance.json")

    claims = claims_payload.get("claims", [])
    evidence = evidence_payload.get("evidence", [])
    provenance = provenance_payload.get("provenance", [])

    if not isinstance(claims, list):
        raise ValueError("INVALID_CLAIMS_ARTIFACT")

    if not claims:
        raise ValueError("NO_CLAIMS_TO_ASSESS")

    evidence_by_id = {
        item["evidence_id"]: item
        for item in evidence
    }

    sources_by_id = {
        item["source_id"]: item
        for item in source_registry["sources"]
    }

    provenance_by_subject: dict[str, list[dict[str, Any]]] = {}

    for record in provenance:
        provenance_by_subject.setdefault(
            record["subject_id"],
            [],
        ).append(record)

    contradictions = _find_contradictions(claims)

    contradicted_claim_ids = {
        item.claim_a_id
        for item in contradictions
    } | {
        item.claim_b_id
        for item in contradictions
    }

    assessments: list[ClaimAssessment] = []
    gaps: list[ResearchGap] = []

    for claim in sorted(
        claims,
        key=lambda item: item["claim_id"],
    ):
        claim_id = str(claim["claim_id"])
        evidence_ids = sorted(set(claim.get("evidence_ids", [])))
        source_ids = sorted(set(claim.get("source_ids", [])))

        linked_provenance = provenance_by_subject.get(claim_id, [])

        provenance_valid = bool(linked_provenance)

        for evidence_id in evidence_ids:
            evidence_record = evidence_by_id.get(evidence_id)

            if evidence_record is None:
                provenance_valid = False
                continue

            if evidence_record.get("source_id") not in source_ids:
                provenance_valid = False

            matching = [
                record
                for record in linked_provenance
                if record.get("evidence_id") == evidence_id
                and record.get("source_id")
                == evidence_record.get("source_id")
            ]

            if not matching:
                provenance_valid = False

        independent_count = _source_independence(
            source_ids,
            sources_by_id,
        )

        contradicted = claim_id in contradicted_claim_ids

        confidence, confidence_reasons = _confidence_level(
            len(source_ids),
            independent_count,
            len(evidence_ids),
            provenance_valid,
            contradicted,
        )

        if contradicted:
            status = "CONTRADICTION_CANDIDATE"
        elif independent_count >= 2:
            status = "MULTI_SOURCE_SUPPORTED"
        elif len(source_ids) == 1 and evidence_ids:
            status = "SINGLE_SOURCE_SUPPORTED"
        elif evidence_ids:
            status = "SUPPORTED_BY_SOURCE_TEXT"
        else:
            status = "INSUFFICIENT_EVIDENCE"

        coverage_state = (
            "BROAD"
            if independent_count >= 3
            else "CORROBORATED"
            if independent_count >= 2
            else "LIMITED"
            if independent_count == 1
            else "MISSING"
        )

        assessments.append(
            ClaimAssessment(
                assessment_id=deterministic_id(
                    "claim_assessment",
                    [
                        claim_id,
                        status,
                        confidence,
                        source_ids,
                        evidence_ids,
                    ],
                ),
                claim_id=claim_id,
                claim_text=str(claim["claim_text"]),
                status=status,
                textual_support=(
                    "PRESENT"
                    if evidence_ids
                    else "MISSING"
                ),
                source_count=len(source_ids),
                independent_source_count=independent_count,
                evidence_count=len(evidence_ids),
                provenance_integrity=(
                    "VALID"
                    if provenance_valid
                    else "INVALID"
                ),
                contradiction_state=(
                    "CANDIDATE"
                    if contradicted
                    else "NONE"
                ),
                coverage_state=coverage_state,
                confidence_level=confidence,
                confidence_reasons=confidence_reasons,
            )
        )

        if not provenance_valid:
            gaps.append(
                ResearchGap(
                    gap_id=deterministic_id(
                        "research_gap",
                        [claim_id, "PROVENANCE_INTEGRITY"],
                    ),
                    gap_type="PROVENANCE_INTEGRITY",
                    subject_id=claim_id,
                    priority="CRITICAL",
                    reason=(
                        "Claim evidence or provenance linkage is incomplete."
                    ),
                    recommended_action=(
                        "Repair evidence and provenance references before use."
                    ),
                )
            )

        if independent_count == 0:
            gaps.append(
                ResearchGap(
                    gap_id=deterministic_id(
                        "research_gap",
                        [claim_id, "NO_INDEPENDENT_SOURCE"],
                    ),
                    gap_type="NO_INDEPENDENT_SOURCE",
                    subject_id=claim_id,
                    priority="CRITICAL",
                    reason="No independent registered source supports the claim.",
                    recommended_action=(
                        "Acquire at least one attributable source."
                    ),
                )
            )

        elif independent_count == 1:
            gaps.append(
                ResearchGap(
                    gap_id=deterministic_id(
                        "research_gap",
                        [claim_id, "SINGLE_SOURCE"],
                    ),
                    gap_type="SINGLE_SOURCE",
                    subject_id=claim_id,
                    priority="HIGH",
                    reason=(
                        "The claim is supported by only one independent source."
                    ),
                    recommended_action=(
                        "Find a second independent source that directly "
                        "addresses the same claim."
                    ),
                )
            )

        if contradicted:
            gaps.append(
                ResearchGap(
                    gap_id=deterministic_id(
                        "research_gap",
                        [claim_id, "CONTRADICTION_REVIEW"],
                    ),
                    gap_type="CONTRADICTION_REVIEW",
                    subject_id=claim_id,
                    priority="CRITICAL",
                    reason=(
                        "A deterministic contradiction candidate involves "
                        "this claim."
                    ),
                    recommended_action=(
                        "Review the cited passages, source dates, editions, "
                        "and contextual scope."
                    ),
                )
            )

    contradiction_count_by_source: dict[str, int] = {}

    for contradiction in contradictions:
        for source_id in contradiction.source_ids:
            contradiction_count_by_source[source_id] = (
                contradiction_count_by_source.get(source_id, 0) + 1
            )

    coverage: list[SourceCoverage] = []

    for source_id in sorted(sources_by_id):
        source_claims = [
            assessment
            for assessment in assessments
            if source_id in next(
                claim["source_ids"]
                for claim in claims
                if claim["claim_id"] == assessment.claim_id
            )
        ]

        source_evidence = [
            item
            for item in evidence
            if item.get("source_id") == source_id
        ]

        multi_source_count = sum(
            item.independent_source_count >= 2
            for item in source_claims
        )

        unique_claim_count = sum(
            item.independent_source_count == 1
            for item in source_claims
        )

        coverage_state = (
            "UNUSED"
            if not source_claims
            else "CONTRADICTORY"
            if contradiction_count_by_source.get(source_id, 0)
            else "CORROBORATIVE"
            if multi_source_count
            else "ISOLATED"
        )

        coverage.append(
            SourceCoverage(
                source_id=source_id,
                claim_count=len(source_claims),
                evidence_count=len(source_evidence),
                unique_claim_count=unique_claim_count,
                multi_source_claim_count=multi_source_count,
                contradiction_count=contradiction_count_by_source.get(
                    source_id,
                    0,
                ),
                coverage_state=coverage_state,
            )
        )

        if not source_claims:
            gaps.append(
                ResearchGap(
                    gap_id=deterministic_id(
                        "research_gap",
                        [source_id, "UNUSED_SOURCE"],
                    ),
                    gap_type="UNUSED_SOURCE",
                    subject_id=source_id,
                    priority="MEDIUM",
                    reason=(
                        "The registered source contributes no extracted claims."
                    ),
                    recommended_action=(
                        "Review ingestion quality or remove the source "
                        "from the active research set."
                    ),
                )
            )

    assessments = sorted(
        assessments,
        key=lambda item: item.claim_id,
    )
    gaps = sorted(
        {
            item.gap_id: item
            for item in gaps
        }.values(),
        key=lambda item: item.gap_id,
    )
    coverage = sorted(
        coverage,
        key=lambda item: item.source_id,
    )

    assessment_run_id = deterministic_id(
        "assessment_run",
        [
            project["project_id"],
            [item.assessment_id for item in assessments],
            [item.contradiction_id for item in contradictions],
            [item.gap_id for item in gaps],
        ],
    )

    common = {
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "project_id": project["project_id"],
        "assessment_run_id": assessment_run_id,
        "created_at": CANONICAL_TIMESTAMP,
    }

    assessments_payload = {
        **common,
        "assessments": [asdict(item) for item in assessments],
    }

    contradictions_payload = {
        **common,
        "contradictions": [
            asdict(item)
            for item in contradictions
        ],
        "limitations": [
            (
                "Contradictions are candidates detected by numeric-pattern "
                "or explicit-negation comparison; semantic adjudication "
                "is not performed."
            )
        ],
    }

    gaps_payload = {
        **common,
        "gaps": [asdict(item) for item in gaps],
    }

    coverage_payload = {
        **common,
        "sources": [asdict(item) for item in coverage],
    }

    result_payload = {
        **common,
        "status": "ASSESSED",
        "assessment_count": len(assessments),
        "contradiction_count": len(contradictions),
        "gap_count": len(gaps),
        "source_coverage_count": len(coverage),
        "high_confidence_count": sum(
            item.confidence_level in {"HIGH", "VERY_HIGH"}
            for item in assessments
        ),
        "low_confidence_count": sum(
            item.confidence_level in {"LOW", "VERY_LOW"}
            for item in assessments
        ),
        "limitations": [
            "No claim is declared historically true.",
            "Confidence is categorical and evidence-derived.",
            "Source independence is based on distinct registered source files.",
            "Contradiction detection is conservative and deterministic.",
        ],
    }

    assessment_root = Path(paths.working_root) / "assessment"
    assessment_root.mkdir(parents=True, exist_ok=True)

    files = {
        "claim-assessments.json": assessments_payload,
        "contradictions.json": contradictions_payload,
        "research-gaps.json": gaps_payload,
        "source-coverage.json": coverage_payload,
        "assessment-result.json": result_payload,
    }

    for filename, payload in files.items():
        _write_json(assessment_root / filename, payload)

    with SQLitePersistenceAdapter(
        SQLiteConnectionConfig(paths.database)
    ) as adapter:
        adapter.initialize()
        transaction = adapter.save_many(
            [
                (
                    "CLAIM_ASSESSMENTS",
                    assessment_run_id,
                    assessments_payload,
                ),
                (
                    "CONTRADICTION_CANDIDATES",
                    assessment_run_id,
                    contradictions_payload,
                ),
                (
                    "RESEARCH_GAPS",
                    assessment_run_id,
                    gaps_payload,
                ),
                (
                    "SOURCE_COVERAGE",
                    assessment_run_id,
                    coverage_payload,
                ),
                (
                    "ASSESSMENT_RESULT",
                    assessment_run_id,
                    result_payload,
                ),
            ]
        )

    if not transaction.committed:
        raise RuntimeError(
            transaction.error_code
            or "ASSESSMENT_PERSISTENCE_FAILED"
        )

    return {
        **result_payload,
        "assessment_root": str(assessment_root),
        "persistence_record_ids": transaction.record_ids,
    }


def _assessment_artifact(
    project_root: Path,
    filename: str,
) -> dict[str, Any]:
    paths = project_paths(project_root)
    path = Path(paths.working_root) / "assessment" / filename
    payload = _read_json(path)

    if payload.get("schema_version") != ASSESSMENT_SCHEMA_VERSION:
        raise ValueError("INVALID_ASSESSMENT_SCHEMA")

    return payload


def assessment_status(project_root: str) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    project = load_project(root)
    paths = project_paths(root)

    result_path = (
        Path(paths.working_root)
        / "assessment"
        / "assessment-result.json"
    )

    if not result_path.is_file():
        return {
            "project_id": project["project_id"],
            "status": "NOT_RUN",
            "result_path": str(result_path),
        }

    payload = _read_json(result_path)

    return {
        "project_id": project["project_id"],
        "status": payload.get("status", "INVALID"),
        "result_path": str(result_path),
        "assessment_run_id": payload.get("assessment_run_id", ""),
        "assessment_count": payload.get("assessment_count", 0),
        "contradiction_count": payload.get("contradiction_count", 0),
        "gap_count": payload.get("gap_count", 0),
        "source_coverage_count": payload.get(
            "source_coverage_count",
            0,
        ),
    }


def list_contradictions(project_root: str) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    payload = _assessment_artifact(
        root,
        "contradictions.json",
    )

    return {
        "project_id": payload["project_id"],
        "assessment_run_id": payload["assessment_run_id"],
        "contradiction_count": len(payload["contradictions"]),
        "contradictions": payload["contradictions"],
    }


def list_gaps(project_root: str) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    payload = _assessment_artifact(
        root,
        "research-gaps.json",
    )

    return {
        "project_id": payload["project_id"],
        "assessment_run_id": payload["assessment_run_id"],
        "gap_count": len(payload["gaps"]),
        "gaps": payload["gaps"],
    }


def verify_assessment(
    project_root: str,
) -> AssessmentVerificationReport:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    project = load_project(root)
    issues: list[AssessmentVerificationIssue] = []

    try:
        assessments_payload = _assessment_artifact(
            root,
            "claim-assessments.json",
        )
        contradictions_payload = _assessment_artifact(
            root,
            "contradictions.json",
        )
        gaps_payload = _assessment_artifact(
            root,
            "research-gaps.json",
        )
        coverage_payload = _assessment_artifact(
            root,
            "source-coverage.json",
        )
        result_payload = _assessment_artifact(
            root,
            "assessment-result.json",
        )
        claims_payload = _knowledge_artifact(
            root,
            "claims.json",
        )
    except (FileNotFoundError, ValueError) as error:
        return AssessmentVerificationReport(
            project_id=project["project_id"],
            status="INVALID",
            assessment_count=0,
            contradiction_count=0,
            gap_count=0,
            source_coverage_count=0,
            issues=[
                AssessmentVerificationIssue(
                    "ASSESSMENT_ARTIFACT_INVALID",
                    detail=str(error),
                )
            ],
        )

    run_ids = {
        payload.get("assessment_run_id")
        for payload in (
            assessments_payload,
            contradictions_payload,
            gaps_payload,
            coverage_payload,
            result_payload,
        )
    }

    if len(run_ids) != 1:
        issues.append(
            AssessmentVerificationIssue(
                "ASSESSMENT_RUN_ID_MISMATCH",
            )
        )

    claims_by_id = {
        item["claim_id"]: item
        for item in claims_payload["claims"]
    }

    assessments = assessments_payload["assessments"]
    contradictions = contradictions_payload["contradictions"]
    gaps = gaps_payload["gaps"]
    coverage = coverage_payload["sources"]

    assessment_by_claim: dict[str, dict[str, Any]] = {}

    for assessment in assessments:
        claim_id = assessment["claim_id"]

        if claim_id in assessment_by_claim:
            issues.append(
                AssessmentVerificationIssue(
                    "DUPLICATE_CLAIM_ASSESSMENT",
                    claim_id,
                )
            )

        assessment_by_claim[claim_id] = assessment

        if claim_id not in claims_by_id:
            issues.append(
                AssessmentVerificationIssue(
                    "ASSESSMENT_CLAIM_NOT_FOUND",
                    claim_id,
                )
            )

        if assessment["evidence_count"] < 0:
            issues.append(
                AssessmentVerificationIssue(
                    "INVALID_EVIDENCE_COUNT",
                    claim_id,
                )
            )

        if (
            assessment["independent_source_count"]
            > assessment["source_count"]
        ):
            issues.append(
                AssessmentVerificationIssue(
                    "INVALID_SOURCE_INDEPENDENCE_COUNT",
                    claim_id,
                )
            )

        if assessment["confidence_level"] not in {
            "VERY_LOW",
            "LOW",
            "MEDIUM",
            "HIGH",
            "VERY_HIGH",
        }:
            issues.append(
                AssessmentVerificationIssue(
                    "INVALID_CONFIDENCE_LEVEL",
                    claim_id,
                )
            )

    if set(assessment_by_claim) != set(claims_by_id):
        issues.append(
            AssessmentVerificationIssue(
                "CLAIM_ASSESSMENT_COVERAGE_MISMATCH",
            )
        )

    contradiction_ids: set[str] = set()

    for contradiction in contradictions:
        contradiction_id = contradiction["contradiction_id"]

        if contradiction_id in contradiction_ids:
            issues.append(
                AssessmentVerificationIssue(
                    "DUPLICATE_CONTRADICTION_ID",
                    contradiction_id,
                )
            )

        contradiction_ids.add(contradiction_id)

        for claim_id in (
            contradiction["claim_a_id"],
            contradiction["claim_b_id"],
        ):
            if claim_id not in claims_by_id:
                issues.append(
                    AssessmentVerificationIssue(
                        "CONTRADICTION_CLAIM_NOT_FOUND",
                        contradiction_id,
                        claim_id,
                    )
                )

            assessment = assessment_by_claim.get(claim_id)

            if (
                assessment
                and assessment["contradiction_state"]
                != "CANDIDATE"
            ):
                issues.append(
                    AssessmentVerificationIssue(
                        "CONTRADICTION_STATE_MISMATCH",
                        claim_id,
                    )
                )

    gap_ids: set[str] = set()

    for gap in gaps:
        gap_id = gap["gap_id"]

        if gap_id in gap_ids:
            issues.append(
                AssessmentVerificationIssue(
                    "DUPLICATE_GAP_ID",
                    gap_id,
                )
            )

        gap_ids.add(gap_id)

        if gap["priority"] not in {
            "LOW",
            "MEDIUM",
            "HIGH",
            "CRITICAL",
        }:
            issues.append(
                AssessmentVerificationIssue(
                    "INVALID_GAP_PRIORITY",
                    gap_id,
                )
            )

    source_ids = {
        item["source_id"]
        for item in load_sources(root)["sources"]
    }
    coverage_ids = {
        item["source_id"]
        for item in coverage
    }

    if source_ids != coverage_ids:
        issues.append(
            AssessmentVerificationIssue(
                "SOURCE_COVERAGE_MISMATCH",
            )
        )

    expected_counts = {
        "assessment_count": len(assessments),
        "contradiction_count": len(contradictions),
        "gap_count": len(gaps),
        "source_coverage_count": len(coverage),
    }

    for key, expected in expected_counts.items():
        if result_payload.get(key) != expected:
            issues.append(
                AssessmentVerificationIssue(
                    "ASSESSMENT_RESULT_COUNT_MISMATCH",
                    key,
                    f"expected={expected}",
                )
            )

    return AssessmentVerificationReport(
        project_id=project["project_id"],
        status="VALID" if not issues else "INVALID",
        assessment_count=len(assessments),
        contradiction_count=len(contradictions),
        gap_count=len(gaps),
        source_coverage_count=len(coverage),
        issues=issues,
    )


__all__ = [
    "ASSESSMENT_SCHEMA_VERSION",
    "AssessmentVerificationIssue",
    "AssessmentVerificationReport",
    "ClaimAssessment",
    "ContradictionCandidate",
    "ResearchGap",
    "SourceCoverage",
    "assess_project_claims",
    "assessment_status",
    "list_contradictions",
    "list_gaps",
    "verify_assessment",
]
