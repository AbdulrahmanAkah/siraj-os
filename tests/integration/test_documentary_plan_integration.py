import pytest

from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.events.event_engine import EventEngine
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.narrative_architecture.narrative_architect import NarrativeArchitect
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_narrative_architect_requires_planner_and_does_not_mutate_graph():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    before = graph.to_dict()
    planner = DocumentaryPlanner(
        EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph))))
    )

    with pytest.raises(TypeError):
        NarrativeArchitect(planner.event_engine)

    architect = NarrativeArchitect(planner)
    plan = planner.build_documentary_plan()
    assert architect.validate_structure(
        architect.build_narrative_architecture(plan),
        plan,
    )
    assert not hasattr(architect, "graph")
    assert graph.to_dict() == before
