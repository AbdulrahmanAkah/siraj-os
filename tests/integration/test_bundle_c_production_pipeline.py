from src.application.documentary_planning_v2 import DocumentaryPlanningArchitectV2, DocumentaryPlanningRuntimeV2
from src.application.narrative_architecture_v2 import NarrativeArchitectureArchitectV2, NarrativeArchitectureRuntimeV2
from src.application.documentary_script_runtime import DocumentaryScriptArchitect, DocumentaryScriptRuntime
from src.application.scene_generation_runtime import SceneGenerationArchitect, SceneGenerationRuntime
from src.application.storyboard_runtime import StoryboardArchitectRuntime, StoryboardRuntime
from src.application.documentary_assembly import DocumentaryAssemblyArchitect, DocumentaryAssemblyRuntime
from src.application.visual_evidence import VisualEvidenceArchitect, VisualEvidenceRuntime
from src.application.source_attribution import SourceAttributionArchitect, SourceAttributionRuntime
from src.application.documentary_verification import DocumentaryVerificationArchitect, DocumentaryVerificationRuntime
from src.application.publication_packaging import PublicationPackagingArchitect, PublicationPackagingRuntime
from src.application.export_architecture import ExportArchitect, ExportArchitectureRuntime
from src.application.production_runtime import ProductionArchitect, ProductionRuntime
from src.application.historical_interpretation.models import HistoricalInterpretationResult, InterpretationRecord
from src.application.historical_timeline.models import HistoricalTimeline, TimelineEntry
from src.application.reasoning_validation.models import ValidatedReasoningResult
from src.application.relationship_graph.models import GraphNode, RelationshipGraph


def _planning_inputs():
    interpretations = HistoricalInterpretationResult("interpretations", "policy", [
        InterpretationRecord("interpretation-a", "Opening", ["chain-a"], ["narrative-a"], evidence_ids=["evidence-a"], source_reference_ids=["source-a"], position=0),
        InterpretationRecord("interpretation-b", "Outcome", ["chain-b"], ["narrative-b"], evidence_ids=["evidence-b"], source_reference_ids=["source-b"], position=1),
    ], 2)
    validated = ValidatedReasoningResult("validated", "policy", "reasoning", interpretations.result_id, True, [], 0, "VALID")
    timeline = HistoricalTimeline("timeline", "policy", [
        TimelineEntry("entry-a", "event-a", "CREATION_EVENT", "Opening", "1900", ["claim-a"], ["entity-a"]),
        TimelineEntry("entry-b", "event-b", "PUBLICATION_EVENT", "Outcome", "1901", ["claim-b"], ["entity-b"]),
    ], 2)
    graph = RelationshipGraph("graph", nodes=[GraphNode("node-a", "EVENT_NODE", "event-a"), GraphNode("node-b", "EVENT_NODE", "event-b")], node_count=2, edge_count=0)
    return validated, timeline, graph, interpretations


def test_bundle_c_produces_deterministic_production_ready_documentary():
    plan = DocumentaryPlanningRuntimeV2().build_documentary_plan(DocumentaryPlanningArchitectV2().build_documentary_planning_policy(), *_planning_inputs())
    narrative = NarrativeArchitectureRuntimeV2().build_narrative_architecture(NarrativeArchitectureArchitectV2().build_narrative_policy(), plan)
    script = DocumentaryScriptRuntime().build_documentary_script(DocumentaryScriptArchitect().build_script_policy(), narrative)
    scenes = SceneGenerationRuntime().build_scene_plan(SceneGenerationArchitect().build_scene_generation_policy(), script)
    storyboard = StoryboardRuntime().build_storyboard(StoryboardArchitectRuntime().build_storyboard_policy(), scenes)
    package = DocumentaryAssemblyRuntime().build_documentary_package(DocumentaryAssemblyArchitect().build_assembly_policy(), plan, narrative, script, scenes, storyboard)
    visuals = VisualEvidenceRuntime().build_visual_evidence_map(VisualEvidenceArchitect().build_visual_evidence_policy(), package, scenes, storyboard)
    attributions = SourceAttributionRuntime().build_attribution_result(SourceAttributionArchitect().build_attribution_policy(), package, storyboard)
    verification = DocumentaryVerificationRuntime().build_verification_report(DocumentaryVerificationArchitect().build_verification_policy(), package, scenes, storyboard, visuals, attributions)
    publication = PublicationPackagingRuntime().build_publication_package(PublicationPackagingArchitect().build_publication_policy(), package, attributions, verification)
    exports = ExportArchitectureRuntime().build_export_bundle(ExportArchitect().build_export_policy(), publication)
    production = ProductionRuntime().build_production_ready_documentary(ProductionArchitect().build_production_policy(), publication, exports, verification)
    assert production.validation_state == "VALID"
    assert verification.is_valid
    assert storyboard.frame_count == scenes.scene_count
    assert attributions.record_count == storyboard.frame_count
    assert exports.manifest.publication_package_id == publication.package_id
    assert production.production_id == ProductionRuntime().build_production_ready_documentary(ProductionArchitect().build_production_policy(), publication, exports, verification).production_id
