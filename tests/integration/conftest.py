import pytest

from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.documentary_planning.models import DocumentaryPlan, DocumentarySection
from src.application.events.event_engine import EventEngine
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.narrative_architecture.narrative_architect import NarrativeArchitect
from src.application.narration_planning.narration_planner import NarrationPlanner
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector
from src.application.script_architecture.script_architect import ScriptArchitect
from src.application.scene_planning.scene_planner import ScenePlanner
from src.application.storyboard_architecture.storyboard_architect import StoryboardArchitect
from src.application.visual_asset_architecture.visual_asset_architect import (
    VisualAssetArchitect,
)
from src.application.visual_source_selection.visual_source_selector import (
    VisualSourceSelector,
)
from src.application.source_discovery_architecture.source_discovery_architect import (
    SourceDiscoveryArchitect,
)
from src.application.source_acquisition_planning.source_acquisition_planner import (
    SourceAcquisitionPlanner,
)
from src.application.source_ingestion_architecture.source_ingestion_architect import (
    SourceIngestionArchitect,
)
from src.application.source_ingestion_runtime.models import IngestionPayload
from src.application.source_ingestion_runtime.source_ingestion_executor import (
    SourceIngestionExecutor,
)


@pytest.fixture
def narrative_architect():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    planner = DocumentaryPlanner(
        EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph))))
    )
    return NarrativeArchitect(planner)


@pytest.fixture
def documentary_plan():
    sections = [
        DocumentarySection("introduction", "Introduction", ["event_1"], 0.7, 1.75),
        DocumentarySection("chapter_1", "Chapter 1", ["event_2"], 0.4, 1.75),
        DocumentarySection("chapter_2", "Chapter 2", ["event_3"], 0.9, 1.75),
        DocumentarySection("chapter_3", "Chapter 3", ["event_4"], 0.5, 1.75),
        DocumentarySection("conclusion", "Conclusion", ["event_5"], 0.6, 1.75),
    ]
    return DocumentaryPlan(
        plan_id="plan_test",
        title="Test Documentary",
        sections=sections,
        selected_event_ids=[f"event_{index}" for index in range(1, 6)],
        estimated_runtime=8.75,
    )


@pytest.fixture
def narrative_architecture(narrative_architect, documentary_plan):
    return narrative_architect.build_narrative_architecture(documentary_plan)


@pytest.fixture
def script_architect(narrative_architect):
    return ScriptArchitect(narrative_architect)


@pytest.fixture
def script_structure(script_architect, narrative_architecture):
    return script_architect.build_script_structure(narrative_architecture)


@pytest.fixture
def narration_planner(script_architect):
    return NarrationPlanner(script_architect)


@pytest.fixture
def scene_planner(narration_planner):
    return ScenePlanner(narration_planner)


@pytest.fixture
def scene_plan(scene_planner, narration_planner, script_structure):
    return scene_planner.build_scene_plan(
        narration_planner.build_narration_plan(script_structure)
    )


@pytest.fixture
def storyboard_architect(scene_planner):
    return StoryboardArchitect(scene_planner)


@pytest.fixture
def visual_asset_architect(storyboard_architect):
    return VisualAssetArchitect(storyboard_architect)


@pytest.fixture
def visual_asset_architecture(
    visual_asset_architect,
    storyboard_architect,
    scene_plan,
):
    storyboard = storyboard_architect.build_storyboard_architecture(scene_plan)
    return visual_asset_architect.build_visual_asset_architecture(storyboard)


@pytest.fixture
def visual_source_selector(visual_asset_architect):
    return VisualSourceSelector(visual_asset_architect)


@pytest.fixture
def visual_source_plan(visual_source_selector, visual_asset_architecture):
    return visual_source_selector.build_visual_source_plan(
        visual_asset_architecture
    )


@pytest.fixture
def source_discovery_architect(visual_source_selector):
    return SourceDiscoveryArchitect(visual_source_selector)


@pytest.fixture
def source_discovery_plan(source_discovery_architect, visual_source_plan):
    return source_discovery_architect.build_source_discovery_plan(
        visual_source_plan
    )


@pytest.fixture
def source_acquisition_planner(source_discovery_architect):
    return SourceAcquisitionPlanner(source_discovery_architect)


@pytest.fixture
def source_acquisition_plan(source_acquisition_planner, source_discovery_plan):
    return source_acquisition_planner.build_source_acquisition_plan(
        source_discovery_plan
    )


@pytest.fixture
def source_ingestion_architect(source_acquisition_planner):
    return SourceIngestionArchitect(source_acquisition_planner)


@pytest.fixture
def source_ingestion_executor(source_ingestion_architect):
    return SourceIngestionExecutor(source_ingestion_architect)


@pytest.fixture
def source_ingestion_plan(source_ingestion_architect, source_acquisition_plan):
    return source_ingestion_architect.build_source_ingestion_plan(
        source_acquisition_plan
    )


@pytest.fixture
def ingestion_payloads(source_ingestion_plan):
    return {
        unit.acquisition_target_id: IngestionPayload(
            target_id=unit.acquisition_target_id,
            content_bytes=f"payload-{unit.acquisition_target_id}".encode("utf-8"),
            media_type=" Image/JPEG ",
            metadata={" Title ": " Example "},
        )
        for batch in source_ingestion_plan.batches
        for unit in batch.units
    }
