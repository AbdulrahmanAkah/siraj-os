from copy import deepcopy

import pytest

from src.application.documentary_intelligence import CANONICAL_CREATED_AT
from src.application.documentary_planning_v2 import (
    DocumentaryPlanningArchitectV2,
    DocumentaryPlanningRuntimeV2,
)
from src.application.historical_interpretation.models import (
    HistoricalInterpretationResult,
    InterpretationRecord,
)
from src.application.historical_timeline.models import HistoricalTimeline, TimelineEntry
from src.application.reasoning_validation.models import ValidatedReasoningResult
from src.application.relationship_graph.models import GraphNode, RelationshipGraph


def _inputs():
    interpretations = HistoricalInterpretationResult(
        result_id="interpretations",
        plan_id="interpretation-policy",
        records=[
            InterpretationRecord(
                "interpretation-a", "Opening fact", ["chain-a"], ["narrative-a"],
                evidence_ids=["evidence-a"], source_reference_ids=["source-a"], position=0,
            ),
            InterpretationRecord(
                "interpretation-b", "Outcome fact", ["chain-b"], ["narrative-b"],
                evidence_ids=["evidence-b"], source_reference_ids=["source-b"], position=1,
            ),
        ],
        record_count=2,
    )
    validated = ValidatedReasoningResult(
        result_id="validated-reasoning",
        plan_id="validation-policy",
        reasoning_result_id="reasoning",
        interpretation_result_id=interpretations.result_id,
        is_valid=True,
        checks=[],
        check_count=0,
        validation_state="VALID",
    )
    timeline = HistoricalTimeline(
        timeline_id="timeline",
        plan_id="timeline-policy",
        entries=[
            TimelineEntry(
                "entry-a", "event-a", "CREATION_EVENT", "Opening fact", "1900-01-01",
                ["claim-a"], ["entity-a"],
            ),
            TimelineEntry(
                "entry-b", "event-b", "PUBLICATION_EVENT", "Outcome fact", "1901-01-01",
                ["claim-b"], ["entity-b"],
            ),
        ],
        entry_count=2,
    )
    graph = RelationshipGraph(
        graph_id="graph",
        nodes=[
            GraphNode("node-a", "EVENT_NODE", "event-a"),
            GraphNode("node-b", "EVENT_NODE", "event-b"),
        ],
        node_count=2,
        edge_count=0,
    )
    return validated, timeline, graph, interpretations


def test_documentary_planning_v2_architect_is_deterministic():
    architect = DocumentaryPlanningArchitectV2()
    first = architect.build_documentary_planning_policy()
    assert first == architect.build_documentary_planning_policy()
    assert first.created_at == CANONICAL_CREATED_AT
    assert architect.validate_policy(first)


def test_documentary_planning_v2_runtime_builds_traceable_stable_plan():
    policy = DocumentaryPlanningArchitectV2().build_documentary_planning_policy()
    runtime = DocumentaryPlanningRuntimeV2()
    first = runtime.build_documentary_plan(policy, *_inputs())
    second = runtime.build_documentary_plan(policy, *_inputs())
    assert first == second
    assert first.title == "Opening fact"
    assert first.subject == first.title
    assert first.time_range == ("1900-01-01", "1901-01-01")
    assert [chapter.chapter_role for chapter in first.major_chapters] == ["OPENING", "OUTCOME"]
    assert first.chapter_ordering == [chapter.chapter_id for chapter in first.major_chapters]
    assert first.evidence_coverage == ["evidence-a", "evidence-b"]
    assert all(chapter.created_at == CANONICAL_CREATED_AT for chapter in first.major_chapters)
    assert all(chapter.trace_metadata["event_ids"] for chapter in first.major_chapters)
    assert all(chapter.trace_metadata["reasoning_ids"] for chapter in first.major_chapters)


def test_documentary_planning_v2_rejects_unvalidated_reasoning():
    inputs = list(_inputs())
    invalid = deepcopy(inputs[0])
    invalid.is_valid = False
    invalid.validation_state = "INVALID"
    inputs[0] = invalid
    policy = DocumentaryPlanningArchitectV2().build_documentary_planning_policy()
    with pytest.raises(ValueError, match="Invalid Documentary Planning v2 inputs"):
        DocumentaryPlanningRuntimeV2().build_documentary_plan(policy, *inputs)
