from hashlib import sha256
import json

from src.application.contradiction_detection.models import ContradictionResult
from src.application.evidence_resolution.models import EvidenceResolutionResult
from src.application.historical_interpretation.models import HistoricalInterpretationResult
from src.application.historical_reasoning_foundation.models import ReasoningResult
from src.application.historical_timeline.models import HistoricalTimeline
from src.application.relationship_graph.models import RelationshipGraph

from .models import ReasoningValidationPlan, ValidatedReasoningResult, ValidationCheck


class ReasoningValidationRuntime:
    def build_validated_reasoning_result(
        self, plan, reasoning, interpretation, timeline, graph, evidence, contradictions
    ):
        inputs = (plan, reasoning, interpretation, timeline, graph, evidence, contradictions)
        if not self._valid_inputs(*inputs):
            raise ValueError("Invalid reasoning validation inputs")
        checks = self.run_checks(*inputs)
        is_valid = all(check.passed for check in checks)
        state = "VALID" if is_valid else "INVALID"
        result = ValidatedReasoningResult(
            result_id=self._id(
                "validated_reasoning_result",
                [plan.plan_id, reasoning.result_id, interpretation.result_id,
                 *[check.check_id for check in checks], state],
            ),
            plan_id=plan.plan_id,
            reasoning_result_id=reasoning.result_id,
            interpretation_result_id=interpretation.result_id,
            is_valid=is_valid,
            checks=checks,
            check_count=len(checks),
            validation_state=state,
        )
        if not self.validate_result(plan, result):
            raise ValueError("Invalid validated reasoning result")
        return result

    def run_checks(
        self, plan, reasoning, interpretation, timeline, graph, evidence, contradictions
    ):
        evaluators = {
            "EVIDENCE_COMPLETENESS": lambda: self._evidence_completeness(
                reasoning, interpretation
            ),
            "REFERENCE_INTEGRITY": lambda: self._reference_integrity(
                reasoning, interpretation, evidence
            ),
            "TIMELINE_CONSISTENCY": lambda: self._timeline_consistency(timeline),
            "GRAPH_CONSISTENCY": lambda: self._graph_consistency(reasoning, graph),
            "CONTRADICTION_CONFLICTS": lambda: self._contradiction_conflicts(
                reasoning, contradictions
            ),
        }
        checks = []
        for position, check_type in enumerate(plan.required_checks):
            passed, errors, references = evaluators[check_type]()
            material = [check_type, passed, errors, references, position]
            checks.append(
                ValidationCheck(
                    check_id=self._id("reasoning_validation_check", material),
                    check_type=check_type,
                    passed=passed,
                    error_codes=errors,
                    reference_ids=references,
                    position=position,
                )
            )
        return checks

    @staticmethod
    def _evidence_completeness(reasoning, interpretation):
        candidates = [
            candidate for chain in reasoning.chains for candidate in chain.candidates
        ]
        missing = sorted(
            [candidate.candidate_id for candidate in candidates if not candidate.evidence_ids]
            + [item.interpretation_id for item in interpretation.records
               if not item.evidence_ids or not item.source_reference_ids]
        )
        inspected = sorted(
            [candidate.candidate_id for candidate in candidates]
            + [item.interpretation_id for item in interpretation.records]
        )
        return not missing, ([] if not missing else ["MISSING_EVIDENCE"]), inspected

    @staticmethod
    def _reference_integrity(reasoning, interpretation, evidence):
        valid_evidence = {item.resolved_evidence_id for item in evidence.resolved_evidence}
        valid_references = {
            reference.reference_id
            for item in evidence.resolved_evidence for reference in item.references
        }
        valid_chains = {chain.chain_id for chain in reasoning.chains}
        invalid = {
            evidence_id
            for chain in reasoning.chains for candidate in chain.candidates
            for evidence_id in candidate.evidence_ids if evidence_id not in valid_evidence
        }
        for item in interpretation.records:
            invalid.update(x for x in item.evidence_ids if x not in valid_evidence)
            invalid.update(x for x in item.source_reference_ids if x not in valid_references)
            invalid.update(x for x in item.reasoning_chain_ids if x not in valid_chains)
        errors = [] if not invalid else ["BROKEN_REFERENCE"]
        return not invalid, errors, sorted(valid_chains | valid_evidence | valid_references)

    @staticmethod
    def _timeline_consistency(timeline):
        event_ids = [entry.event_id for entry in timeline.entries]
        expected = sorted(
            timeline.entries,
            key=lambda item: (item.event_date is None, item.event_date or "", item.event_id),
        )
        errors = []
        if len(event_ids) != len(set(event_ids)):
            errors.append("DUPLICATE_TIMELINE_EVENT")
        if timeline.entries != expected:
            errors.append("INVALID_TIMELINE_ORDER")
        return not errors, errors, sorted(event_ids)

    @staticmethod
    def _graph_consistency(reasoning, graph):
        node_ids = {node.node_id for node in graph.nodes}
        broken_edges = sorted(
            edge.edge_id for edge in graph.edges
            if edge.source_node_id not in node_ids or edge.target_node_id not in node_ids
        )
        missing_nodes = sorted(
            candidate.graph_node_id
            for chain in reasoning.chains for candidate in chain.candidates
            if candidate.graph_node_id not in node_ids
        )
        errors = []
        if broken_edges:
            errors.append("BROKEN_GRAPH_EDGE")
        if missing_nodes:
            errors.append("MISSING_REASONING_GRAPH_NODE")
        references = sorted(node_ids | set(broken_edges) | set(missing_nodes))
        return not errors, errors, references

    @staticmethod
    def _contradiction_conflicts(reasoning, contradictions):
        claim_ids = {
            claim_id for chain in reasoning.chains for candidate in chain.candidates
            for claim_id in candidate.source_claim_ids
        }
        conflicts = sorted(
            record.contradiction_id for record in contradictions.contradictions
            if claim_ids.intersection(record.claim_ids)
        )
        errors = [] if not conflicts else ["CONTRADICTION_CONFLICT"]
        return not conflicts, errors, conflicts

    @staticmethod
    def validate_result(plan, result):
        if not isinstance(plan, ReasoningValidationPlan):
            return False
        if not isinstance(result, ValidatedReasoningResult):
            return False
        if result.plan_id != plan.plan_id or result.check_count != len(result.checks):
            return False
        if [check.position for check in result.checks] != list(range(len(result.checks))):
            return False
        if [check.check_type for check in result.checks] != plan.required_checks:
            return False
        if len({check.check_id for check in result.checks}) != len(result.checks):
            return False
        expected = all(check.passed for check in result.checks)
        return (
            result.is_valid == expected
            and result.validation_state == ("VALID" if expected else "INVALID")
            and all(check.passed == (not check.error_codes) for check in result.checks)
        )

    @staticmethod
    def _valid_inputs(plan, reasoning, interpretation, timeline, graph, evidence, contradictions):
        return (
            isinstance(plan, ReasoningValidationPlan) and bool(plan.plan_id)
            and isinstance(reasoning, ReasoningResult)
            and reasoning.chain_count == len(reasoning.chains)
            and isinstance(interpretation, HistoricalInterpretationResult)
            and interpretation.record_count == len(interpretation.records)
            and isinstance(timeline, HistoricalTimeline)
            and timeline.entry_count == len(timeline.entries)
            and isinstance(graph, RelationshipGraph)
            and graph.node_count == len(graph.nodes) and graph.edge_count == len(graph.edges)
            and isinstance(evidence, EvidenceResolutionResult)
            and evidence.evidence_count == len(evidence.resolved_evidence)
            and isinstance(contradictions, ContradictionResult)
            and contradictions.contradiction_count == len(contradictions.contradictions)
        )

    @staticmethod
    def _id(prefix, material):
        return prefix + "_" + sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]


__all__ = ["ReasoningValidationRuntime"]
