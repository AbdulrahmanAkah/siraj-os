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
