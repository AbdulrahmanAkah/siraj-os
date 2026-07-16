from copy import deepcopy

from src.application.causal_reasoning import CausalReasoningArchitect, CausalReasoningRuntime
from src.application.claim_extraction.models import ClaimEvidence, ClaimExtractionResult, ClaimRecord
from src.application.contradiction_detection.models import (
    ContradictionRecord,
    ContradictionResult,
)
from src.application.historical_interpretation import (
    HistoricalInterpretationArchitect,
    HistoricalInterpretationRuntime,
)
from src.application.historical_reasoning_foundation import (
    HistoricalReasoningArchitect,
    HistoricalReasoningRuntime,
)
from src.application.historical_timeline.models import HistoricalTimeline, TimelineEntry
from src.application.knowledge_confidence.models import (
    ConfidenceAssessment,
    KnowledgeConfidenceResult,
)
from src.application.narrative_reasoning import NarrativeReasoningArchitect, NarrativeReasoningRuntime
from src.application.reasoning_validation import (
    ReasoningValidationArchitect,
    ReasoningValidationRuntime,
)
from src.application.relationship_graph.models import GraphEdge
from src.application.temporal_reasoning import TemporalReasoningArchitect, TemporalReasoningRuntime


def _build_bundle_b(runtime, plan, inputs):
    claims, _, _, graph, timeline = inputs
    evidence = runtime.build_resolution_result(plan, *inputs)
    confidence = KnowledgeConfidenceResult(
        result_id="confidence-result",
        assessment=ConfidenceAssessment("confidence-assessment", []),
        record_count=0,
    )
    reasoning_plan = HistoricalReasoningArchitect().build_reasoning_plan()
    reasoning = HistoricalReasoningRuntime().build_reasoning_result(
        reasoning_plan, timeline, graph, evidence, confidence
    )
    causal_plan = CausalReasoningArchitect().build_causal_plan()
    causal = CausalReasoningRuntime().build_causal_result(causal_plan, claims, reasoning)
    temporal_plan = TemporalReasoningArchitect().build_temporal_plan()
    temporal = TemporalReasoningRuntime().build_temporal_result(temporal_plan, timeline)
    narrative_plan = NarrativeReasoningArchitect().build_narrative_reasoning_plan()
    narrative = NarrativeReasoningRuntime().build_narrative_result(
        narrative_plan, timeline, reasoning
    )
    interpretation_plan = HistoricalInterpretationArchitect().build_interpretation_plan()
    interpretation = HistoricalInterpretationRuntime().build_interpretation_result(
        interpretation_plan, reasoning, causal, temporal, narrative, evidence
    )
    validation_plan = ReasoningValidationArchitect().build_validation_plan()
    contradictions = ContradictionResult("contradictions", [], 0)
    validated = ReasoningValidationRuntime().build_validated_reasoning_result(
        validation_plan,
        reasoning,
        interpretation,
        timeline,
        graph,
        evidence,
        contradictions,
    )
    return {
        "claims": claims,
        "graph": graph,
        "timeline": timeline,
        "evidence": evidence,
        "reasoning": reasoning,
        "causal": causal,
        "temporal": temporal,
        "narrative": narrative,
        "interpretation": interpretation,
        "validation_plan": validation_plan,
        "validated": validated,
    }


def test_all_bundle_b_architects_build_deterministic_plans():
    builders = [
        (HistoricalReasoningArchitect(), "build_reasoning_plan"),
        (CausalReasoningArchitect(), "build_causal_plan"),
        (TemporalReasoningArchitect(), "build_temporal_plan"),
        (NarrativeReasoningArchitect(), "build_narrative_reasoning_plan"),
        (HistoricalInterpretationArchitect(), "build_interpretation_plan"),
        (ReasoningValidationArchitect(), "build_validation_plan"),
    ]
    for architect, method_name in builders:
        build = getattr(architect, method_name)
        assert build() == build()
        assert build().plan_id


def test_reasoning_foundation_requires_graph_and_resolved_evidence(
    evidence_resolution_runtime, evidence_resolution_plan, evidence_resolution_inputs
):
    result = _build_bundle_b(
        evidence_resolution_runtime, evidence_resolution_plan, evidence_resolution_inputs
    )
    reasoning = result["reasoning"]
    assert reasoning.chain_count > 0
    assert all(chain.evidence_ids for chain in reasoning.chains)
    assert all(chain.candidates[0].graph_node_id for chain in reasoning.chains)


def test_causal_reasoning_accepts_only_explicit_supported_patterns(
    evidence_resolution_runtime, evidence_resolution_plan, evidence_resolution_inputs
):
    pipeline = _build_bundle_b(
        evidence_resolution_runtime, evidence_resolution_plan, evidence_resolution_inputs
    )
    reasoning = deepcopy(pipeline["reasoning"])
    reasoning.chains[0].candidates[0].source_claim_ids = ["claim-causal"]
    evidence = ClaimEvidence("claim-evidence", "record", "fingerprint", "Rain CAUSES flood")
    claims = ClaimExtractionResult(
        "claims", "plan",
        claims=[
            ClaimRecord("claim-causal", "Rain CAUSES flood", [evidence], ["record"]),
            ClaimRecord("claim-unsupported", "Rain may cause flood", [evidence], ["record"]),
        ],
        claim_count=2,
    )
    plan = CausalReasoningArchitect().build_causal_plan()
    result = CausalReasoningRuntime().build_causal_result(plan, claims, reasoning)
    assert [(item.cause_text, item.relation_type, item.effect_text) for item in result.relations] == [
        ("Rain", "CAUSES", "flood")
    ]


def test_temporal_reasoning_uses_only_explicit_dates_and_stable_relations():
    timeline = HistoricalTimeline(
        "timeline", "plan",
        entries=[
            TimelineEntry("entry-a", "event-a", "DATE_EVENT", "A", "2020"),
            TimelineEntry("entry-b", "event-b", "DATE_EVENT", "B", "2020-05"),
            TimelineEntry("entry-c", "event-c", "DATE_EVENT", "C", "2021-01-01"),
            TimelineEntry("entry-d", "event-d", "DATE_EVENT", "D", None),
        ],
        entry_count=4,
    )
    plan = TemporalReasoningArchitect().build_temporal_plan()
    result = TemporalReasoningRuntime().build_temporal_result(plan, timeline)
    kinds = {item.relation_type for item in result.relations}
    assert {"BEFORE", "AFTER", "CONTAINS"} <= kinds
    assert all("event-d" not in (item.source_event_id, item.target_event_id) for item in result.relations)
    assert result == TemporalReasoningRuntime().build_temporal_result(plan, timeline)


def test_narrative_roles_and_interpretation_trace_are_complete(
    evidence_resolution_runtime, evidence_resolution_plan, evidence_resolution_inputs
):
    result = _build_bundle_b(
        evidence_resolution_runtime, evidence_resolution_plan, evidence_resolution_inputs
    )
    records = result["narrative"].records
    assert records[0].role == "BEGINNING"
    if len(records) > 1:
        assert records[-1].role == "OUTCOME"
    assert [item.position for item in records] == list(range(len(records)))
    assert all(item.reasoning_chain_ids for item in result["interpretation"].records)
    assert all(item.evidence_ids for item in result["interpretation"].records)
    assert all(item.source_reference_ids for item in result["interpretation"].records)


def test_reasoning_validation_reports_broken_graph_and_relevant_contradiction(
    evidence_resolution_runtime, evidence_resolution_plan, evidence_resolution_inputs
):
    result = _build_bundle_b(
        evidence_resolution_runtime, evidence_resolution_plan, evidence_resolution_inputs
    )
    graph = deepcopy(result["graph"])
    graph.edges.append(GraphEdge("broken-edge", "REFERENCES", "missing-node", graph.nodes[0].node_id))
    graph.edge_count += 1
    claim_id = result["reasoning"].chains[0].candidates[0].source_claim_ids[0]
    contradictions = ContradictionResult(
        "contradictions",
        [ContradictionRecord("conflict", "subject", "predicate", ["a", "b"], [claim_id])],
        1,
    )
    validated = ReasoningValidationRuntime().build_validated_reasoning_result(
        result["validation_plan"], result["reasoning"], result["interpretation"],
        result["timeline"], graph, result["evidence"], contradictions,
    )
    assert not validated.is_valid
    failures = {check.check_type: check.error_codes for check in validated.checks if not check.passed}
    assert failures["GRAPH_CONSISTENCY"] == ["BROKEN_GRAPH_EDGE"]
    assert failures["CONTRADICTION_CONFLICTS"] == ["CONTRADICTION_CONFLICT"]


def test_bundle_b_full_pipeline_is_valid_and_deterministic(
    evidence_resolution_runtime, evidence_resolution_plan, evidence_resolution_inputs
):
    first = _build_bundle_b(
        evidence_resolution_runtime, evidence_resolution_plan, evidence_resolution_inputs
    )
    second = _build_bundle_b(
        evidence_resolution_runtime, evidence_resolution_plan, evidence_resolution_inputs
    )
    assert first["validated"].is_valid
    assert first["validated"] == second["validated"]
    assert first["interpretation"] == second["interpretation"]
    assert first["validated"].check_count == 5
