from hashlib import sha256
import json

from src.application.evidence_resolution.models import EvidenceResolutionResult
from src.application.historical_timeline.models import HistoricalTimeline
from src.application.knowledge_confidence.models import KnowledgeConfidenceResult
from src.application.relationship_graph.models import RelationshipGraph

from .models import (
    HistoricalReasoningPlan,
    ReasoningCandidate,
    ReasoningChain,
    ReasoningResult,
)


class HistoricalReasoningRuntime:
    def build_reasoning_result(self, plan, timeline, graph, evidence, confidence):
        self.validate_runtime_inputs_or_raise(plan, timeline, graph, evidence, confidence)
        candidates = self.generate_candidates(timeline, graph, evidence, confidence)
        chains = [
            ReasoningChain(
                chain_id=self._id("reasoning_chain", [candidate.candidate_id]),
                candidates=[candidate],
                source_event_ids=[candidate.event_id],
                evidence_ids=list(candidate.evidence_ids),
                position=candidate.position,
            )
            for candidate in candidates
        ]
        result = ReasoningResult(
            result_id=self._id(
                "reasoning_result",
                [plan.plan_id, *[chain.chain_id for chain in chains], "VALID"],
            ),
            plan_id=plan.plan_id,
            chains=chains,
            chain_count=len(chains),
            validation_state="VALID",
        )
        if not self.validate_reasoning(plan, timeline, graph, evidence, confidence, result):
            raise ValueError("Invalid historical reasoning result")
        return result

    def generate_candidates(self, timeline, graph, evidence, confidence):
        event_nodes = {
            node.source_id: node.node_id
            for node in graph.nodes
            if node.node_type == "EVENT_NODE"
        }
        confidence_by_subject = {
            record.subject_id: record.confidence_id
            for record in confidence.assessment.records
        }
        candidates = []
        for position, entry in enumerate(timeline.entries):
            graph_node_id = event_nodes.get(entry.event_id)
            if graph_node_id is None:
                continue
            source_ids = {
                entry.event_id,
                entry.entry_id,
                *entry.source_claim_ids,
                *entry.source_entity_ids,
            }
            evidence_ids = sorted(
                item.resolved_evidence_id
                for item in evidence.resolved_evidence
                if any(reference.source_id in source_ids for reference in item.references)
            )
            if not evidence_ids:
                continue
            confidence_ids = sorted(
                confidence_by_subject[evidence_id]
                for evidence_id in evidence_ids
                if evidence_id in confidence_by_subject
            )
            material = {
                "event_id": entry.event_id,
                "statement": entry.event_title,
                "graph_node_id": graph_node_id,
                "evidence_ids": evidence_ids,
                "confidence_record_ids": confidence_ids,
                "source_claim_ids": sorted(entry.source_claim_ids),
                "source_entity_ids": sorted(entry.source_entity_ids),
                "position": position,
            }
            candidates.append(
                ReasoningCandidate(
                    candidate_id=self._id("reasoning_candidate", material),
                    event_id=entry.event_id,
                    statement=entry.event_title,
                    graph_node_id=graph_node_id,
                    evidence_ids=evidence_ids,
                    confidence_record_ids=confidence_ids,
                    source_claim_ids=sorted(entry.source_claim_ids),
                    source_entity_ids=sorted(entry.source_entity_ids),
                    position=position,
                )
            )
        return candidates

    def validate_reasoning(self, plan, timeline, graph, evidence, confidence, result):
        if not self._valid_inputs(plan, timeline, graph, evidence, confidence):
            return False
        if not isinstance(result, ReasoningResult):
            return False
        if result.plan_id != plan.plan_id or result.validation_state != "VALID":
            return False
        if result.chain_count != len(result.chains):
            return False
        chain_ids = [chain.chain_id for chain in result.chains]
        if len(chain_ids) != len(set(chain_ids)):
            return False
        if [chain.position for chain in result.chains] != sorted(
            chain.position for chain in result.chains
        ):
            return False
        valid_nodes = {node.node_id for node in graph.nodes}
        valid_evidence = {item.resolved_evidence_id for item in evidence.resolved_evidence}
        for chain in result.chains:
            if len(chain.candidates) != 1 or not chain.evidence_ids:
                return False
            candidate = chain.candidates[0]
            if candidate.graph_node_id not in valid_nodes:
                return False
            if not candidate.evidence_ids or not set(candidate.evidence_ids) <= valid_evidence:
                return False
            if chain.evidence_ids != candidate.evidence_ids:
                return False
            if chain.source_event_ids != [candidate.event_id]:
                return False
        return result == self.build_result_without_validation(plan, result.chains)

    def build_result_without_validation(self, plan, chains):
        return ReasoningResult(
            result_id=self._id(
                "reasoning_result",
                [plan.plan_id, *[chain.chain_id for chain in chains], "VALID"],
            ),
            plan_id=plan.plan_id,
            chains=list(chains),
            chain_count=len(chains),
            validation_state="VALID",
        )

    def validate_runtime_inputs_or_raise(self, *inputs):
        if not self._valid_inputs(*inputs):
            raise ValueError("Invalid historical reasoning inputs")

    @staticmethod
    def _valid_inputs(plan, timeline, graph, evidence, confidence):
        return (
            isinstance(plan, HistoricalReasoningPlan)
            and bool(plan.plan_id)
            and isinstance(timeline, HistoricalTimeline)
            and timeline.entry_count == len(timeline.entries)
            and isinstance(graph, RelationshipGraph)
            and graph.node_count == len(graph.nodes)
            and graph.edge_count == len(graph.edges)
            and isinstance(evidence, EvidenceResolutionResult)
            and evidence.evidence_count == len(evidence.resolved_evidence)
            and isinstance(confidence, KnowledgeConfidenceResult)
            and confidence.record_count == len(confidence.assessment.records)
        )

    @staticmethod
    def _id(prefix, material):
        return prefix + "_" + sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]


__all__ = ["HistoricalReasoningRuntime"]
