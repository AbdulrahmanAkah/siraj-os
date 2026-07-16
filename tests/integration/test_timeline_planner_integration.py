import pytest

from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.events.event_engine import EventEngine
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_documentary_planner_requires_event_engine_and_does_not_mutate_graph():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    before = graph.to_dict()
    engine = EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph))))

    with pytest.raises(TypeError):
        DocumentaryPlanner(engine.selector)

    planner = DocumentaryPlanner(engine)
    assert planner.build_documentary_plan()
    assert not hasattr(planner, "graph")
    assert graph.to_dict() == before
