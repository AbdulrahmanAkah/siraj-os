from hashlib import sha256
import json

from src.application.historical_reasoning_foundation.models import ReasoningResult
from src.application.historical_timeline.models import HistoricalTimeline

from .models import (
    NarrativeReasoningPlan,
    NarrativeReasoningRecord,
    NarrativeReasoningResult,
)


class NarrativeReasoningRuntime:
    def build_narrative_result(self, plan, timeline, reasoning):
        if not self._valid_inputs(plan, timeline, reasoning):
            raise ValueError("Invalid narrative reasoning inputs")
        chains_by_event = {
            event_id: chain
            for chain in reasoning.chains
            for event_id in chain.source_event_ids
        }
        entries = [entry for entry in timeline.entries if entry.event_id in chains_by_event]
        records = []
        for position, entry in enumerate(entries):
            chain = chains_by_event[entry.event_id]
            role = self._role(position, len(entries))
            material = [
                entry.event_id,
                role,
                chain.chain_id,
                chain.evidence_ids,
                position,
            ]
            records.append(
                NarrativeReasoningRecord(
                    record_id=self._id("narrative_reasoning_record", material),
                    event_id=entry.event_id,
                    role=role,
                    reasoning_chain_ids=[chain.chain_id],
                    evidence_ids=list(chain.evidence_ids),
                    position=position,
                )
            )
        result = NarrativeReasoningResult(
            result_id=self._id(
                "narrative_reasoning_result",
                [plan.plan_id, *[item.record_id for item in records], "VALID"],
            ),
            plan_id=plan.plan_id,
            records=records,
            record_count=len(records),
            validation_state="VALID",
        )
        if not self.validate_narrative(plan, timeline, reasoning, result):
            raise ValueError("Invalid narrative reasoning result")
        return result

    def validate_narrative(self, plan, timeline, reasoning, result):
        if not self._valid_inputs(plan, timeline, reasoning):
            return False
        if not isinstance(result, NarrativeReasoningResult):
            return False
        if result.plan_id != plan.plan_id or result.validation_state != "VALID":
            return False
        if result.record_count != len(result.records):
            return False
        if [item.position for item in result.records] != list(range(len(result.records))):
            return False
        record_ids = [item.record_id for item in result.records]
        if len(record_ids) != len(set(record_ids)):
            return False
        valid_chains = {chain.chain_id for chain in reasoning.chains}
        valid_events = {entry.event_id for entry in timeline.entries}
        return all(
            item.role in plan.narrative_roles
            and item.event_id in valid_events
            and item.reasoning_chain_ids
            and set(item.reasoning_chain_ids) <= valid_chains
            and item.evidence_ids
            for item in result.records
        )

    @staticmethod
    def _role(position, count):
        if position == 0:
            return "BEGINNING"
        if position == count - 1:
            return "OUTCOME"
        if position == count // 2:
            return "TURNING_POINT"
        return "DEVELOPMENT"

    @staticmethod
    def _valid_inputs(plan, timeline, reasoning):
        return (
            isinstance(plan, NarrativeReasoningPlan)
            and bool(plan.plan_id)
            and isinstance(timeline, HistoricalTimeline)
            and timeline.entry_count == len(timeline.entries)
            and isinstance(reasoning, ReasoningResult)
            and reasoning.chain_count == len(reasoning.chains)
        )

    @staticmethod
    def _id(prefix, material):
        return prefix + "_" + sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]


__all__ = ["NarrativeReasoningRuntime"]
