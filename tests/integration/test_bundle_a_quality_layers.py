from src.application.contradiction_detection.models import ContradictionResult
from src.application.contradiction_detection.contradiction_runtime import ContradictionRuntime
from src.application.evidence_weighting.evidence_weight_runtime import EvidenceWeightRuntime
from src.application.historical_consistency.historical_consistency_runtime import HistoricalConsistencyRuntime
from src.application.knowledge_confidence.knowledge_confidence_runtime import KnowledgeConfidenceRuntime
from src.application.multi_source_correlation.multi_source_correlation_architect import MultiSourceCorrelationArchitect
from src.application.multi_source_correlation.multi_source_correlation_runtime import MultiSourceCorrelationRuntime
from src.application.source_reliability.source_reliability_runtime import SourceReliabilityRuntime


def test_bundle_a_quality_pipeline(evidence_resolution_runtime, evidence_resolution_plan, evidence_resolution_inputs):
    claims, entities, events, graph, timeline = evidence_resolution_inputs
    evidence = evidence_resolution_runtime.build_resolution_result(evidence_resolution_plan, *evidence_resolution_inputs)
    correlation_plan = MultiSourceCorrelationArchitect().build_correlation_plan()
    correlation = MultiSourceCorrelationRuntime().build_correlation_result(correlation_plan, claims, entities, events)
    consistency = HistoricalConsistencyRuntime().build_consistency_result(events, graph, timeline)
    contradictions = ContradictionRuntime().detect_contradictions(claims)
    reliability = SourceReliabilityRuntime().build_reliability_result(evidence, contradictions)
    weights = EvidenceWeightRuntime().build_weight_result(evidence, reliability, correlation)
    confidence = KnowledgeConfidenceRuntime().build_confidence_result(weights, reliability, contradictions)

    assert consistency.check_count == 4
    assert reliability.score_count
    assert weights.weight_count == evidence.evidence_count
    assert confidence.record_count == weights.weight_count


def test_quality_layer_validation_interfaces():
    assert ContradictionRuntime().validate_contradictions(ContradictionResult("result", [], 0))
