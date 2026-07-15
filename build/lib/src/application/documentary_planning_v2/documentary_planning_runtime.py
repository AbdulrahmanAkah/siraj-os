from src.application.documentary_intelligence import (
    CANONICAL_CREATED_AT,
    canonical_trace,
    deterministic_id,
    stable_unique,
)
from src.application.historical_interpretation.models import HistoricalInterpretationResult
from src.application.historical_timeline.models import HistoricalTimeline
from src.application.reasoning_validation.models import ValidatedReasoningResult
from src.application.relationship_graph.models import RelationshipGraph

from .documentary_planning_architect import DocumentaryPlanningArchitectV2
from .models import DocumentaryChapter, DocumentaryPlan, DocumentaryPlanningPolicy


class DocumentaryPlanningRuntimeV2:
    def build_documentary_plan(
        self, policy, validated_reasoning, timeline, evidence_graph, interpretations
    ):
        if not self._valid_inputs(
            policy, validated_reasoning, timeline, evidence_graph, interpretations
        ):
            raise ValueError("Invalid Documentary Planning v2 inputs")
        event_nodes = {
            node.source_id
            for node in evidence_graph.nodes
            if node.node_type == "EVENT_NODE"
        }
        interpretations_by_position = {
            item.position: item for item in interpretations.records
        }
        chapter_inputs = [
            (entry, interpretations_by_position[position])
            for position, entry in enumerate(timeline.entries)
            if entry.event_id in event_nodes and position in interpretations_by_position
        ]
        if not chapter_inputs:
            raise ValueError("Documentary Planning v2 requires supported chapters")
        chapters = [
            self._build_chapter(policy, entry, interpretation, position, len(chapter_inputs))
            for position, (entry, interpretation) in enumerate(chapter_inputs)
        ]
        dated = [entry.event_date for entry, _ in chapter_inputs if entry.event_date]
        evidence_coverage = stable_unique(
            evidence_id for chapter in chapters for evidence_id in chapter.evidence_ids
        )
        trace = canonical_trace(
            source_ids=(
                source_id
                for chapter in chapters
                for source_id in chapter.trace_metadata["source_ids"]
            ),
            evidence_ids=evidence_coverage,
            claim_ids=(
                claim_id for chapter in chapters for claim_id in chapter.trace_metadata["claim_ids"]
            ),
            event_ids=(chapter.event_ids[0] for chapter in chapters),
            reasoning_ids=(
                reasoning_id
                for chapter in chapters
                for reasoning_id in chapter.trace_metadata["reasoning_ids"]
            ),
        )
        title = chapters[0].title
        scope = "|".join(stable_unique(entry.event_type for entry, _ in chapter_inputs))
        time_range = (min(dated), max(dated)) if dated else (None, None)
        material = {
            "policy_id": policy.policy_id,
            "validated_reasoning_result_id": validated_reasoning.result_id,
            "title": title,
            "subject": title,
            "scope": scope,
            "time_range": time_range,
            "chapter_ids": [chapter.chapter_id for chapter in chapters],
            "evidence_coverage": evidence_coverage,
            "trace": trace,
        }
        plan = DocumentaryPlan(
            plan_id=deterministic_id("documentary_plan_v2", material),
            title=title,
            subject=title,
            scope=scope,
            time_range=time_range,
            major_chapters=chapters,
            chapter_ordering=[chapter.chapter_id for chapter in chapters],
            evidence_coverage=evidence_coverage,
            created_at=CANONICAL_CREATED_AT,
            position=0,
            trace_metadata=trace,
            validation_state="VALID",
        )
        if not self.validate_documentary_plan(
            policy, validated_reasoning, timeline, evidence_graph, interpretations, plan
        ):
            raise ValueError("Invalid Documentary Planning v2 result")
        return plan

    def _build_chapter(self, policy, entry, interpretation, position, count):
        role = self._role(position, count)
        trace = canonical_trace(
            source_ids=interpretation.source_reference_ids,
            evidence_ids=interpretation.evidence_ids,
            claim_ids=entry.source_claim_ids,
            event_ids=[entry.event_id],
            reasoning_ids=interpretation.reasoning_chain_ids,
        )
        material = {
            "title": entry.event_title,
            "role": role,
            "event_id": entry.event_id,
            "interpretation_id": interpretation.interpretation_id,
            "evidence_ids": interpretation.evidence_ids,
            "position": position,
            "trace": trace,
        }
        return DocumentaryChapter(
            chapter_id=deterministic_id("documentary_chapter_v2", material),
            title=entry.event_title,
            chapter_role=role,
            event_ids=[entry.event_id],
            interpretation_ids=[interpretation.interpretation_id],
            evidence_ids=stable_unique(interpretation.evidence_ids),
            created_at=CANONICAL_CREATED_AT,
            position=position,
            trace_metadata=trace,
        )

    @staticmethod
    def _role(position, count):
        if position == 0:
            return "OPENING"
        if position == count - 1:
            return "OUTCOME"
        if position == 1:
            return "CONTEXT"
        if position == count // 2:
            return "TURNING_POINT"
        return "DEVELOPMENT"

    def validate_documentary_plan(
        self, policy, validated_reasoning, timeline, evidence_graph, interpretations, plan
    ):
        if not self._valid_inputs(
            policy, validated_reasoning, timeline, evidence_graph, interpretations
        ) or not isinstance(plan, DocumentaryPlan):
            return False
        if plan.validation_state != "VALID" or plan.created_at != CANONICAL_CREATED_AT:
            return False
        if not plan.title or plan.subject != plan.title or not plan.scope:
            return False
        if plan.chapter_ordering != [chapter.chapter_id for chapter in plan.major_chapters]:
            return False
        if [chapter.position for chapter in plan.major_chapters] != list(range(len(plan.major_chapters))):
            return False
        chapter_ids = [chapter.chapter_id for chapter in plan.major_chapters]
        if len(chapter_ids) != len(set(chapter_ids)):
            return False
        valid_events = {entry.event_id for entry in timeline.entries}
        valid_interpretations = {item.interpretation_id for item in interpretations.records}
        if any(
            chapter.created_at != CANONICAL_CREATED_AT
            or chapter.chapter_role not in policy.allowed_chapter_roles
            or len(chapter.event_ids) != 1
            or chapter.event_ids[0] not in valid_events
            or len(chapter.interpretation_ids) != 1
            or chapter.interpretation_ids[0] not in valid_interpretations
            or not chapter.evidence_ids
            for chapter in plan.major_chapters
        ):
            return False
        coverage = stable_unique(
            evidence_id for chapter in plan.major_chapters for evidence_id in chapter.evidence_ids
        )
        return plan.evidence_coverage == coverage and bool(plan.plan_id)

    @staticmethod
    def _valid_inputs(policy, validated_reasoning, timeline, graph, interpretations):
        return (
            isinstance(policy, DocumentaryPlanningPolicy)
            and DocumentaryPlanningArchitectV2().validate_policy(policy)
            and isinstance(validated_reasoning, ValidatedReasoningResult)
            and validated_reasoning.is_valid
            and validated_reasoning.validation_state == "VALID"
            and isinstance(timeline, HistoricalTimeline)
            and timeline.entry_count == len(timeline.entries)
            and isinstance(graph, RelationshipGraph)
            and graph.node_count == len(graph.nodes)
            and graph.edge_count == len(graph.edges)
            and isinstance(interpretations, HistoricalInterpretationResult)
            and interpretations.record_count == len(interpretations.records)
            and validated_reasoning.interpretation_result_id == interpretations.result_id
        )


__all__ = ["DocumentaryPlanningRuntimeV2"]
