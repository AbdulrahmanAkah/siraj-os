import pytest

from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.events.event_engine import EventEngine
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.narrative_architecture.narrative_architect import NarrativeArchitect
from src.application.narration_planning.narration_planner import NarrationPlanner
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.script_architecture.script_architect import ScriptArchitect
from src.application.selection.claim_selector import ClaimSelector


def test_narration_planner_requires_script_architect_and_does_not_mutate_graph():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    before = graph.to_dict()
    script_architect = ScriptArchitect(
        NarrativeArchitect(
            DocumentaryPlanner(
                EventEngine(
                    ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph)))
                )
            )
        )
    )

    with pytest.raises(TypeError):
        NarrationPlanner(script_architect.narrative_architect)

    narration_planner = NarrationPlanner(script_architect)
    script_structure = script_architect.build_script_structure()
    assert narration_planner.validate_plan(
        narration_planner.build_narration_plan(script_structure),
        script_structure,
    )
    assert not hasattr(narration_planner, "graph")
    assert graph.to_dict() == before
