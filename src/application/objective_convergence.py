"""Objective convergence law for semantic and deterministic repair workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from src.application.alignment_audit_schema_v1 import (
    AlignmentAudit,
    DETERMINISTIC_CATEGORIES,
)
from src.application.artifact_provenance_v1 import canonical_sha256


SCHEMA_VERSION = "siraj-objective-convergence-v1"


class ObjectiveConvergenceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ObjectiveVector:
    blocking_finding_count: int
    finding_ids: tuple[str, ...]
    finding_categories: tuple[str, ...]
    affected_shot_ids: tuple[str, ...]
    timeline_mismatch_count: int
    duplicate_count: int
    semantic_conflict_count: int
    structural_fingerprint: str

    @property
    def metric_tuple(self) -> tuple[int, ...]:
        return (
            self.timeline_mismatch_count,
            self.duplicate_count,
            self.blocking_finding_count,
            self.semantic_conflict_count,
            len(self.affected_shot_ids),
        )

    @property
    def normalized_state_sha256(self) -> str:
        return canonical_sha256(self.as_dict())

    @property
    def failure_class_sha256(self) -> str:
        return canonical_sha256(
            {
                "categories": self.finding_categories,
                "affected_shot_ids": self.affected_shot_ids,
                "metric_tuple": self.metric_tuple,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ConvergenceDecision:
    action: str
    reason: str
    objective_improved: bool
    provider_call_allowed: bool
    current_state_sha256: str


def objective_from_alignment_audit(
    audit: AlignmentAudit,
    *,
    structural_fingerprint: str,
) -> ObjectiveVector:
    if not structural_fingerprint or len(structural_fingerprint) < 16:
        raise ObjectiveConvergenceError("OBJECTIVE_STRUCTURAL_FINGERPRINT_REQUIRED")
    blocking = audit.blocking_findings
    categories = tuple(sorted(finding.category for finding in blocking))
    deterministic = sum(
        1 for finding in blocking if finding.category in DETERMINISTIC_CATEGORIES
    )
    duplicates = sum(
        1
        for finding in blocking
        if "DUPLICATE" in finding.category or "REPETITION" in finding.category
    )
    semantic = len(blocking) - deterministic
    return ObjectiveVector(
        blocking_finding_count=len(blocking),
        finding_ids=tuple(sorted(finding.finding_id for finding in blocking)),
        finding_categories=categories,
        affected_shot_ids=tuple(
            sorted(
                {
                    shot_id
                    for finding in blocking
                    for shot_id in finding.affected_shot_ids
                }
            )
        ),
        timeline_mismatch_count=deterministic,
        duplicate_count=duplicates,
        semantic_conflict_count=semantic,
        structural_fingerprint=structural_fingerprint,
    )


def failure_mode(vector: ObjectiveVector) -> str:
    if vector.timeline_mismatch_count > 0:
        return "DETERMINISTIC_FAILURE"
    if vector.blocking_finding_count > 0:
        return "SEMANTIC_FAILURE"
    return "PASS"


def _strictly_dominates(candidate: ObjectiveVector, previous: ObjectiveVector) -> bool:
    candidate_metrics = candidate.metric_tuple
    previous_metrics = previous.metric_tuple
    return all(
        candidate_value <= previous_value
        for candidate_value, previous_value in zip(candidate_metrics, previous_metrics)
    ) and any(
        candidate_value < previous_value
        for candidate_value, previous_value in zip(candidate_metrics, previous_metrics)
    )


def evaluate_candidate(
    history: Sequence[ObjectiveVector],
    candidate: ObjectiveVector,
) -> ConvergenceDecision:
    if not history:
        mode = failure_mode(candidate)
        return ConvergenceDecision(
            action=(
                "PASS" if mode == "PASS"
                else "LOCAL_REPAIR_OR_STOP" if mode == "DETERMINISTIC_FAILURE"
                else "PROPOSE_ONCE"
            ),
            reason="INITIAL_OBJECTIVE_STATE",
            objective_improved=False,
            provider_call_allowed=mode == "SEMANTIC_FAILURE",
            current_state_sha256=candidate.normalized_state_sha256,
        )

    previous = history[-1]
    if candidate.structural_fingerprint != previous.structural_fingerprint:
        return ConvergenceDecision(
            action="STOP_HUMAN_REVIEW",
            reason="STRUCTURAL_AUTHORITY_CHANGED",
            objective_improved=False,
            provider_call_allowed=False,
            current_state_sha256=candidate.normalized_state_sha256,
        )
    if failure_mode(candidate) == "DETERMINISTIC_FAILURE":
        return ConvergenceDecision(
            action="LOCAL_REPAIR_OR_STOP",
            reason="DETERMINISTIC_FAILURE_ZERO_LUNA_CALLS",
            objective_improved=False,
            provider_call_allowed=False,
            current_state_sha256=candidate.normalized_state_sha256,
        )
    if failure_mode(candidate) == "PASS":
        return ConvergenceDecision(
            action="PASS",
            reason="NO_BLOCKING_FINDINGS",
            objective_improved=True,
            provider_call_allowed=False,
            current_state_sha256=candidate.normalized_state_sha256,
        )
    prior_hashes = [vector.normalized_state_sha256 for vector in history]
    if candidate.normalized_state_sha256 in prior_hashes:
        distance = len(prior_hashes) - prior_hashes.index(candidate.normalized_state_sha256)
        return ConvergenceDecision(
            action="STOP_HUMAN_REVIEW",
            reason=f"OSCILLATION_CYCLE_LENGTH_{distance}",
            objective_improved=False,
            provider_call_allowed=False,
            current_state_sha256=candidate.normalized_state_sha256,
        )
    if candidate.failure_class_sha256 == previous.failure_class_sha256:
        return ConvergenceDecision(
            action="STOP_HUMAN_REVIEW",
            reason="SAME_FAILURE_CLASS_NO_OBJECTIVE_PROGRESS",
            objective_improved=False,
            provider_call_allowed=False,
            current_state_sha256=candidate.normalized_state_sha256,
        )
    if not _strictly_dominates(candidate, previous):
        return ConvergenceDecision(
            action="STOP_HUMAN_REVIEW",
            reason="NO_STRICT_OBJECTIVE_IMPROVEMENT",
            objective_improved=False,
            provider_call_allowed=False,
            current_state_sha256=candidate.normalized_state_sha256,
        )
    return ConvergenceDecision(
        action="CONTINUE_SEMANTIC_PROPOSAL",
        reason="OBJECTIVE_VECTOR_STRICTLY_IMPROVED",
        objective_improved=True,
        provider_call_allowed=True,
        current_state_sha256=candidate.normalized_state_sha256,
    )


def objective_from_duplicate_problems(
    problems: Sequence[Mapping[str, Any]],
    *,
    structural_fingerprint: str,
) -> ObjectiveVector:
    categories = tuple(sorted(str(problem.get("type") or "UNKNOWN") for problem in problems))
    affected = tuple(
        sorted(
            {
                str(problem[key])
                for problem in problems
                for key in ("a", "b", "shot_id")
                if problem.get(key)
            }
        )
    )
    ids = tuple(
        canonical_sha256(problem)[:16]
        for problem in sorted(problems, key=canonical_sha256)
    )
    return ObjectiveVector(
        blocking_finding_count=len(problems),
        finding_ids=ids,
        finding_categories=categories,
        affected_shot_ids=affected,
        timeline_mismatch_count=0,
        duplicate_count=len(problems),
        semantic_conflict_count=0,
        structural_fingerprint=structural_fingerprint,
    )
