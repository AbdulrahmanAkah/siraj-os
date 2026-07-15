from hashlib import sha256
import json

from src.application.causal_reasoning.models import CausalReasoningResult
from src.application.evidence_resolution.models import EvidenceResolutionResult
from src.application.historical_reasoning_foundation.models import ReasoningResult
from src.application.narrative_reasoning.models import NarrativeReasoningResult
from src.application.temporal_reasoning.models import TemporalReasoningResult

from .models import (
    HistoricalInterpretationPlan,
    HistoricalInterpretationResult,
    InterpretationRecord,
)


class HistoricalInterpretationRuntime:
    def build_interpretation_result(
        self,
        plan,
        reasoning,
        causal,
        temporal,
        narrative,
        evidence,
    ):
        if not self._valid_inputs(plan, reasoning, causal, temporal, narrative, evidence):
            raise ValueError("Invalid historical interpretation inputs")
        chain_by_id = {chain.chain_id: chain for chain in reasoning.chains}
        evidence_by_id = {
            item.resolved_evidence_id: item for item in evidence.resolved_evidence
        }
        records = []
        for narrative_record in sorted(narrative.records, key=lambda item: item.position):
            chain_ids = sorted(narrative_record.reasoning_chain_ids)
            chains = [chain_by_id[chain_id] for chain_id in chain_ids]
            evidence_ids = sorted(
                {evidence_id for chain in chains for evidence_id in chain.evidence_ids}
            )
            source_reference_ids = sorted(
                {
                    reference.reference_id
                    for evidence_id in evidence_ids
                    for reference in evidence_by_id[evidence_id].references
                }
            )
            event_ids = {
                event_id for chain in chains for event_id in chain.source_event_ids
            }
            statements = [
                candidate.statement for chain in chains for candidate in chain.candidates
            ]
            causal_ids = sorted(
                relation.relation_id
                for relation in causal.relations
                if relation.cause_text in statements or relation.effect_text in statements
            )
            temporal_ids = sorted(
                relation.relation_id
                for relation in temporal.relations
                if relation.source_event_id in event_ids
                or relation.target_event_id in event_ids
            )
            interpretation_text = "; ".join(statements)
            material = {
                "interpretation_text": interpretation_text,
                "reasoning_chain_ids": chain_ids,
                "narrative_record_id": narrative_record.record_id,
                "causal_relation_ids": causal_ids,
                "temporal_relation_ids": temporal_ids,
                "evidence_ids": evidence_ids,
                "source_reference_ids": source_reference_ids,
                "position": narrative_record.position,
            }
            records.append(
                InterpretationRecord(
                    interpretation_id=self._id("interpretation_record", material),
                    interpretation_text=interpretation_text,
                    reasoning_chain_ids=chain_ids,
                    narrative_record_ids=[narrative_record.record_id],
                    causal_relation_ids=causal_ids,
                    temporal_relation_ids=temporal_ids,
                    evidence_ids=evidence_ids,
                    source_reference_ids=source_reference_ids,
                    position=narrative_record.position,
                )
            )
        result = HistoricalInterpretationResult(
            result_id=self._id(
                "historical_interpretation_result",
                [plan.plan_id, *[item.interpretation_id for item in records], "VALID"],
            ),
            plan_id=plan.plan_id,
            records=records,
            record_count=len(records),
            validation_state="VALID",
        )
        if not self.validate_interpretations(
            plan, reasoning, causal, temporal, narrative, evidence, result
        ):
            raise ValueError("Invalid historical interpretation result")
        return result

    def validate_interpretations(
        self, plan, reasoning, causal, temporal, narrative, evidence, result
    ):
        if not self._valid_inputs(plan, reasoning, causal, temporal, narrative, evidence):
            return False
        if not isinstance(result, HistoricalInterpretationResult):
            return False
        if result.plan_id != plan.plan_id or result.validation_state != "VALID":
            return False
        if result.record_count != len(result.records):
            return False
        if [item.position for item in result.records] != list(range(len(result.records))):
            return False
        record_ids = [item.interpretation_id for item in result.records]
        if len(record_ids) != len(set(record_ids)):
            return False
        valid_chains = {chain.chain_id for chain in reasoning.chains}
        valid_narrative = {item.record_id for item in narrative.records}
        valid_evidence = {item.resolved_evidence_id for item in evidence.resolved_evidence}
        valid_references = {
            reference.reference_id
            for item in evidence.resolved_evidence
            for reference in item.references
        }
        return all(
            bool(item.interpretation_text)
            and bool(item.reasoning_chain_ids)
            and set(item.reasoning_chain_ids) <= valid_chains
            and bool(item.narrative_record_ids)
            and set(item.narrative_record_ids) <= valid_narrative
            and bool(item.evidence_ids)
            and set(item.evidence_ids) <= valid_evidence
            and bool(item.source_reference_ids)
            and set(item.source_reference_ids) <= valid_references
            for item in result.records
        )

    @staticmethod
    def _valid_inputs(plan, reasoning, causal, temporal, narrative, evidence):
        return (
            isinstance(plan, HistoricalInterpretationPlan)
            and bool(plan.plan_id)
            and isinstance(reasoning, ReasoningResult)
            and reasoning.chain_count == len(reasoning.chains)
            and isinstance(causal, CausalReasoningResult)
            and causal.relation_count == len(causal.relations)
            and isinstance(temporal, TemporalReasoningResult)
            and temporal.relation_count == len(temporal.relations)
            and isinstance(narrative, NarrativeReasoningResult)
            and narrative.record_count == len(narrative.records)
            and isinstance(evidence, EvidenceResolutionResult)
            and evidence.evidence_count == len(evidence.resolved_evidence)
        )

    @staticmethod
    def _id(prefix, material):
        return prefix + "_" + sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]


__all__ = ["HistoricalInterpretationRuntime"]
